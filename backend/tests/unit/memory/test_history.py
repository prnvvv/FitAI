"""Tests for history record preparation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.memory.change_detector import ChangeKind, DetectedChange
from app.memory.extractor import ExtractedFact, StatementType, Tense
from app.memory.history import build_history_record, prepare_history

_FactField = Literal["weight", "height", "body_fat", "goal", "workout", "supplement", "measurement"]


def _fact(field: _FactField, value: float | str, tense: Tense = Tense.PRESENT,
          statement_type: StatementType = StatementType.EXPLICIT,
          timestamp: datetime | None = None, source_text: str = "test") -> ExtractedFact:
    return ExtractedFact(
        field=field, value=value,
        unit="kg" if field == "weight" else None,
        confidence=0.9, timestamp=timestamp,
        extracted_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        tense=tense, statement_type=statement_type, source_text=source_text,
    )


def test_build_history_record_present_statement_uses_extracted_date() -> None:
    fact = _fact("weight", 70)
    record = build_history_record(fact)
    assert record is not None
    assert record.category == "weight"
    assert record.value == 70.0
    assert record.effective_date == fact.extracted_at.date()


def test_build_history_record_stated_timestamp() -> None:
    ts = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    fact = _fact("weight", 70, timestamp=ts)
    record = build_history_record(fact)
    assert record is not None
    assert record.effective_date == ts.date()


def test_build_history_record_past_without_date_returns_none() -> None:
    fact = _fact("weight", 80, tense=Tense.PAST, statement_type=StatementType.HISTORICAL,
                 source_text="I weighed 80 kg before")
    assert build_history_record(fact) is None


def test_build_history_record_hypothetical_returns_none() -> None:
    fact = _fact("weight", 60, statement_type=StatementType.HYPOTHETICAL)
    assert build_history_record(fact) is None


def test_build_history_record_future_non_goal_returns_none() -> None:
    fact = _fact("weight", 60, tense=Tense.FUTURE, statement_type=StatementType.EXPLICIT)
    assert build_history_record(fact) is None


def test_build_history_record_goal_future_allowed() -> None:
    fact = _fact("goal", "lose 5 kg", tense=Tense.FUTURE, statement_type=StatementType.EXPLICIT)
    record = build_history_record(fact)
    assert record is not None
    assert record.category == "goal"


def test_prepare_history_splits_records_and_missing_dates() -> None:
    dated = _fact("weight", 70, timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc))
    missing = _fact("weight", 80, tense=Tense.PAST, statement_type=StatementType.HISTORICAL,
                    source_text="I weighed 80 kg before")
    changes = [
        DetectedChange(fact=dated, kind=ChangeKind.CHANGED),
        DetectedChange(fact=missing, kind=ChangeKind.HISTORICAL_EVENT),
    ]
    plan = prepare_history(changes)
    assert len(plan.records) == 1
    assert len(plan.missing_date) == 1
