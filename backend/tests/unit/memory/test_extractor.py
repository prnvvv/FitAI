"""Tests for structured fact extraction."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.memory.extractor import (
    ExtractedFact,
    ExtractionResult,
    StatementType,
    Tense,
    extract_facts,
)


def _fact_json(field: str, value: float | str, unit: str | None = None,
               tense: str = "present", statement_type: str = "explicit",
               source_text: str = "I weigh 70 kg", qualifier: str | None = None) -> str:
    import json
    return json.dumps({"facts": [{
        "field": field,
        "qualifier": qualifier,
        "value": value,
        "unit": unit,
        "confidence": 0.9,
        "timestamp": None,
        "tense": tense,
        "statement_type": statement_type,
        "source_text": source_text,
    }]})


def test_extract_facts_parses_weight(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = _fact_json("weight", 70, "kg")
    result = extract_facts("I weigh 70 kg", fake_llm, now)
    assert isinstance(result, ExtractionResult)
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.field == "weight"
    assert fact.value == 70.0
    assert fact.unit == "kg"
    assert fact.key == "weight"


def test_extract_facts_converts_lbs_to_kg(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = _fact_json("weight", 154, "lb")
    result = extract_facts("I weigh 154 lb", fake_llm, now)
    fact = result.facts[0]
    assert pytest.approx(fact.value, 0.01) == 69.85
    assert fact.unit == "kg"


def test_extract_facts_rejects_out_of_range(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = _fact_json("weight", 5000, "kg")
    result = extract_facts("I weigh 5000 kg", fake_llm, now)
    assert len(result.facts) == 0
    assert len(result.rejected) == 1


def test_extract_facts_handles_historical(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = _fact_json("weight", 80, "kg", tense="past",
                                    statement_type="historical", source_text="I weighed 80 kg last year")
    result = extract_facts("I weighed 80 kg last year", fake_llm, now)
    fact = result.facts[0]
    assert fact.tense is Tense.PAST
    assert fact.statement_type is StatementType.HISTORICAL


def test_extract_facts_downgrades_hypothetical(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = _fact_json("weight", 70, "kg", tense="future",
                                    statement_type="explicit", source_text="What if I weighed 70 kg?")
    result = extract_facts("What if I weighed 70 kg?", fake_llm, now)
    fact = result.facts[0]
    assert fact.statement_type is StatementType.HYPOTHETICAL


def test_extract_facts_returns_error_on_bad_json(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = "not json"
    result = extract_facts("hello", fake_llm, now)
    assert result.error is not None
    assert len(result.facts) == 0


def test_extract_facts_empty_list(fake_llm: Any, now: datetime) -> None:
    fake_llm.response = '{"facts":[]}'
    result = extract_facts("hello", fake_llm, now)
    assert len(result.facts) == 0
    assert result.error is None


def test_extracted_fact_key_with_qualifier(now: datetime) -> None:
    fact = ExtractedFact(
        field="measurement", qualifier="waist", value=80, unit="cm",
        confidence=0.9, extracted_at=now, tense=Tense.PRESENT,
        statement_type=StatementType.EXPLICIT, source_text="my waist is 80 cm"
    )
    assert fact.key == "measurement:waist"
