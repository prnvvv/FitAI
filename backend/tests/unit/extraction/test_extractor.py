"""Unit tests for the dedicated structured extractor."""

from __future__ import annotations

import pytest

from app.extraction.extractor import GroqActivityExtractor, _validate_result
from app.extraction.schemas import ExtractionResult


def _extractor(response: str | None = None, *, raises: bool = False) -> GroqActivityExtractor:
    class _LLM:
        def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
            assert json_mode is True  # extraction is always structured JSON
            if raises:
                raise RuntimeError("provider down")
            return response or "{}"

    return GroqActivityExtractor(api_key="unused", model="unused", llm=_LLM())


def test_extract_parses_completed_workout_and_preference() -> None:
    payload = (
        '{"completed_workouts":[{"activity":"cycling","duration_minutes":120,'
        '"performed_on":null,"confidence":0.95,"source_text":"I did cycling for 2 hours"}],'
        '"user_preferences":[{"preference":"enjoys cycling","confidence":0.9,'
        '"source_text":"I love it"}]}'
    )
    result = _extractor(payload).extract("I did cycling today and I love it. 2 hours.")
    assert result.error is None
    assert len(result.completed_workouts) == 1
    assert result.completed_workouts[0].duration_minutes == 120
    assert result.user_preferences[0].preference == "enjoys cycling"
    assert result.has_any()


def test_extract_provider_failure_reports_error_not_success() -> None:
    result = _extractor(raises=True).extract("I did cycling.")
    assert result.error is not None
    assert not result.has_any()


def test_extract_malformed_json_reports_error() -> None:
    result = _extractor("not json").extract("hello")
    assert result.error is not None
    assert not result.has_any()


def test_invalid_measurement_candidate_is_rejected_not_stored() -> None:
    result = _validate_result(
        {"progress_records": [{"measurement_type": "weight", "value": 99999, "unit": "kg"}]}
    )
    assert result.progress_records == []
    assert result.rejected  # out-of-range value is dropped


def test_unknown_measurement_type_is_rejected() -> None:
    result = _validate_result(
        {"progress_records": [{"measurement_type": "nonsense", "value": 70, "unit": "kg"}]}
    )
    assert result.progress_records == []
    assert result.rejected


def test_valid_progress_record_is_stored() -> None:
    result = _validate_result(
        {"progress_records": [{"measurement_type": "weight", "value": 72, "unit": "kg"}]}
    )
    assert len(result.progress_records) == 1
    assert result.progress_records[0].value == 72


def test_empty_result_has_nothing() -> None:
    result = _extractor('{"completed_workouts":[],"planned_workouts":[]}').extract("just chatting")
    assert not result.has_any()
    assert result.error is None


def test_null_arrays_are_tolerated() -> None:
    result = _validate_result({"completed_workouts": None, "user_preferences": None})
    assert result.completed_workouts == []
    assert result.user_preferences == []


def test_extraction_result_default_is_empty() -> None:
    assert ExtractionResult().has_any() is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
