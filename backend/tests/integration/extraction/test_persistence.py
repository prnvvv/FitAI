"""Integration tests for extraction persistence routing.

Uses the real services against in-memory SQLite to prove each candidate lands in
the correct authoritative table and that retries are idempotent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.extraction.persistence import persist_extraction
from app.extraction.schemas import (
    CompletedWorkout,
    ExtractionResult,
    PlannedWorkout,
    ProgressRecord,
    UserPreference,
)
from app.models.enums import MeasurementType
from app.repositories.user_repository import UserRepository
from app.repositories.workout_repository import WorkoutRepository
from app.services.progress_service import ProgressService

NOW = datetime(2026, 5, 20, 9, 0, 0, tzinfo=timezone.utc)


def _user(db: Session, email="a@example.com"):
    uid = uuid4()
    UserRepository(db).get_or_create(uid, email)
    return uid


def test_completed_workout_is_durable_and_idempotent(db_session: Session) -> None:
    uid = _user(db_session)
    result = ExtractionResult(
        completed_workouts=[
            CompletedWorkout(
                activity="cycling",
                duration_minutes=120,
                confidence=0.95,
                source_text="I did cycling for 2 hours",
            )
        ]
    )

    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    assert len(outcomes) == 1
    assert outcomes[0].kind == "completed_workout"
    assert outcomes[0].status == "saved"
    saved_id = outcomes[0].record_id
    assert saved_id is not None

    sessions, total = WorkoutRepository(db_session).list_sessions(uid, limit=10, offset=0)
    assert total == 1
    assert sessions[0].duration_minutes == 120
    assert sessions[0].sets and sessions[0].sets[0].duration_seconds == 7200

    # Retry (e.g. resubmit) must NOT create a duplicate session.
    outcomes2 = persist_extraction(db_session, uid, result, now=NOW)
    assert outcomes2[0].status == "duplicate"
    assert outcomes2[0].record_id == saved_id
    _sessions, total2 = WorkoutRepository(db_session).list_sessions(uid, limit=10, offset=0)
    assert total2 == 1


def test_planned_workout_goes_to_plan_service(db_session: Session) -> None:
    uid = _user(db_session)
    result = ExtractionResult(
        planned_workouts=[PlannedWorkout(activity="leg day", confidence=0.8, source_text="tmrw")]
    )
    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    assert outcomes[0].kind == "planned_workout"
    assert outcomes[0].status == "saved"

    from app.repositories.planned_session_repository import PlannedSessionRepository

    planned, total = PlannedSessionRepository(db_session).list_for_user(
        uid, from_date=NOW.date(), to_date=NOW.date() + timedelta(days=2), limit=10
    )
    assert total == 1
    assert planned[0].title == "leg day"
    # It must NOT become a completed workout session.
    _w, wt = WorkoutRepository(db_session).list_sessions(uid, limit=10, offset=0)
    assert wt == 0


def test_progress_record_goes_to_measurements(db_session: Session) -> None:
    uid = _user(db_session)
    result = ExtractionResult(
        progress_records=[
            ProgressRecord(measurement_type=MeasurementType.WEIGHT, value=72, unit="kg")
        ]
    )
    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    assert outcomes[0].status == "saved"
    series = ProgressService(db_session).weight_series(uid)
    assert len(series) == 1
    # Idempotent retry.
    assert persist_extraction(db_session, uid, result, now=NOW)[0].status == "duplicate"
    assert len(ProgressService(db_session).weight_series(uid)) == 1


def test_user_preference_stored_separately_from_workout(db_session: Session) -> None:
    uid = _user(db_session)
    result = ExtractionResult(
        completed_workouts=[CompletedWorkout(activity="cycling", duration_minutes=120)],
        user_preferences=[UserPreference(preference="enjoys cycling", confidence=0.9)],
    )
    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    kinds = {o.kind: o.status for o in outcomes}
    assert kinds["completed_workout"] == "saved"
    assert kinds["user_preference"] == "saved"

    from app.services.profile_service import ProfileService

    profile = ProfileService(db_session).get(uid)
    assert profile is not None
    assert "enjoys cycling" in (profile.preferences or {}).get("interests", [])
    # The workout is stored as a WorkoutSession, not inside the preferences.
    _w, wt = WorkoutRepository(db_session).list_sessions(uid, limit=10, offset=0)
    assert wt == 1


def test_fitness_goal_is_not_persisted_here(db_session: Session) -> None:
    from app.extraction.schemas import FitnessGoal

    uid = _user(db_session)
    result = ExtractionResult(fitness_goals=[FitnessGoal(goal="build chest muscle")])
    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    assert outcomes == []  # goals go through the existing memory workflow, not here


def test_provider_error_persists_nothing(db_session: Session) -> None:
    uid = _user(db_session)
    result = ExtractionResult(error="provider_down")
    assert persist_extraction(db_session, uid, result, now=NOW) == []


def test_failed_workout_write_is_reported_as_failed(db_session: Session, monkeypatch) -> None:
    uid = _user(db_session)

    def _boom(*args, **kwargs):
        raise AppError("db write failed")

    monkeypatch.setattr("app.extraction.persistence.WorkoutService.create_session", _boom)
    result = ExtractionResult(completed_workouts=[CompletedWorkout(activity="rowing")])
    outcomes = persist_extraction(db_session, uid, result, now=NOW)
    assert outcomes[0].status == "failed"
    assert outcomes[0].record_id is None
    # Nothing was committed.
    _w, wt = WorkoutRepository(db_session).list_sessions(uid, limit=10, offset=0)
    assert wt == 0


def test_user_isolation(db_session: Session) -> None:
    uid_a = _user(db_session, "a@example.com")
    uid_b = _user(db_session, "b@example.com")
    result = ExtractionResult(completed_workouts=[CompletedWorkout(activity="cycling")])
    persist_extraction(db_session, uid_a, result, now=NOW)
    # User B sees nothing and cannot dedup onto A's record.
    _w, wt_b = WorkoutRepository(db_session).list_sessions(uid_b, limit=10, offset=0)
    assert wt_b == 0
