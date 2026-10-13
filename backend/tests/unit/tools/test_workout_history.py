"""Tests for the read-only workout-history tool."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.tools.calculations import ToolInputError
from app.tools.workout_history import (
    MAX_SESSIONS,
    build_workout_history,
    format_workout_history,
    resolve_range,
)
from app.tools.workout_tools import ExerciseEntry, SetEntry, WorkoutLog


class _FakeHistoryService:
    def __init__(self, workouts: list[WorkoutLog] | None = None) -> None:
        self.workouts = workouts or []
        self.calls: list[tuple[str, date, date]] = []

    def get_workouts(self, user_id: str, start: date, end: date) -> list[WorkoutLog]:
        self.calls.append((user_id, start, end))
        return [w for w in self.workouts if start <= w.performed_on <= end]


def _log(day: date, name: str = "Bench Press", reps: int = 5, kg: float = 80) -> WorkoutLog:
    return WorkoutLog(
        performed_on=day,
        name="Push day",
        duration_min=45,
        exercises=[ExerciseEntry(name=name, sets=[SetEntry(reps=reps, weight_kg=kg)])],
    )


def test_resolve_range_defaults_to_window() -> None:
    today = date(2026, 1, 15)
    start, end = resolve_range({}, today)
    assert end == today
    assert start == today - timedelta(days=89)


def test_resolve_range_explicit_dates() -> None:
    start, end = resolve_range({"start": "2026-01-13", "end": "2026-01-14"}, date(2026, 2, 1))
    assert start == date(2026, 1, 13)
    assert end == date(2026, 1, 14)


def test_resolve_range_single_start_means_one_day() -> None:
    start, end = resolve_range({"start": "2026-01-13"}, date(2026, 2, 1))
    assert start == date(2026, 1, 13)
    assert end == date(2026, 1, 13)


def test_resolve_range_rejects_inverted_range() -> None:
    with pytest.raises(ToolInputError):
        resolve_range({"start": "2026-01-20", "end": "2026-01-13"}, date(2026, 2, 1))


def test_resolve_range_rejects_bad_date() -> None:
    with pytest.raises(ToolInputError):
        resolve_range({"start": "13th"}, date(2026, 2, 1))


def test_resolve_range_rejects_out_of_bounds_days() -> None:
    with pytest.raises(ToolInputError):
        resolve_range({"days": 400}, date(2026, 2, 1))


def test_format_workout_history_no_data() -> None:
    result = format_workout_history([], start=date(2026, 1, 1), end=date(2026, 1, 2))
    assert result["status"] == "no_data"
    assert result["sessions"] == []


def test_format_workout_history_lists_exercises() -> None:
    result = format_workout_history(
        [_log(date(2026, 1, 13))], start=date(2026, 1, 13), end=date(2026, 1, 13)
    )
    assert result["status"] == "ok"
    assert result["session_count"] == 1
    session = result["sessions"][0]
    assert session["date"] == "2026-01-13"
    assert session["exercises"][0]["exercise"] == "Bench Press"
    assert session["exercises"][0]["sets"] == [{"reps": 5, "weight_kg": 80.0}]


def test_format_workout_history_truncates() -> None:
    logs = [_log(date(2026, 1, 1) + timedelta(days=i)) for i in range(MAX_SESSIONS + 5)]
    result = format_workout_history(logs, start=date(2026, 1, 1), end=date(2026, 12, 31))
    assert result["truncated"] is True
    assert len(result["sessions"]) == MAX_SESSIONS


def test_build_workout_history_filters_by_range() -> None:
    service = _FakeHistoryService([_log(date(2026, 1, 13)), _log(date(2026, 2, 2), name="Squat")])
    result = build_workout_history(
        service, "user-1", {"start": "2026-01-13"}, today=lambda: date(2026, 3, 1)
    )
    assert result["session_count"] == 1
    assert service.calls == [("user-1", date(2026, 1, 13), date(2026, 1, 13))]


def test_build_workout_history_passes_window() -> None:
    service = _FakeHistoryService()
    build_workout_history(service, "user-1", {"days": 7}, today=lambda: date(2026, 1, 15))
    assert service.calls == [("user-1", date(2026, 1, 9), date(2026, 1, 15))]
