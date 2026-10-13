"""Tests for confirmation decisions and execution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.memory.change_detector import ChangeKind, DetectedChange
from app.memory.confirmation import (
    Action,
    apply_decisions,
    decide,
    decide_all,
)
from app.memory.extractor import ExtractedFact, StatementType, Tense

_FactField = Literal["weight", "height", "body_fat", "goal", "workout", "supplement", "measurement"]


def _change(kind: ChangeKind, field: _FactField = "weight", value: float = 70,
            statement_type: StatementType = StatementType.EXPLICIT,
            tense: Tense = Tense.PRESENT, confidence: float = 0.9,
            timestamp: datetime | None = None) -> DetectedChange:
    fact = ExtractedFact(
        field=field, value=value, unit="kg" if field == "weight" else None,
        confidence=confidence, timestamp=timestamp, extracted_at=datetime.now(timezone.utc),
        tense=tense, statement_type=statement_type,
        source_text="test",
    )
    return DetectedChange(fact=fact, kind=kind)


def test_decide_skips_unchanged() -> None:
    decision = decide(_change(ChangeKind.UNCHANGED))
    assert decision.action is Action.SKIP


def test_decide_skips_not_current() -> None:
    decision = decide(_change(ChangeKind.NOT_CURRENT))
    assert decision.action is Action.SKIP


def test_decide_contradiction_becomes_pending() -> None:
    decision = decide(_change(ChangeKind.CONTRADICTION))
    assert decision.action is Action.CREATE_PENDING


def test_decide_auto_applies_high_confidence_current() -> None:
    decision = decide(_change(ChangeKind.NEW, confidence=0.9))
    assert decision.action is Action.AUTO_APPLY


def test_decide_low_confidence_becomes_pending() -> None:
    decision = decide(_change(ChangeKind.NEW, confidence=0.5))
    assert decision.action is Action.CREATE_PENDING


def test_decide_historical_with_date_records_history() -> None:
    from datetime import datetime, timezone
    ts = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    decision = decide(_change(ChangeKind.HISTORICAL_EVENT, tense=Tense.PAST,
                              statement_type=StatementType.HISTORICAL, value=80,
                              timestamp=ts))
    assert decision.action is Action.RECORD_HISTORY


def test_decide_historical_without_date_becomes_pending() -> None:
    from app.memory.history import build_history_record
    change = _change(ChangeKind.HISTORICAL_EVENT, tense=Tense.PAST,
                     statement_type=StatementType.HISTORICAL)
    assert build_history_record(change.fact) is None
    decision = decide(change)
    assert decision.action is Action.CREATE_PENDING


def test_decide_all_returns_one_per_change() -> None:
    changes = [_change(ChangeKind.NEW), _change(ChangeKind.UNCHANGED)]
    decisions = decide_all(changes)
    assert len(decisions) == 2


def test_apply_decisions_calls_writer(fake_memory_writer: Any) -> None:
    change = _change(ChangeKind.NEW)
    decision = decide(change)
    results = apply_decisions("user-1", [decision], fake_memory_writer)
    assert len(results) == 1
    assert results[0].status == "applied"
    assert len(fake_memory_writer.updates) == 1
    assert len(fake_memory_writer.history) == 1


def test_apply_decisions_pending(fake_memory_writer: Any) -> None:
    change = _change(ChangeKind.CONTRADICTION)
    decision = decide(change)
    results = apply_decisions("user-1", [decision], fake_memory_writer)
    assert results[0].status == "pending_created"
    assert results[0].proposal_id == "pending-1"


def test_apply_decisions_history(fake_memory_writer: Any) -> None:
    from datetime import datetime, timezone
    ts = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    change = _change(ChangeKind.HISTORICAL_EVENT, tense=Tense.PAST,
                     statement_type=StatementType.HISTORICAL, value=80, timestamp=ts)
    decision = decide(change)
    results = apply_decisions("user-1", [decision], fake_memory_writer)
    assert results[0].status == "history_recorded"


def test_apply_decisions_skip_not_passed_to_writer(fake_memory_writer: Any) -> None:
    change = _change(ChangeKind.UNCHANGED)
    decision = decide(change)
    results = apply_decisions("user-1", [decision], fake_memory_writer)
    assert results[0].status == "skipped"
    assert len(fake_memory_writer.updates) == 0


def test_apply_decisions_failed_when_writer_returns_false(fake_memory_writer: Any) -> None:
    fake_memory_writer.succeed = False
    change = _change(ChangeKind.NEW)
    decision = decide(change)
    results = apply_decisions("user-1", [decision], fake_memory_writer)
    assert results[0].status == "failed"
