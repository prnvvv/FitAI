"""Tests for LangGraph routing."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.graph import (
    route_after_detect,
    route_after_extract,
    route_after_safety,
    route_after_updates,
)
from app.agent.state import AgentState
from app.memory.confirmation import Action, Decision
from app.memory.extractor import ExtractedFact, StatementType, Tense
from app.safety import SafetyResult


def _fact() -> ExtractedFact:
    return ExtractedFact(
        field="weight",
        value=70,
        unit="kg",
        confidence=0.9,
        extracted_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        tense=Tense.PRESENT,
        statement_type=StatementType.EXPLICIT,
        source_text="I weigh 70 kg",
    )


def test_route_after_safety_blocked() -> None:
    state: AgentState = {"safety": SafetyResult(blocked=True)}
    assert route_after_safety(state) == "safe_response"


def test_route_after_safety_personal() -> None:
    state: AgentState = {"safety": SafetyResult(), "user_message": "I weigh 70 kg"}
    assert route_after_safety(state) == "extract_facts"


def test_route_after_safety_question() -> None:
    state: AgentState = {"safety": SafetyResult(), "user_message": "How much protein?"}
    assert route_after_safety(state) == "retrieve_context"


def test_route_after_safety_otherwise() -> None:
    state: AgentState = {"safety": SafetyResult(), "user_message": "Hello"}
    assert route_after_safety(state) == "generate_response"


def test_route_after_extract_with_facts() -> None:
    state: AgentState = {"extracted_facts": [_fact()]}
    assert route_after_extract(state) == "detect_changes"


def test_route_after_extract_without_facts() -> None:
    state: AgentState = {"extracted_facts": [], "user_message": "How much protein?"}
    assert route_after_extract(state) == "retrieve_context"


def test_route_after_detect_with_actionable_updates() -> None:
    from app.memory.change_detector import ChangeKind, DetectedChange

    decision = Decision(
        change=DetectedChange(fact=_fact(), kind=ChangeKind.NEW),
        action=Action.AUTO_APPLY,
        reason="test",
    )
    state: AgentState = {"proposed_updates": [decision], "user_message": "Hello"}
    assert route_after_detect(state) == "apply_updates"


def test_route_after_detect_only_skips() -> None:
    from app.memory.change_detector import ChangeKind, DetectedChange

    decision = Decision(
        change=DetectedChange(fact=_fact(), kind=ChangeKind.UNCHANGED),
        action=Action.SKIP,
        reason="test",
    )
    state: AgentState = {"proposed_updates": [decision], "user_message": "Hello"}
    assert route_after_detect(state) == "generate_response"


def test_route_after_updates_question() -> None:
    state: AgentState = {"user_message": "How much protein?"}
    assert route_after_updates(state) == "retrieve_context"


def test_route_after_updates_statement() -> None:
    state: AgentState = {"user_message": "I weigh 70 kg"}
    assert route_after_updates(state) == "generate_response"
