"""End-to-end automatic memory intelligence: extract -> persist -> retrieve.

Both LLM calls are replaced by deterministic fakes (the dedicated extraction
model and the primary chat model), while persistence, reconciliation and
retrieval use the REAL services against the in-memory database. The primary
model records the exact prompt it receives, which proves the retrieved memory
actually reaches the answering model rather than only being stored.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.extraction.reconciliation import HISTORY_KEY, INSIGHTS_KEY
from app.extraction.schemas import (
    CompletedWorkout,
    ExtractionResult,
    MemoryInsight,
    ProgressRecord,
)
from app.models.enums import MeasurementType
from app.services import chat_service as chat_service_module


class _ScriptedExtractor:
    """Dedicated extraction model: returns a fixed candidate set per message."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.calls: list[str] = []

    def extract(self, message: str, now=None) -> ExtractionResult:
        self.calls.append(message)
        if "cycling every day" in message:
            return ExtractionResult(
                memory_insights=[
                    MemoryInsight(
                        text="cycles every day",
                        category="routine",
                        confidence=0.95,
                        source_text="I like to do cycling every day",
                    )
                ]
            )
        if "might try swimming" in message:
            return ExtractionResult(
                memory_insights=[
                    MemoryInsight(
                        text="might try swimming someday",
                        confidence=0.8,
                        source_text="I might try swimming someday",
                    )
                ]
            )
        if "used to run" in message:
            return ExtractionResult(
                memory_insights=[
                    MemoryInsight(
                        text="used to run every morning",
                        category="routine",
                        confidence=0.9,
                        source_text="I used to run every morning",
                    )
                ]
            )
        return ExtractionResult()


class _RecordingPrimaryLLM:
    """Primary chat model that records the prompt and answers deterministically."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.prompts.append(user)
        return "Sure - based on what you have told me before."

    def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
        self.prompts.append(str(messages[-1].get("content", "")))
        if "cycl" in messages[-1].get("content", "").lower():
            return "You told me you like to do cycling every day."
        return "I don't have anything remembered about that yet."


class _BoomVectorStore:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("chroma disabled in this test")


@pytest.fixture
def primary() -> _RecordingPrimaryLLM:
    return _RecordingPrimaryLLM()


@pytest.fixture
def extractor() -> _ScriptedExtractor:
    return _ScriptedExtractor()


@pytest.fixture
def wired(
    client: TestClient, monkeypatch, primary: _RecordingPrimaryLLM, extractor: _ScriptedExtractor
) -> TestClient:
    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", lambda **kw: extractor)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: primary)
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)
    return client


def _insights(client: TestClient) -> list[dict]:
    prefs = client.get("/api/v1/profile").json().get("preferences") or {}
    return prefs.get(INSIGHTS_KEY) or []


# --- the required cross-chat scenario ---------------------------------------
def test_fact_from_one_conversation_is_retrieved_in_another(
    wired: TestClient, primary: _RecordingPrimaryLLM
) -> None:
    first = wired.post("/api/v1/chat", json={"message": "I like to do cycling every day."}).json()
    assert first["conversation_id"]
    assert "Noted for future chats" in first["response"]

    second = wired.post("/api/v1/chat", json={"message": "What do I like to do every day?"}).json()
    assert second["conversation_id"] != first["conversation_id"]

    # The stored fact exists in the authoritative store...
    assert any(i["text"] == "cycles every day" for i in _insights(wired))
    # ...and the primary model actually received it in a later conversation.
    assert any("cycles every day" in p for p in primary.prompts)
    assert "cycling every day" in second["response"]


def test_equivalently_worded_question_still_retrieves(
    wired: TestClient, primary: _RecordingPrimaryLLM
) -> None:
    """Different wording, same stored fact: retrieval is not keyword-exact."""
    wired.post("/api/v1/chat", json={"message": "I like to do cycling every day."})
    primary.prompts.clear()
    resp = wired.post("/api/v1/chat", json={"message": "What activities do I enjoy?"}).json()
    assert any("cycles every day" in p for p in primary.prompts)
    assert "cycling every day" in resp["response"]


# --- hypothetical must not become a stored preference -----------------------
def test_hypothetical_is_not_saved(wired: TestClient) -> None:
    resp = wired.post("/api/v1/chat", json={"message": "I might try swimming someday."}).json()
    assert "Noted for future chats" not in resp["response"]
    assert _insights(wired) == []


def test_historical_statement_is_kept_but_not_current(wired: TestClient) -> None:
    resp = wired.post("/api/v1/chat", json={"message": "I used to run every morning."}).json()
    prefs = wired.get("/api/v1/profile").json().get("preferences") or {}
    stored = prefs.get(INSIGHTS_KEY) or []
    assert stored and stored[0]["status"] == "historical"
    # It is announced honestly as a past habit, never as current behaviour.
    assert "used to do" in resp["response"]


def test_historical_fact_is_not_pinned_as_current(wired: TestClient, primary) -> None:
    wired.post("/api/v1/chat", json={"message": "I used to run every morning."})
    primary.prompts.clear()
    wired.post("/api/v1/chat", json={"message": "What is my routine?"})
    prompt = primary.prompts[-1]
    assert "used to run every morning" not in prompt


def test_repeated_statement_does_not_duplicate(wired: TestClient) -> None:
    wired.post("/api/v1/chat", json={"message": "I like to do cycling every day."})
    wired.post("/api/v1/chat", json={"message": "I like to do cycling every day."})
    assert len(_insights(wired)) == 1


# --- user isolation ---------------------------------------------------------
def test_other_user_cannot_retrieve_the_fact(make_client, monkeypatch, primary, extractor) -> None:
    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", lambda **kw: extractor)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: primary)
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)

    alice = make_client()
    bob = make_client()
    alice.post("/api/v1/chat", json={"message": "I like to do cycling every day."})

    assert (bob.get("/api/v1/profile").json().get("preferences") or {}).get(INSIGHTS_KEY) is None
    bob.post("/api/v1/chat", json={"message": "What do I like to do every day?"})
    assert not any("cycles every day" in p for p in primary.prompts[-1:])


# --- deletion is honoured ---------------------------------------------------
def test_deleting_the_fact_stops_future_retrieval(wired: TestClient, primary) -> None:
    """A user clearing the remembered fact is never told they still do it."""
    wired.post("/api/v1/chat", json={"message": "I like to do cycling every day."})
    assert _insights(wired)

    cleared = wired.patch(
        "/api/v1/profile", json={"preferences": {INSIGHTS_KEY: [], HISTORY_KEY: []}}
    )
    assert cleared.status_code == 200

    primary.prompts.clear()
    resp = wired.post("/api/v1/chat", json={"message": "What do I like to do every day?"}).json()
    assert not any("cycles every day" in p for p in primary.prompts)
    assert "don't have anything remembered" in resp["response"]


# --- workout routing does not duplicate into memory ------------------------
def test_completed_workout_is_not_stored_as_generic_memory(
    client: TestClient, monkeypatch, primary: _RecordingPrimaryLLM
) -> None:
    class _WorkoutExtractor:
        def __init__(self, api_key=None, model=None) -> None:
            pass

        def extract(self, message: str, now=None) -> ExtractionResult:
            return ExtractionResult(
                completed_workouts=[
                    CompletedWorkout(
                        activity="running",
                        duration_minutes=30,
                        distance_meters=5000,
                        confidence=0.95,
                        source_text="I completed a 5 km run today",
                    )
                ]
            )

    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", _WorkoutExtractor)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: primary)
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)

    resp = client.post("/api/v1/chat", json={"message": "I completed a 5 km run today."}).json()
    workouts = client.get("/api/v1/workouts?limit=10").json()
    assert workouts["total"] == 1
    prefs = client.get("/api/v1/profile").json().get("preferences") or {}
    assert not prefs.get(INSIGHTS_KEY)  # no competing generic-memory record
    assert any(e["tool"] == "extract_completed_workout" for e in resp["tool_events"])


def test_measurement_routes_to_progress_store(
    client: TestClient, monkeypatch, primary: _RecordingPrimaryLLM
) -> None:
    class _MeasurementExtractor:
        def __init__(self, api_key=None, model=None) -> None:
            pass

        def extract(self, message: str, now=None) -> ExtractionResult:
            return ExtractionResult(
                progress_records=[
                    ProgressRecord(
                        measurement_type=MeasurementType.WEIGHT,
                        value=72,
                        unit="kg",
                        confidence=0.95,
                        source_text="I weighed 72 kg today",
                    )
                ]
            )

    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", _MeasurementExtractor)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: primary)
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)

    client.post("/api/v1/chat", json={"message": "I weighed 72 kg today."})
    series = client.get("/api/v1/progress/weight").json()
    assert series
    assert float(series[0]["value"]) == 72.0
