"""Adapter exposing persisted workouts to the agent's workout-history port.

Implements :class:`~app.tools.workout_history.WorkoutHistoryService` on top of
the persistence :class:`~app.services.workout_service.WorkoutService`, mapping
ORM sessions/sets onto the agent's canonical :class:`WorkoutLog` shape.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import WeightUnit
from app.models.workout import WorkoutSession
from app.services.workout_service import WorkoutService
from app.tools.workout_tools import ExerciseEntry, SetEntry, WorkoutLog

LB_TO_KG = 0.45359237
MAX_SET_KG = 1000.0
MAX_SET_REPS = 200
MAX_DURATION_MIN = 600
MAX_NAME_LEN = 80


def _to_kg(weight: Decimal | None, unit: WeightUnit | None) -> float:
    """Convert a recorded load to kilograms, clamped to the tool's valid range."""
    if weight is None:
        return 0.0
    value = float(weight)
    if unit == WeightUnit.LB:
        value *= LB_TO_KG
    return round(min(max(value, 0.0), MAX_SET_KG), 3)


class WorkoutHistoryServiceAdapter:
    """Read-only adapter exposing a user's logged workouts to the agent tools."""

    def __init__(self, db: Session, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def get_workouts(self, user_id: str, start: date, end: date) -> list[WorkoutLog]:
        uid = UUID(user_id or self._user_id)
        start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)
        sessions = WorkoutService(self._db).list_sessions_between(uid, start=start_dt, end=end_dt)
        logs: list[WorkoutLog] = []
        for session in sessions:
            log = self._to_log(session)
            if log is not None:
                logs.append(log)
        return logs

    @staticmethod
    def _to_log(session: WorkoutSession) -> WorkoutLog | None:
        groups: dict[str, list[SetEntry]] = {}
        for workout_set in session.sets:
            reps = workout_set.reps
            if reps is None or reps < 1:
                continue
            name = " ".join((workout_set.exercise_name or "").split())[:MAX_NAME_LEN]
            if not name:
                continue
            groups.setdefault(name, []).append(
                SetEntry(
                    reps=min(reps, MAX_SET_REPS),
                    weight_kg=_to_kg(workout_set.weight, workout_set.weight_unit),
                )
            )
        exercises = [ExerciseEntry(name=name, sets=sets) for name, sets in groups.items() if sets]
        if not exercises:
            return None
        duration = session.duration_minutes
        return WorkoutLog(
            performed_on=session.performed_at.date(),
            name=session.name[:MAX_NAME_LEN] if session.name else None,
            duration_min=min(duration, MAX_DURATION_MIN) if duration and duration >= 1 else None,
            exercises=exercises,
        )
