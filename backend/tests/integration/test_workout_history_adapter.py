"""Integration tests for the workout-history adapter and date-range persistence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.user import User
from app.services.workout_service import WorkoutService
from app.tools.tool_definitions import ToolContext, build_legacy_executor
from app.tools.workout_adapter import WorkoutHistoryServiceAdapter


def _seed_user(db_session) -> User:
    user = User(id=uuid.uuid4(), email="workouts@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _create(db_session, user_id, performed_at, sets):
    WorkoutService(db_session).create_session(
        user_id, performed_at, name="Push day", duration_minutes=45, sets=sets
    )


def test_adapter_groups_sets_by_exercise_and_converts_units(db_session) -> None:
    user = _seed_user(db_session)
    _create(
        db_session,
        user.id,
        datetime(2026, 1, 13, 18, 0, tzinfo=timezone.utc),
        [
            {"exercise_name": "Bench Press", "reps": 5, "weight": 80, "weight_unit": "kg"},
            {"exercise_name": "Bench Press", "reps": 5, "weight": 82.5, "weight_unit": "kg"},
            {"exercise_name": "Row", "reps": 10, "weight": 100, "weight_unit": "lb"},
        ],
    )

    adapter = WorkoutHistoryServiceAdapter(db_session, str(user.id))
    logs = adapter.get_workouts(str(user.id), date(2026, 1, 13), date(2026, 1, 13))

    assert len(logs) == 1
    log = logs[0]
    assert log.performed_on == date(2026, 1, 13)
    assert log.duration_min == 45
    names = [ex.name for ex in log.exercises]
    assert names == ["Bench Press", "Row"]
    bench = log.exercises[0]
    assert [s.reps for s in bench.sets] == [5, 5]
    assert bench.sets[1].weight_kg == 82.5
    row = log.exercises[1]
    assert row.sets[0].weight_kg == pytest.approx(45.359, abs=0.01)


def test_adapter_excludes_sessions_outside_window(db_session) -> None:
    user = _seed_user(db_session)
    _create(
        db_session,
        user.id,
        datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        [{"exercise_name": "Squat", "reps": 5, "weight": 100, "weight_unit": "kg"}],
    )
    _create(
        db_session,
        user.id,
        datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        [{"exercise_name": "Squat", "reps": 5, "weight": 100, "weight_unit": "kg"}],
    )

    adapter = WorkoutHistoryServiceAdapter(db_session, str(user.id))
    logs = adapter.get_workouts(str(user.id), date(2026, 1, 13), date(2026, 1, 20))
    assert logs == []


def test_adapter_skips_sets_without_reps(db_session) -> None:
    user = _seed_user(db_session)
    _create(
        db_session,
        user.id,
        datetime(2026, 1, 13, 7, 0, tzinfo=timezone.utc),
        [{"exercise_name": "Treadmill", "duration_seconds": 600}],
    )
    adapter = WorkoutHistoryServiceAdapter(db_session, str(user.id))
    logs = adapter.get_workouts(str(user.id), date(2026, 1, 13), date(2026, 1, 13))
    assert logs == []


def test_adapter_is_scoped_to_user(db_session) -> None:
    owner = _seed_user(db_session)
    other = User(id=uuid.uuid4(), email="other@example.com")
    db_session.add(other)
    db_session.commit()
    _create(
        db_session,
        owner.id,
        datetime(2026, 1, 13, 7, 0, tzinfo=timezone.utc),
        [{"exercise_name": "Deadlift", "reps": 3, "weight": 140, "weight_unit": "kg"}],
    )
    adapter = WorkoutHistoryServiceAdapter(db_session, str(other.id))
    assert adapter.get_workouts(str(other.id), date(2026, 1, 1), date(2026, 1, 31)) == []


def test_legacy_executor_returns_history_for_specific_date(db_session) -> None:
    user = _seed_user(db_session)
    _create(
        db_session,
        user.id,
        datetime(2026, 1, 13, 18, 0, tzinfo=timezone.utc),
        [{"exercise_name": "Bench Press", "reps": 5, "weight": 80, "weight_unit": "kg"}],
    )
    ctx = ToolContext(user_id=str(user.id), db_session=db_session)
    executor = build_legacy_executor(ctx)
    result = executor("get_workout_history", {"start": "2026-01-13"})
    assert result["status"] == "ok"
    assert result["sessions"][0]["exercises"][0]["exercise"] == "Bench Press"
