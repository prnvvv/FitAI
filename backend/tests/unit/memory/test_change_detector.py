"""Tests for memory change detection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.memory.change_detector import (
    ChangeKind,
    MemoryEntry,
    detect_changes,
)
from app.memory.extractor import ExtractedFact, StatementType, Tense

_FactField = Literal["weight", "height", "body_fat", "goal", "workout", "supplement", "measurement"]


def _fact(field: _FactField, value: float | str, unit: str | None = None,
          tense: Tense = Tense.PRESENT, statement_type: StatementType = StatementType.EXPLICIT,
          source_text: str = "fact", qualifier: str | None = None,
          timestamp: datetime | None = None) -> ExtractedFact:
    return ExtractedFact(
        field=field, qualifier=qualifier, value=value, unit=unit,
        confidence=0.9, timestamp=timestamp, extracted_at=datetime.now(timezone.utc),
        tense=tense, statement_type=statement_type, source_text=source_text,
    )


def _entry(key: str, value: float | str | list[str], unit: str | None = None) -> MemoryEntry:
    return MemoryEntry(key=key, value=value, unit=unit)


def test_detect_changes_new_value() -> None:
    fact = _fact("weight", 70, "kg")
    memory: dict[str, MemoryEntry] = {}
    result = detect_changes([fact], memory)
    assert len(result) == 1
    assert result[0].kind is ChangeKind.NEW


def test_detect_changes_unchanged_within_tolerance() -> None:
    fact = _fact("weight", 70.05, "kg")
    memory = {"weight": _entry("weight", 70, "kg")}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.UNCHANGED


def test_detect_changes_changed_value() -> None:
    fact = _fact("weight", 75, "kg")
    memory: dict[str, MemoryEntry] = {"weight": _entry("weight", 70, "kg")}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.CHANGED


def test_detect_changes_historical_event() -> None:
    fact = _fact("weight", 80, "kg", tense=Tense.PAST,
                 statement_type=StatementType.HISTORICAL, source_text="I weighed 80 kg")
    memory: dict[str, MemoryEntry] = {}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.HISTORICAL_EVENT


def test_detect_changes_hypothetical_ignored() -> None:
    fact = _fact("weight", 60, "kg", statement_type=StatementType.HYPOTHETICAL,
                 source_text="What if I weighed 60 kg?")
    memory: dict[str, MemoryEntry] = {}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.NOT_CURRENT


def test_detect_changes_contradiction_implausible() -> None:
    fact = _fact("weight", 200, "kg")
    memory: dict[str, MemoryEntry] = {"weight": _entry("weight", 70, "kg")}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.CONTRADICTION


def test_detect_changes_supplement_set() -> None:
    fact = _fact("supplement", "creatine", source_text="I take creatine")
    memory: dict[str, MemoryEntry] = {"supplement": _entry("supplement", ["creatine", "whey"])}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.UNCHANGED


def test_detect_changes_supplement_new() -> None:
    fact = _fact("supplement", "caffeine", source_text="I take caffeine")
    memory: dict[str, MemoryEntry] = {"supplement": _entry("supplement", ["creatine"])}
    result = detect_changes([fact], memory)
    assert result[0].kind is ChangeKind.NEW


def test_detect_changes_conflicting_batch() -> None:
    f1 = _fact("weight", 70, "kg")
    f2 = _fact("weight", 75, "kg")
    memory: dict[str, MemoryEntry] = {}
    result = detect_changes([f1, f2], memory)
    assert all(r.kind is ChangeKind.CONTRADICTION for r in result)
