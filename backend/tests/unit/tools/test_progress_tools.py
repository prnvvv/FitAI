"""Tests for progress analysis tools."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.tools.progress_tools import DatedValue, GoalEntry, analyze_trend, make_progress_tools


def _config(uid: str = "user-1") -> RunnableConfig:
    return {"configurable": {"user_id": uid}}


def test_analyze_trend_insufficient_data() -> None:
    points = [DatedValue(on=date(2026, 1, 1), value=70)]
    result = analyze_trend(points, flat_threshold_per_week=0.1)
    assert result["status"] == "insufficient_data"


def test_analyze_trend_decreasing() -> None:
    points = [
        DatedValue(on=date(2026, 1, 1), value=75),
        DatedValue(on=date(2026, 1, 8), value=74),
        DatedValue(on=date(2026, 1, 15), value=73),
    ]
    result = analyze_trend(points, flat_threshold_per_week=0.1)
    assert result["status"] == "ok"
    assert result["direction"] == "decreasing"
    assert result["slope_per_week"] < 0


def test_weight_trend_tool(fake_progress_service: Any, fake_workout_service: Any) -> None:
    fake_progress_service.weights = [
        DatedValue(on=date(2026, 1, 1), value=75),
        DatedValue(on=date(2026, 1, 15), value=73),
    ]
    tools = make_progress_tools(
        fake_progress_service, fake_workout_service, today=lambda: date(2026, 1, 15)
    )
    weight_tool = tools[0]
    result = weight_tool.invoke({"days": 30}, config=_config())
    assert result["window_days"] == 30
    assert result["unit"] == "kg"


def test_goal_progress_tool_no_goals(fake_progress_service: Any, fake_workout_service: Any) -> None:
    tools = make_progress_tools(
        fake_progress_service, fake_workout_service, today=lambda: date(2026, 1, 15)
    )
    goal_tool = tools[3]
    result = goal_tool.invoke({}, config=_config())
    assert result["status"] == "no_data"


def test_goal_progress_tool_numeric_weight_goal(
    fake_progress_service: Any, fake_workout_service: Any
) -> None:
    fake_progress_service.goals = [
        GoalEntry(on=date(2026, 1, 1), goal="lose weight", metric="weight", target_value=70),
    ]
    fake_progress_service.weights = [
        DatedValue(on=date(2026, 1, 1), value=75),
        DatedValue(on=date(2026, 1, 15), value=73),
    ]
    tools = make_progress_tools(
        fake_progress_service, fake_workout_service, today=lambda: date(2026, 1, 15)
    )
    goal_tool = tools[3]
    result = goal_tool.invoke({}, config=_config())
    assert result["status"] == "ok"
    assert result["progress_pct"] is not None
    assert result["remaining"] == -3
