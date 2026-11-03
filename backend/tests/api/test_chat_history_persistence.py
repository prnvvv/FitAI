"""Regression tests: a conversation's history is persisted, ordered and isolated.

The frontend reloads history from these endpoints on every refresh and every
conversation switch, so they must return the complete, correctly ordered,
owner-scoped message list. Chat uses the real services and the in-memory database
shared by the ``client`` fixture; only the LLM and the vector store are faked.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import AuthUser
from app.services import chat_service as chat_service_module


class _FakePrimaryLLM:
    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        return '{"facts":[]}'

    def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
        # Echo the latest user text so each reply is identifiable per conversation.
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"Coach reply to: {last_user}"


class _BoomVectorStore:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("chroma disabled in this test")


@pytest.fixture
def wired_chat(make_client, monkeypatch):
    monkeypatch.setattr(settings, "agent_activity_extraction", False)
    # Keep the suite offline: the prompt guard would otherwise call Groq with the
    # developer's real key from backend/.env.
    monkeypatch.setattr(settings, "prompt_guard_enabled", False)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: _FakePrimaryLLM())
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)
    return make_client


def _history(client: TestClient, conversation_id: str, **params: int) -> dict:
    response = client.get(f"/api/v1/conversations/{conversation_id}/messages", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_chat_turns_are_persisted_in_order_and_reloadable(wired_chat) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))

    first = client.post("/api/v1/chat", json={"message": "How do I start squatting?"}).json()
    conversation_id = first["conversation_id"]
    for text in ("What about depth?", "And foot placement?"):
        reply = client.post(
            "/api/v1/chat", json={"message": text, "conversation_id": conversation_id}
        ).json()
        assert reply["conversation_id"] == conversation_id

    # Simulates a page refresh: history is read fresh from the API/database.
    page = _history(client, conversation_id)
    assert page["total"] == 6
    roles = [m["role"] for m in page["items"]]
    assert roles == ["user", "assistant"] * 3
    contents = [m["content"] for m in page["items"]]
    assert contents[0] == "How do I start squatting?"
    assert contents[2] == "What about depth?"
    assert contents[4] == "And foot placement?"
    assert all(m["conversation_id"] == conversation_id for m in page["items"])
    assert len({m["id"] for m in page["items"]}) == 6  # stable, unique ids
    stamps = [m["created_at"] for m in page["items"]]
    assert stamps == sorted(stamps)

    # Reading twice returns the same ids: they are stable across reloads.
    again = _history(client, conversation_id)
    assert [m["id"] for m in again["items"]] == [m["id"] for m in page["items"]]


def test_assistant_message_keeps_sources_actions_and_tool_events(wired_chat) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))
    reply = client.post("/api/v1/chat", json={"message": "Plan my week"}).json()

    stored = _history(client, reply["conversation_id"])["items"][-1]
    assert stored["role"] == "assistant"
    metadata = stored["metadata"]
    assert set(metadata) >= {"sources", "actions", "tool_events"}


def test_two_conversations_keep_separate_histories(wired_chat) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))
    a = client.post("/api/v1/chat", json={"message": "alpha topic"}).json()["conversation_id"]
    b = client.post("/api/v1/chat", json={"message": "beta topic"}).json()["conversation_id"]
    client.post("/api/v1/chat", json={"message": "alpha again", "conversation_id": a})

    history_a = [m["content"] for m in _history(client, a)["items"]]
    history_b = [m["content"] for m in _history(client, b)["items"]]
    assert "alpha topic" in history_a and "alpha again" in history_a
    assert not any("beta" in text for text in history_a)
    assert any("beta topic" in text for text in history_b)
    assert not any("alpha" in text for text in history_b)


def test_history_pages_cover_the_whole_conversation(wired_chat) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))
    conversation_id = client.post("/api/v1/chat", json={"message": "m0"}).json()["conversation_id"]
    for i in range(1, 6):
        client.post("/api/v1/chat", json={"message": f"m{i}", "conversation_id": conversation_id})

    full = _history(client, conversation_id, limit=100, offset=0)
    collected: list[str] = []
    for offset in range(0, full["total"], 5):
        collected += [
            m["id"] for m in _history(client, conversation_id, limit=5, offset=offset)["items"]
        ]
    assert collected == [m["id"] for m in full["items"]]
    assert full["total"] == 12


def test_another_user_cannot_read_or_write_a_conversation(wired_chat) -> None:
    owner = wired_chat(AuthUser(id=uuid.uuid4()))
    other = wired_chat(AuthUser(id=uuid.uuid4()))
    conversation_id = owner.post("/api/v1/chat", json={"message": "private plan"}).json()[
        "conversation_id"
    ]

    assert other.get(f"/api/v1/conversations/{conversation_id}/messages").status_code == 404
    assert other.get("/api/v1/conversations").json()["total"] == 0
    intruder = other.post(
        "/api/v1/chat", json={"message": "hello", "conversation_id": conversation_id}
    )
    assert intruder.status_code == 404
    # The owner's history is untouched by the attempt.
    contents = [m["content"] for m in _history(owner, conversation_id)["items"]]
    assert contents[0] == "private plan" and "hello" not in contents


def test_deleted_conversation_cannot_be_loaded_and_new_chats_still_work(wired_chat) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))
    doomed = client.post("/api/v1/chat", json={"message": "to be deleted"}).json()[
        "conversation_id"
    ]
    kept = client.post("/api/v1/chat", json={"message": "to be kept"}).json()["conversation_id"]

    assert client.delete(f"/api/v1/conversations/{doomed}").status_code == 204
    assert client.get(f"/api/v1/conversations/{doomed}/messages").status_code == 404
    assert (
        client.post(
            "/api/v1/chat", json={"message": "revive?", "conversation_id": doomed}
        ).status_code
        == 404
    )
    assert [m["content"] for m in _history(client, kept)["items"]][0] == "to be kept"
    fresh = client.post("/api/v1/chat", json={"message": "brand new"}).json()
    assert _history(client, fresh["conversation_id"])["total"] == 2


def test_failed_chat_turn_does_not_corrupt_existing_history(wired_chat, monkeypatch) -> None:
    client = wired_chat(AuthUser(id=uuid.uuid4()))
    conversation_id = client.post("/api/v1/chat", json={"message": "first"}).json()[
        "conversation_id"
    ]
    before = _history(client, conversation_id)

    class _BrokenLLM(_FakePrimaryLLM):
        def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
            raise RuntimeError("provider down")

    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: _BrokenLLM())
    )
    # The agent degrades gracefully when the model provider fails: the turn still
    # completes, and what is stored must stay a well-formed question/answer pair.
    client.post("/api/v1/chat", json={"message": "second", "conversation_id": conversation_id})

    after = _history(client, conversation_id)
    assert [m["id"] for m in after["items"][: len(before["items"])]] == [
        m["id"] for m in before["items"]
    ]
    assert [m["role"] for m in after["items"]] == ["user", "assistant"] * (after["total"] // 2)
    assert after["items"][2]["content"] == "second"
    assert all(m["content"] for m in after["items"])
    ids = [m["id"] for m in after["items"]]
    assert len(ids) == len(set(ids))
