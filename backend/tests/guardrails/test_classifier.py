"""Tests for the LLM intent classifier and the guard decision gate.

Unit tests cover parsing, the fail-closed decision logic, fallback behaviour and
caching. The integration test drives the real ``POST /api/v1/chat`` route with a
fake classifier to prove the classifier blocks an off-scope message that the
deterministic regex rules miss, and that a refusal never reaches the model.

No test touches the network: the classifier is a fake here, and the root
conftest disables the default (real) classifier for the whole suite.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.guardrails.classifier import Intent, parse_intent
from app.guardrails.guard import (
    GuardDecision,
    classify_and_decide,
    clear_decision_cache,
)
from app.services import chat_service as chat_service_module

# ---------------------------------------------------------------------------
# parse_intent
# ---------------------------------------------------------------------------


def test_parse_intent_valid_json() -> None:
    raw = (
        '{"label":"fitness","in_scope":true,"wants_tool":false,'
        '"confidence":0.9,"reason":"nutrition question"}'
    )
    intent = parse_intent(raw)
    assert intent is not None
    assert intent.label == "fitness"
    assert intent.in_scope is True
    assert intent.wants_tool is False
    assert intent.confidence == pytest.approx(0.9)


def test_parse_intent_tolerates_markdown_fence() -> None:
    raw = (
        '```json\n{"label":"off_topic","in_scope":false,"wants_tool":false,'
        '"confidence":0.95,"reason":"unrelated"}\n```'
    )
    intent = parse_intent(raw)
    assert intent is not None
    assert intent.label == "off_topic"


def test_parse_intent_tolerates_wrapped_object() -> None:
    raw = (
        '{"intent":{"label":"code_request","in_scope":false,"wants_tool":false,'
        '"confidence":0.9,"reason":"asks for code"}}'
    )
    intent = parse_intent(raw)
    assert intent is not None
    assert intent.label == "code_request"


@pytest.mark.parametrize(
    "raw",
    [
        "",  # empty
        "not json at all",
        '{"label":"nope","in_scope":true,"wants_tool":false,"confidence":0.9}',
        '{"label":"fitness","in_scope":true,"wants_tool":false,"confidence":5.0}',
        '{"in_scope":true,"wants_tool":false,"confidence":0.9}',
        "[1,2,3]",
    ],
)
def test_parse_intent_rejects_unusable_output(raw: str) -> None:
    assert parse_intent(raw) is None


# ---------------------------------------------------------------------------
# classify_and_decide
# ---------------------------------------------------------------------------


class _FakeClassifier:
    """Classifier stand-in returning a preset intent and recording calls."""

    def __init__(self, intent: Intent | None) -> None:
        self._intent = intent
        self.calls: list[str] = []

    def classify(self, message: str) -> Intent | None:
        self.calls.append(message)
        return self._intent


def _intent(**kwargs: Any) -> Intent:
    base = {
        "label": "fitness",
        "in_scope": True,
        "wants_tool": False,
        "confidence": 0.95,
        "reason": "fitness question",
    }
    base.update(kwargs)
    return Intent.model_validate(base)


def test_deterministic_block_short_circuits_classifier() -> None:
    clf = _FakeClassifier(_intent())
    decision = classify_and_decide("I want to kill myself", "user-1", clf)
    assert decision.blocked is True
    assert decision.category == "self_harm"
    assert decision.source == "deterministic"
    assert clf.calls == []  # classifier never ran


def test_no_classifier_allows_deterministically() -> None:
    decision = classify_and_decide("how many calories to build muscle", "user-1", None)
    assert decision.blocked is False
    assert decision.source == "deterministic"


def test_classifier_fitness_intent_allows_and_keeps_wants_tool() -> None:
    clf = _FakeClassifier(_intent(wants_tool=True))
    decision = classify_and_decide("find gyms open now near me", "user-1", clf)
    assert decision.blocked is False
    assert decision.source == "classifier"
    assert decision.wants_tool is True


def test_classifier_off_scope_intent_blocks_with_safe_reply() -> None:
    clf = _FakeClassifier(
        _intent(label="off_topic", in_scope=False, confidence=0.97, reason="unrelated")
    )
    # Not caught by the deterministic regex rules, so the classifier decides.
    decision = classify_and_decide("what's the capital of France", "user-1", clf)
    assert decision.blocked is True
    assert decision.category == "off_topic"
    assert decision.response  # a fixed safe reply
    assert decision.source == "classifier"


def test_classifier_unavailable_falls_back_to_allow() -> None:
    clf = _FakeClassifier(None)  # provider failure / malformed output
    decision = classify_and_decide("what's a good split", "user-1", clf)
    assert decision.blocked is False
    assert decision.source == "fallback"


def test_low_confidence_falls_back_to_allow() -> None:
    clf = _FakeClassifier(_intent(label="off_topic", in_scope=False, confidence=0.3))
    decision = classify_and_decide("hmm maybe something", "user-1", clf)
    assert decision.blocked is False
    assert decision.source == "fallback"


def test_fitness_label_with_in_scope_false_is_fail_closed() -> None:
    """A contradictory output (fitness label but not in scope) must block."""
    clf = _FakeClassifier(_intent(label="fitness", in_scope=False, confidence=0.99))
    decision = classify_and_decide("how do I structure a strength block", "user-1", clf)
    assert decision.blocked is True
    assert decision.category == "fitness"


def test_same_message_is_cached_after_a_real_decision() -> None:
    clf = _FakeClassifier(_intent())
    first = classify_and_decide("how much protein do i need", "user-1", clf)
    second = classify_and_decide("how much protein do i need", "user-1", clf)
    assert first.source == "classifier"
    assert second is first  # same cached decision object
    assert len(clf.calls) == 1  # only one classifier call


def test_fallback_decisions_are_not_cached() -> None:
    clf = _FakeClassifier(None)
    classify_and_decide("what split should i run", "user-2", clf)
    classify_and_decide("what split should i run", "user-2", clf)
    assert len(clf.calls) == 2  # fallback is never cached


def test_cache_is_scoped_per_user() -> None:
    clf = _FakeClassifier(_intent())
    classify_and_decide("same message", "user-a", clf)
    classify_and_decide("same message", "user-b", clf)
    assert len(clf.calls) == 2  # different users do not share a cache entry


# ---------------------------------------------------------------------------
# Integration through the real /chat route
# ---------------------------------------------------------------------------


class _RecordingPrimaryLLM:
    """Stand-in for the primary assistant that records whether it was called."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.calls.append(user)
        return '{"facts":[]}'

    def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
        self.calls.append(str(messages))
        return "A good protein target is roughly 1.6-2.2 g per kg of bodyweight."


class _BoomVectorStore:
    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("chroma disabled in this test")


@pytest.fixture
def wired(client: TestClient, monkeypatch) -> tuple[TestClient, _RecordingPrimaryLLM]:
    """Authenticated client with a fake primary LLM and an injected classifier."""
    primary = _RecordingPrimaryLLM()
    monkeypatch.setattr(
        chat_service_module.ChatService, "_build_llm", staticmethod(lambda: primary)
    )
    monkeypatch.setattr(chat_service_module, "VectorStore", _BoomVectorStore)
    # Default to an in-scope fitness classifier; individual tests override.
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "_build_classifier",
        lambda self: _FakeClassifier(_intent()),
    )
    return client, primary


def test_classifier_blocks_off_scope_message_regex_misses(wired, monkeypatch) -> None:
    client, primary = wired
    # This message is NOT caught by the deterministic regex rules, so only the
    # classifier can block it. Pretend it returns code_request.
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "_build_classifier",
        lambda self: _FakeClassifier(
            _intent(label="code_request", in_scope=False, confidence=0.93, reason="asks for code")
        ),
    )
    resp = client.post("/api/v1/chat", json={"message": "write me a haiku about squats"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The refusal is the fixed safe reply for code_request, and the model never ran.
    from app.safety import get_safe_reply

    assert body["response"] == get_safe_reply("code_request")
    assert primary.calls == []
    assert body["sources"] == []


def test_in_scope_message_reaches_the_model(wired) -> None:
    client, primary = wired
    resp = client.post(
        "/api/v1/chat", json={"message": "What's a good protein intake for muscle gain?"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "protein" in body["response"].lower()
    assert primary.calls  # the model produced the answer


def test_monitor_mode_logs_but_does_not_block(wired, monkeypatch) -> None:
    client, primary = wired
    monkeypatch.setattr(settings, "guardrails_mode", "monitor")
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "_build_classifier",
        lambda self: _FakeClassifier(
            _intent(label="off_topic", in_scope=False, confidence=0.97, reason="unrelated")
        ),
    )
    resp = client.post("/api/v1/chat", json={"message": "tell me about the weather"})
    assert resp.status_code == 200, resp.text
    # Monitor mode: the classifier flagged it, but the message still reached the
    # model (parity with the existing log-only behaviour).
    assert primary.calls


def test_guard_decision_dataclass_defaults() -> None:
    d = GuardDecision()
    assert d.blocked is False
    assert d.source == "deterministic"
    assert d.wants_tool is True


def test_clear_decision_cache_is_safe_when_empty() -> None:
    clear_decision_cache()
    clear_decision_cache()
