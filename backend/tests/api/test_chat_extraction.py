"""API integration: chat extraction persists a durable workout + preference.

External providers are replaced with deterministic fakes (the primary LLM and
the dedicated extractor), while persistence uses the real services and the
in-memory database shared by the ``client`` fixture. This distinguishes mocked
providers from real database behaviour.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.extraction.schemas import CompletedWorkout, ExtractionResult, UserPreference
from app.services import chat_service as chat_service_module

_RESULT = ExtractionResult(
    completed_workouts=[
        CompletedWorkout(
            activity="cycling",
            duration_minutes=120,
            confidence=0.95,
            source_text="I did cycling for 2 hours",
        )
    ],
    user_preferences=[UserPreference(preference="enjoys cycling", confidence=0.9)],
)


class _FakeExtractor:
    def __init__(self, api_key=None, model=None) -> None:  # accepts settings kwargs
        pass

    def extract(self, message: str, now=None) -> ExtractionResult:
        return _RESULT


class _FakePrimaryLLM:
    """Deterministic stand-in for the primary Groq assistant (no records)."""

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        return '{"facts":[]}'

    def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
        return "Cycling is great cardio! Aim for a steady pace you can sustain."


class _BoomVectorStore:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("chroma disabled in this test")


@pytest.fixture
def wired(client: TestClient, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")
    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", _FakeExtractor)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: _FakePrimaryLLM())
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)
    return client


def test_cycling_message_creates_durable_workout_and_preference(wired: TestClient) -> None:
    resp = wired.post(
        "/api/v1/chat", json={"message": "I did cycling today and I love it. I did it for 2 hours."}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Truthful confirmation only appears because the DB write succeeded.
    assert "Workout recorded: cycling, 120 min" in body["response"]
    assert any(
        e["tool"] == "extract_completed_workout" and e["status"] == "saved"
        for e in body["tool_events"]
    )

    # Durable workout record in the authoritative store.
    workouts = wired.get("/api/v1/workouts?limit=20").json()
    assert workouts["total"] == 1
    session = workouts["items"][0]
    assert session["name"] == "cycling"
    assert session["duration_minutes"] == 120

    # Preference stored SEPARATELY in the profile, not inside the workout.
    profile = wired.get("/api/v1/profile").json()
    assert "enjoys cycling" in (profile.get("preferences") or {}).get("interests", [])


def test_new_conversation_can_read_the_persisted_workout(wired: TestClient) -> None:
    # Chat 1: report cycling.
    first = wired.post("/api/v1/chat", json={"message": "I did cycling for 2 hours today."}).json()

    # Chat 2: a brand-new conversation asks about today's workout.
    second = wired.post(
        "/api/v1/chat", json={"message": "What exercise did I do today, and for how long?"}
    ).json()
    assert second["conversation_id"] != first["conversation_id"]

    # The actual persisted workout is retrievable regardless of conversation.
    workouts = wired.get("/api/v1/workouts?limit=20").json()
    assert any(
        item["name"] == "cycling" and item["duration_minutes"] == 120 for item in workouts["items"]
    )


def test_workout_recording_is_idempotent_on_retry(wired: TestClient) -> None:
    message = {"message": "I did cycling today for 2 hours."}
    wired.post("/api/v1/chat", json=message)
    wired.post("/api/v1/chat", json=message)  # resubmit / retry
    workouts = wired.get("/api/v1/workouts?limit=20").json()
    assert workouts["total"] == 1  # no duplicate


def test_extraction_failure_does_not_break_chat(client: TestClient, monkeypatch) -> None:
    # Extraction enabled but the provider raises; chat must still answer and
    # must NOT claim any record was saved.
    monkeypatch.setattr(settings, "agent_activity_extraction", True)
    monkeypatch.setattr(settings, "extraction_api_key", "test-extraction-key")

    class _Broken:
        def __init__(self, api_key=None, model=None) -> None:
            pass

        def extract(self, message, now=None):
            raise RuntimeError("provider down")

    monkeypatch.setattr(chat_service_module, "GroqActivityExtractor", _Broken)
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: _FakePrimaryLLM())
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)

    resp = client.post("/api/v1/chat", json={"message": "I did cycling for 2 hours."})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Cycling is great cardio!" in body["response"]
    assert "Workout recorded" not in body["response"]
    assert wired_workouts_total(client) == 0


def wired_workouts_total(client: TestClient) -> int:
    return client.get("/api/v1/workouts?limit=20").json()["total"]
