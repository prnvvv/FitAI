"""Tests for workout tools."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from app.tools.workout_tools import (
    ExerciseEntry,
    SetEntry,
    WorkoutLog,
    analyze_personal_records,
    estimate_1rm,
    make_workout_tools,
    summarize_workouts,
)


def _config(uid: str = "user-1") -> RunnableConfig:
    return {"configurable": {"user_id": uid}}


def test_estimate_1rm_epley() -> None:
    assert estimate_1rm(100, 5) == pytest.approx(116.67, 0.01)
    assert estimate_1rm(100, 1) == 100
    assert estimate_1rm(100, 13) is None


def test_summarize_workouts_empty() -> None:
    result = summarize_workouts([])
    assert result["status"] == "no_data"


def test_summarize_workouts_totals() -> None:
    workout = WorkoutLog(
        performed_on=date(2026, 1, 10),
        exercises=[ExerciseEntry(name="Squat", sets=[SetEntry(reps=5, weight_kg=100)])],
        duration_min=30,
    )
    result = summarize_workouts([workout])
    assert result["status"] == "ok"
    assert result["total_sets"] == 1
    assert result["total_volume_kg"] == 500


def test_analyze_personal_records() -> None:
    w1 = WorkoutLog(
        performed_on=date(2026, 1, 1),
        exercises=[ExerciseEntry(name="Bench", sets=[SetEntry(reps=5, weight_kg=80)])],
    )
    w2 = WorkoutLog(
        performed_on=date(2026, 1, 8),
        exercises=[ExerciseEntry(name="Bench", sets=[SetEntry(reps=3, weight_kg=85)])],
    )
    result = analyze_personal_records([w1, w2], exercise="Bench")
    assert result["status"] == "ok"
    bench = result["records"][0]
    assert bench["max_weight_kg"] == 85


def test_require_user_id_raises_when_missing() -> None:
    from app.tools.calculations import ToolInputError
    from app.tools.workout_tools import require_user_id
    with pytest.raises(ToolInputError, match="no authenticated user"):
        require_user_id({})


def test_require_user_id_returns_uid() -> None:
    from app.tools.workout_tools import require_user_id
    uid = require_user_id(_config())
    assert uid == "user-1"


def test_workout_summary_tool(fake_workout_service: Any) -> None:
    tools = make_workout_tools(fake_workout_service, today=lambda: date(2026, 1, 15))
    summary_tool = tools[1]
    result = summary_tool.invoke({"days": 30}, config=_config())
    assert result["window_days"] == 30
