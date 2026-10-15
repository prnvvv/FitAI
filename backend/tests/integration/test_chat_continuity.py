"""Integration: cross-chat continuity wiring in the real chat path.

External providers (primary LLM, summary LLM) and the vector store are replaced
with deterministic fakes; persistence uses the real services and the in-memory
database shared by the ``client`` fixture. This distinguishes mocked providers
from real database behaviour (summary rows, conversation ownership).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthUser
from app.models.conversation import ConversationSummary
from app.models.enums import MemoryKey, MemoryStatus
from app.models.memory import Memory
from app.repositories.user_repository import UserRepository
from app.services import chat_service as chat_service_module
from app.services.chat_service import ChatService, _ContinuityReaderAdapter
from app.services.profile_service import ProfileService

_SUMMARY_TEXT = "User is cutting to 72 kg and asked about protein."


class _FakePrimaryLLM:
    """Deterministic stand-in for the primary Groq assistant (no records)."""

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        return '{"facts":[]}'

    def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
        return "Here is some guidance you can use."


class _FakeSummaryLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.calls.append(user)
        return _SUMMARY_TEXT


class _FakeVectorStore:
    """Inert stand-in so the retriever and continuity store construct offline."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def query(self, *args, **kwargs):
        return []

    def add_chunks(self, *args, **kwargs) -> int:
        return 0

    def delete_document(self, *args, **kwargs) -> int:
        return 0

    def list_vectors(self, *args, **kwargs):
        return []


class _RecordingContinuityStore:
    """Captures summary indexing and memory syncs without touching Chroma."""

    instances: list[_RecordingContinuityStore] = []

    def __init__(self, store) -> None:
        self.store = store
        self.summaries: list[dict] = []
        self.synced: list[tuple[str, dict]] = []
        _RecordingContinuityStore.instances.append(self)

    def index_summary(self, user_id, conversation_id, text, title=None) -> None:
        self.summaries.append(
            {"user_id": user_id, "conversation_id": conversation_id, "text": text, "title": title}
        )

    def sync_memories(self, user_id, mapping) -> None:
        self.synced.append((user_id, mapping))

    def search(self, *args, **kwargs):
        return []

    def delete_memory(self, *args, **kwargs) -> int:
        return 0

    def delete_summary(self, *args, **kwargs) -> int:
        return 0


@pytest.fixture
def wired(client: TestClient, monkeypatch) -> TestClient:
    _RecordingContinuityStore.instances.clear()
    monkeypatch.setattr(chat_service_module.settings, "continuity_enabled", True)
    monkeypatch.setattr(chat_service_module, "VectorStore", _FakeVectorStore)
    monkeypatch.setattr(chat_service_module, "ContinuityStore", _RecordingContinuityStore)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: _FakePrimaryLLM())
    )
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "_build_summary_llm",
        staticmethod(lambda: _FakeSummaryLLM()),
    )
    return client


def test_new_chat_summarises_previous_conversation(wired: TestClient, db_session: Session) -> None:
    first = wired.post("/api/v1/chat", json={"message": "I am cutting to 72 kg."}).json()
    conv_a = UUID(first["conversation_id"])

    # A brand-new conversation is started; the previous one is flushed.
    second = wired.post("/api/v1/chat", json={"message": "How much protein should I eat?"}).json()
    assert UUID(second["conversation_id"]) != conv_a

    rows = db_session.scalars(select(ConversationSummary)).all()
    assert len(rows) == 1
    assert rows[0].conversation_id == conv_a
    assert rows[0].summary == _SUMMARY_TEXT
    assert rows[0].message_count == 2

    # The summary was also indexed into continuity recall.
    indexed = [s for store in _RecordingContinuityStore.instances for s in store.summaries]
    assert any(s["conversation_id"] == str(conv_a) for s in indexed)


def test_summary_is_not_recomputed_when_unchanged(wired: TestClient, db_session: Session) -> None:
    wired.post("/api/v1/chat", json={"message": "I am cutting to 72 kg."})
    wired.post("/api/v1/chat", json={"message": "How much protein?"})  # flushes conv A
    # Two more new chats flush conv B twice; A must not be summarised again.
    wired.post("/api/v1/chat", json={"message": "And fibre?"})
    wired.post("/api/v1/chat", json={"message": "And water?"})
    rows = db_session.scalars(select(ConversationSummary)).all()
    # One row per conversation, never two for the same conversation.
    conv_ids = [row.conversation_id for row in rows]
    assert len(conv_ids) == len(set(conv_ids))


def test_chat_indexes_current_memory_for_semantic_recall(
    wired: TestClient, db_session: Session
) -> None:
    wired.post("/api/v1/chat", json={"message": "Hello"})
    synced = [
        mapping for store in _RecordingContinuityStore.instances for _, mapping in store.synced
    ]
    # At minimum a sync happened; with no memory it is empty, with memory it is not.
    assert synced  # the chat path always reconciles memory vectors


# ---------------------------------------------------------------------------
# Toggle enforcement (server-side) and adapter behaviour
# ---------------------------------------------------------------------------


class _StubStore:
    def __init__(self, hits_by_kind: dict[str, list]) -> None:
        self._hits = hits_by_kind
        self.kinds: list[str | None] = []

    def search(self, user_id, query, *, k=6, kind=None, min_score=0.25):
        self.kinds.append(kind)
        return self._hits.get(kind or "", [])


class _Hit:
    def __init__(self, text: str, kind: str) -> None:
        self.text = text
        self.kind = kind
        self.metadata = {"title": "Earlier chat"} if kind == "summary" else {}


def test_adapter_recalls_both_layers_when_enabled() -> None:
    store = _StubStore(
        {"memory": [_Hit("weight: 72 kg", "memory")], "summary": [_Hit("cutting plan", "summary")]}
    )
    adapter = _ContinuityReaderAdapter(store, use_memory=True, use_past_chats=True)
    ctx = adapter.recall("user-1", "what is my weight?")
    assert ctx.memories == ["weight: 72 kg"]
    assert ctx.past_chats and "cutting plan" in ctx.past_chats[0]
    assert set(store.kinds) == {"memory", "summary"}


def test_adapter_respects_toggles() -> None:
    store = _StubStore({"memory": [_Hit("weight: 72 kg", "memory")]})
    adapter = _ContinuityReaderAdapter(store, use_memory=False, use_past_chats=False)
    ctx = adapter.recall("user-1", "what is my weight?")
    assert ctx.is_empty
    assert store.kinds == []  # no store query when both toggles are off


def test_toggles_default_true_and_respect_preferences(db_session: Session) -> None:
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "toggles@example.com")
    service = ChatService(db_session)
    assert service._toggles(user_id) == (True, True)

    ProfileService(db_session).update(
        user_id,
        {"preferences": {"use_memory": False, "reference_past_chats": False}},
        partial=True,
    )
    assert service._toggles(user_id) == (False, False)


def test_index_memories_syncs_current_values(db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(chat_service_module.settings, "continuity_enabled", True)
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "index@example.com")
    db_session.add(
        Memory(user_id=user_id, key=MemoryKey.WEIGHT, value=72.0, status=MemoryStatus.ACTIVE)
    )
    db_session.commit()

    store = _RecordingContinuityStore(_FakeVectorStore())
    ChatService(db_session)._index_memories(user_id, store)
    assert len(store.synced) == 1
    mapped_user, mapping = store.synced[0]
    assert mapped_user == str(user_id)
    assert mapping["weight"].startswith("weight: 72")


def test_make_client_user_isolation_for_toggles(make_client, db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "iso@example.com")
    ProfileService(db_session).update(uid, {"preferences": {"use_memory": False}}, partial=True)
    client = make_client(AuthUser(id=uid, email="iso@example.com"))
    # The endpoint still works; the toggle is enforced inside the service.
    assert client.get("/api/v1/profile").status_code == 200
    assert ChatService(db_session)._toggles(uid) == (False, True)
