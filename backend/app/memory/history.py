"""Build dated, append-only history records. Never invents dates; never writes."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .change_detector import ChangeKind, DetectedChange
from .extractor import ExtractedFact, StatementType, Tense

HistoryCategory = Literal["weight", "goal", "workout", "measurement", "supplement"]
_CATEGORY: dict[str, HistoryCategory] = {
    "weight": "weight",
    "goal": "goal",
    "workout": "workout",
    "supplement": "supplement",
    "height": "measurement",
    "body_fat": "measurement",
    "measurement": "measurement",
}
_RECORDABLE = {ChangeKind.NEW, ChangeKind.CHANGED, ChangeKind.HISTORICAL_EVENT}


class HistoryRecord(BaseModel):
    """Append-only record for the persistence service to insert."""

    category: HistoryCategory
    key: str
    value: float | str
    unit: str | None = None
    effective_date: date  # when the fact held, from user text or message time
    recorded_at: datetime  # when we captured it
    confidence: float
    source_text: str


class HistoryPlan(BaseModel):
    records: list[HistoryRecord] = Field(default_factory=list)
    missing_date: list[DetectedChange] = Field(default_factory=list)  # ask the user for a date


def build_history_record(fact: ExtractedFact) -> HistoryRecord | None:
    """Return a record, or None when no honest date exists.

    Date = stated timestamp; else the message date for a present-tense statement
    (the user said it now). Past statements and workouts without a stated date
    return None; hypothetical/future (non-goal) statements never produce history.
    """
    if fact.statement_type is StatementType.HYPOTHETICAL:
        return None
    if fact.tense is Tense.FUTURE and fact.field != "goal":
        return None
    if fact.timestamp is not None:
        effective = fact.timestamp.astimezone(timezone.utc).date()
    elif (
        fact.tense is Tense.PRESENT
        and fact.field != "workout"
        or (fact.field == "goal" and fact.tense is Tense.FUTURE)
    ):
        effective = fact.extracted_at.astimezone(timezone.utc).date()
    else:
        return None
    return HistoryRecord(
        category=_CATEGORY[fact.field],
        key=fact.key,
        value=fact.value,
        unit=fact.unit,
        effective_date=effective,
        recorded_at=fact.extracted_at,
        confidence=fact.confidence,
        source_text=fact.source_text,
    )


def prepare_history(changes: list[DetectedChange]) -> HistoryPlan:
    """Split recordable changes into dated records and ones missing a date."""
    plan = HistoryPlan()
    for c in changes:
        if c.kind not in _RECORDABLE:
            continue
        rec = build_history_record(c.fact)
        if rec:
            plan.records.append(rec)
        else:
            plan.missing_date.append(c)
    return plan
