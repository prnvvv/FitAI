"""Guardrails must not hide the user's own memory.

Live verification showed a legitimate question ("What do I like to do every
day?") being scope-blocked as ``off_topic``, which silently denied cross-chat
recall. These tests pin the deterministic override and prove safety labels are
still enforced.
"""

from __future__ import annotations

from app.guardrails.classifier import Intent
from app.guardrails.guard import classify_and_decide, clear_decision_cache


class _Classifier:
    """Returns a fixed verdict (or None to simulate a provider failure)."""

    def __init__(self, intent: Intent | None) -> None:
        self._intent = intent

    def classify(self, message: str) -> Intent | None:
        return self._intent


def _off_topic() -> Intent:
    return Intent(
        label="off_topic",
        in_scope=False,
        wants_tool=False,
        confidence=0.95,
        reason="no fitness keywords",
    )


def test_own_preference_question_is_not_scope_blocked() -> None:
    clear_decision_cache()
    decision = classify_and_decide(
        "What do I like to do every day?", "u1", _Classifier(_off_topic())
    )
    assert decision.blocked is False
    assert decision.wants_tool is False


def test_own_history_question_is_not_scope_blocked() -> None:
    clear_decision_cache()
    decision = classify_and_decide("What was my previous routine?", "u1", _Classifier(_off_topic()))
    assert decision.blocked is False


def test_genuine_off_topic_question_is_still_blocked() -> None:
    clear_decision_cache()
    decision = classify_and_decide("Who won the world cup?", "u1", _Classifier(_off_topic()))
    assert decision.blocked is True
    assert decision.category == "off_topic"


def test_safety_label_is_never_overridden_by_the_own_data_rule() -> None:
    clear_decision_cache()
    intent = Intent(
        label="unsafe_training",
        in_scope=False,
        wants_tool=False,
        confidence=0.97,
        reason="injury ignored",
    )
    decision = classify_and_decide(
        "What do I like to do every day when my knee hurts?", "u1", _Classifier(intent)
    )
    assert decision.blocked is True
    assert decision.category == "unsafe_training"


def test_classifier_failure_still_allows_chat() -> None:
    clear_decision_cache()
    decision = classify_and_decide("What do I like to do every day?", "u1", _Classifier(None))
    assert decision.blocked is False


def test_in_scope_classifier_verdict_is_unchanged() -> None:
    clear_decision_cache()
    intent = Intent(
        label="fitness", in_scope=True, wants_tool=True, confidence=0.9, reason="planning"
    )
    decision = classify_and_decide("plan my week of training", "u1", _Classifier(intent))
    assert decision.blocked is False
    assert decision.wants_tool is True
