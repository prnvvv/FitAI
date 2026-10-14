"""Tests for chat action proposal detection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agent.proposals import (
    build_action_proposals,
    extract_workout_log,
    looks_like_body_stats_query,
    looks_like_workout_log,
)
from app.memory.change_detector import MemoryEntry
from app.models.enums import PendingActionType

_NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


def _no_llm() -> Any:
    def _call(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("LLM should not be called")

    return _call


def test_looks_like_workout_log_detects_report() -> None:
    assert looks_like_workout_log("I did treadmill for 2h today") is True
    assert looks_like_workout_log("went for a run for 30 minutes") is True


def test_looks_like_workout_log_ignores_questions() -> None:
    assert looks_like_workout_log("What is protein?") is False


def test_looks_like_body_stats_query_requires_metric_and_question() -> None:
    assert looks_like_body_stats_query("What is my BMI?") is True
    assert looks_like_body_stats_query("How much should I eat according to my weight?") is True
    assert looks_like_body_stats_query("What is protein?") is False
    assert looks_like_body_stats_query("my weight is 70 kg") is False


def test_extract_workout_log_parses_llm_json(fake_llm: Any) -> None:
    fake_llm.response = (
        '{"is_workout": true, "activity": "Treadmill", "duration_minutes": 120,'
        ' "performed_on": "2026-10-14", "notes": null}'
    )
    proposal = extract_workout_log("I did treadmill for 2h today", fake_llm, _NOW.date())
    assert proposal is not None
    assert proposal.activity == "Treadmill"
    assert proposal.duration_minutes == 120
    assert proposal.performed_on.isoformat() == "2026-10-14"


def test_extract_workout_log_returns_none_when_not_workout(fake_llm: Any) -> None:
    fake_llm.response = '{"is_workout": false}'
    assert extract_workout_log("I did treadmill for 2h", fake_llm, _NOW.date()) is None


def test_extract_workout_log_survives_bad_json(fake_llm: Any) -> None:
    fake_llm.response = "not json"
    assert extract_workout_log("I did treadmill for 2h", fake_llm, _NOW.date()) is None


def test_build_action_proposals_for_workout_log(fake_llm: Any) -> None:
    fake_llm.response = (
        '{"is_workout": true, "activity": "Treadmill", "duration_minutes": 120,'
        ' "performed_on": "2026-10-14", "notes": null}'
    )
    proposals = build_action_proposals("I did treadmill for 2h today", {}, None, fake_llm, _NOW)
    assert len(proposals) == 1
    assert proposals[0].action_type is PendingActionType.LOG_WORKOUT
    assert proposals[0].payload["duration_minutes"] == 120
    assert "Treadmill" in proposals[0].summary


def test_build_action_proposals_uses_stored_measurements() -> None:
    memory = {
        "height": MemoryEntry(key="height", value=180.0, unit="cm"),
        "weight": MemoryEntry(key="weight", value=75.0, unit="kg"),
    }
    proposals = build_action_proposals("What is my BMI?", memory, None, _no_llm(), _NOW)
    assert len(proposals) == 1
    assert proposals[0].action_type is PendingActionType.USE_MEASUREMENTS
    assert proposals[0].payload["height_cm"] == 180.0
    assert proposals[0].payload["weight_kg"] == 75.0


def test_build_action_proposals_skips_measurements_without_stored_values() -> None:
    proposals = build_action_proposals("What is my BMI?", {}, None, _no_llm(), _NOW)
    assert proposals == []


def test_build_action_proposals_none_for_plain_message() -> None:
    proposals = build_action_proposals("What is protein?", {}, None, _no_llm(), _NOW)
    assert proposals == []
