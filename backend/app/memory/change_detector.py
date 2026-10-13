"""Compare extracted facts with current memory. Pure logic, no I/O."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, field_validator

from .extractor import ExtractedFact, StatementType, Tense


class ChangeKind(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"  # current value differs from memory
    HISTORICAL_EVENT = "historical_event"  # past/event; never a current update
    CONTRADICTION = "contradiction"  # conflicts in a way that needs the user
    NOT_CURRENT = "not_current"  # hypothetical/future/other: ignore


class MemoryEntry(BaseModel):
    """Current value held by the profile service (numeric values in canonical units)."""

    key: str
    value: float | str | list[str]
    unit: str | None = None
    updated_at: datetime | None = None

    @field_validator("updated_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v


class DetectedChange(BaseModel):
    fact: ExtractedFact
    kind: ChangeKind
    previous: MemoryEntry | None = None
    reason: str = ""


_TOL = {"weight": 0.1, "height": 0.5, "body_fat": 0.2, "measurement": 0.5}
_MAX_REL = {"weight": 0.10, "height": 0.02, "measurement": 0.15}
_MAX_ABS_BODY_FAT = 5.0
_MULTI_VALUED = {"supplement"}


def _implausible(field: str, old: float, new: float) -> bool:
    if field == "body_fat":
        return abs(new - old) > _MAX_ABS_BODY_FAT
    return old > 0 and abs(new - old) / old > _MAX_REL[field]


def _same(field: str, a: float | str, b: float | str) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    return abs(a - b) <= _TOL.get(field, 0.0)


def _classify(f: ExtractedFact, prev: MemoryEntry | None) -> DetectedChange:
    def out(kind: ChangeKind, reason: str) -> DetectedChange:
        return DetectedChange(fact=f, kind=kind, previous=prev, reason=reason)

    if f.statement_type is StatementType.HYPOTHETICAL:
        return out(ChangeKind.NOT_CURRENT, "hypothetical statement")
    if (
        f.tense is Tense.PAST
        or f.statement_type is StatementType.HISTORICAL
        or f.field == "workout"
    ):
        return out(ChangeKind.HISTORICAL_EVENT, "past event or workout log; not a current value")
    if not (f.tense is Tense.PRESENT or (f.field == "goal" and f.tense is Tense.FUTURE)):
        return out(ChangeKind.NOT_CURRENT, "not a current-state statement")
    if prev is None:
        return out(ChangeKind.NEW, "no existing value")

    if f.field in _MULTI_VALUED:
        known = {
            s.lower() for s in (prev.value if isinstance(prev.value, list) else [str(prev.value)])
        }
        return out(
            ChangeKind.UNCHANGED if str(f.value).lower() in known else ChangeKind.NEW,
            "supplement set comparison",
        )
    if f.field == "goal":
        same = _same("goal", f.value, str(prev.value))
        return out(ChangeKind.UNCHANGED if same else ChangeKind.CHANGED, "goal text comparison")

    # numeric single-valued fields
    if isinstance(prev.value, str | list):
        return out(ChangeKind.CONTRADICTION, "stored value is not numeric")
    if prev.unit and prev.unit != f.unit:
        return out(ChangeKind.CONTRADICTION, f"unit mismatch: stored {prev.unit}, new {f.unit}")
    if _same(f.field, f.value, prev.value):
        return out(ChangeKind.UNCHANGED, "within tolerance of stored value")
    if f.timestamp and prev.updated_at and f.timestamp < prev.updated_at:
        return out(ChangeKind.CONTRADICTION, "statement is older than the stored value")
    if _implausible(f.field, float(prev.value), float(f.value)):
        return out(
            ChangeKind.CONTRADICTION, "change too large to be plausible without confirmation"
        )
    return out(ChangeKind.CHANGED, "value differs from stored value")


def detect_changes(
    facts: list[ExtractedFact], memory: Mapping[str, MemoryEntry]
) -> list[DetectedChange]:
    """Classify each fact against current memory (keyed by `ExtractedFact.key`)."""
    results = [_classify(f, memory.get(f.key)) for f in facts]

    # conflicting current statements for the same single-valued key in one batch
    groups: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(results):
        if (
            c.kind in (ChangeKind.NEW, ChangeKind.CHANGED, ChangeKind.UNCHANGED)
            and c.fact.field not in _MULTI_VALUED
        ):
            groups[c.fact.key].append(i)
    for idxs in (g for g in groups.values() if len(g) > 1):
        first = results[idxs[0]].fact
        if not all(_same(first.field, first.value, results[i].fact.value) for i in idxs[1:]):
            for i in idxs:
                results[i] = DetectedChange(
                    fact=results[i].fact,
                    kind=ChangeKind.CONTRADICTION,
                    previous=results[i].previous,
                    reason="conflicting statements in the same message",
                )
    return results
