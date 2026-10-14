"""Plan business logic: planned sessions, templates and day summaries."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, BadRequestError, NotFoundError
from app.models.enums import WeightUnit
from app.models.planned_session import PlannedExercise, PlannedSession
from app.models.workout import WorkoutSession, WorkoutSet
from app.repositories.planned_session_repository import PlannedSessionRepository
from app.repositories.workout_repository import WorkoutRepository

# Starter programme templates. Each is a list of planned-session descriptions
# that can be applied to a week or a single day.
TEMPLATES: dict[str, list[dict[str, object]]] = {
    "push_pull_legs": [
        {
            "title": "Push",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Bench Press", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Overhead Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Triceps Pushdown", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Lateral Raise", "target_sets": 3, "target_reps": 15},
            ],
        },
        {
            "title": "Pull",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Barbell Row", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Lat Pulldown", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Bicep Curl", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Face Pull", "target_sets": 3, "target_reps": 15},
            ],
        },
        {
            "title": "Legs",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Barbell Back Squat", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Romanian Deadlift", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Leg Press", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Calf Raise", "target_sets": 4, "target_reps": 15},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Push",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Incline Dumbbell Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Dumbbell Shoulder Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Dips", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Cable Fly", "target_sets": 3, "target_reps": 15},
            ],
        },
        {
            "title": "Pull",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Pull-up", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Seated Cable Row", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Hammer Curl", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Rear Delt Fly", "target_sets": 3, "target_reps": 15},
            ],
        },
        {
            "title": "Legs",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Front Squat", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Leg Curl", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Leg Extension", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Hip Thrust", "target_sets": 3, "target_reps": 12},
            ],
        },
    ],
    "upper_lower": [
        {
            "title": "Upper",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Bench Press", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Barbell Row", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Overhead Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Lat Pulldown", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Bicep Curl", "target_sets": 3, "target_reps": 12},
            ],
        },
        {
            "title": "Lower",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Barbell Back Squat", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Romanian Deadlift", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Leg Press", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Calf Raise", "target_sets": 4, "target_reps": 15},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Upper",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Incline Dumbbell Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Pull-up", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Dumbbell Shoulder Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Seated Cable Row", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Triceps Pushdown", "target_sets": 3, "target_reps": 12},
            ],
        },
        {
            "title": "Lower",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Front Squat", "target_sets": 4, "target_reps": 8},
                {"exercise_name": "Leg Curl", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Leg Extension", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Hip Thrust", "target_sets": 3, "target_reps": 12},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {"title": "Rest", "day_type": "rest", "exercises": []},
    ],
    "full_body_3": [
        {
            "title": "Full body A",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Barbell Back Squat", "target_sets": 3, "target_reps": 8},
                {"exercise_name": "Bench Press", "target_sets": 3, "target_reps": 8},
                {"exercise_name": "Barbell Row", "target_sets": 3, "target_reps": 8},
                {"exercise_name": "Plank", "duration_seconds": 60},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Full body B",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Romanian Deadlift", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Overhead Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Pull-up", "target_sets": 3, "target_reps": 8},
                {"exercise_name": "Walking Lunge", "target_sets": 3, "target_reps": 10},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Full body C",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Leg Press", "target_sets": 3, "target_reps": 12},
                {"exercise_name": "Incline Dumbbell Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Seated Cable Row", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Calf Raise", "target_sets": 3, "target_reps": 15},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {"title": "Rest", "day_type": "rest", "exercises": []},
    ],
    "beginner_strength": [
        {
            "title": "Strength A",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Goblet Squat", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Push-up", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Dumbbell Row", "target_sets": 3, "target_reps": 10},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Strength B",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Romanian Deadlift", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Dumbbell Shoulder Press", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Lat Pulldown", "target_sets": 3, "target_reps": 10},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {
            "title": "Strength A",
            "day_type": "workout",
            "exercises": [
                {"exercise_name": "Goblet Squat", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Push-up", "target_sets": 3, "target_reps": 10},
                {"exercise_name": "Dumbbell Row", "target_sets": 3, "target_reps": 10},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {"title": "Rest", "day_type": "rest", "exercises": []},
    ],
    "walk_mobility": [
        {
            "title": "Walk",
            "day_type": "active_recovery",
            "exercises": [
                {"exercise_name": "Walking", "duration_seconds": 1800},
            ],
        },
        {
            "title": "Mobility",
            "day_type": "active_recovery",
            "exercises": [
                {"exercise_name": "Stretching", "duration_seconds": 900},
                {"exercise_name": "Foam Rolling", "duration_seconds": 600},
            ],
        },
        {
            "title": "Walk",
            "day_type": "active_recovery",
            "exercises": [
                {"exercise_name": "Walking", "duration_seconds": 1800},
            ],
        },
        {
            "title": "Mobility",
            "day_type": "active_recovery",
            "exercises": [
                {"exercise_name": "Yoga Flow", "duration_seconds": 900},
                {"exercise_name": "Hip Flexor Stretch", "duration_seconds": 300},
            ],
        },
        {
            "title": "Walk",
            "day_type": "active_recovery",
            "exercises": [
                {"exercise_name": "Walking", "duration_seconds": 1800},
            ],
        },
        {"title": "Rest", "day_type": "rest", "exercises": []},
        {"title": "Rest", "day_type": "rest", "exercises": []},
    ],
}

MAX_SUMMARY_DAYS = 400


def _utc_date(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class PlanService:
    """Coordinates planned sessions and day summaries."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._planned = PlannedSessionRepository(db)
        self._workouts = WorkoutRepository(db)

    def day_summary(
        self,
        user_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, object]]:
        """Return per-day plan aggregates for the inclusive date range.

        The range is capped to ``MAX_SUMMARY_DAYS`` to avoid abuse.
        """
        if from_date > to_date:
            from_date, to_date = to_date, from_date
        if (to_date - from_date).days > MAX_SUMMARY_DAYS:
            raise BadRequestError(
                f"Date range is too large. Maximum is {MAX_SUMMARY_DAYS} days.",
                details={"max_days": MAX_SUMMARY_DAYS},
            )

        planned, _ = self._planned.list_for_user(
            user_id, from_date=from_date, to_date=to_date, limit=MAX_SUMMARY_DAYS
        )
        logged = self._workouts.list_sessions_in_range(user_id, from_date, to_date)

        days: dict[date, dict[str, object]] = {}
        for planned_session in planned:
            d = planned_session.planned_date
            entry = days.setdefault(
                d,
                {
                    "date": d.isoformat(),
                    "planned_count": 0,
                    "completed_count": 0,
                    "day_type": planned_session.day_type,
                    "has_meals": False,
                },
            )
            entry["planned_count"] = int(entry.get("planned_count", 0)) + 1
            if planned_session.status == "completed":
                entry["completed_count"] = int(entry.get("completed_count", 0)) + 1

        linked_workout_ids = {
            s.completed_session_id for s in planned if s.completed_session_id is not None
        }

        for workout in logged:
            d = workout.performed_at.date()
            if d < from_date or d > to_date:
                continue
            if workout.id in linked_workout_ids:
                # Already counted through its planned session.
                continue
            entry = days.setdefault(
                d,
                {
                    "date": d.isoformat(),
                    "planned_count": 0,
                    "completed_count": 0,
                    "day_type": "workout",
                    "has_meals": False,
                },
            )
            entry["completed_count"] = int(entry.get("completed_count", 0)) + 1

        # Ensure every date in the range is represented.
        current = from_date
        while current <= to_date:
            if current not in days:
                days[current] = {
                    "date": current.isoformat(),
                    "planned_count": 0,
                    "completed_count": 0,
                    "day_type": "rest",
                    "has_meals": False,
                }
            current += timedelta(days=1)

        return [days[d] for d in sorted(days)]

    def list_sessions(
        self,
        user_id: uuid.UUID,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PlannedSession], int]:
        """Return a page of the user's planned sessions in a date range."""
        return self._planned.list_for_user(
            user_id, from_date=from_date, to_date=to_date, limit=limit, offset=offset
        )

    def get(self, session_id: uuid.UUID, user_id: uuid.UUID) -> PlannedSession:
        """Return one of the user's planned sessions or raise NotFoundError."""
        session = self._planned.get(session_id, user_id)
        if session is None:
            raise NotFoundError("Planned session not found.")
        return session

    def create_planned_session(
        self,
        user_id: uuid.UUID,
        planned_date: date,
        *,
        title: str | None = None,
        day_type: str = "workout",
        notes: str | None = None,
        exercises: list[dict[str, object]] | None = None,
    ) -> PlannedSession:
        session = self._planned.create(
            user_id,
            planned_date,
            title=title,
            day_type=day_type,
            notes=notes,
        )
        for idx, item in enumerate(exercises or []):
            session.exercises.append(
                PlannedExercise(
                    position=idx,
                    exercise_name=str(item.get("exercise_name", "Exercise")),
                    target_sets=item.get("target_sets"),
                    target_reps=item.get("target_reps"),
                    target_weight=item.get("target_weight"),
                    target_weight_unit=item.get("target_weight_unit"),
                    duration_seconds=item.get("duration_seconds"),
                    distance_meters=item.get("distance_meters"),
                    notes=item.get("notes"),
                )
            )
        self._commit()
        self._db.refresh(session)
        return session

    def update_planned_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        day_type: str | None = None,
        notes: str | None = None,
        exercises: list[dict[str, object]] | None = None,
    ) -> PlannedSession:
        session = self._planned.get(session_id, user_id)
        if session is None:
            raise NotFoundError("Planned session not found.")
        if title is not None:
            session.title = title
        if day_type is not None:
            session.day_type = day_type
        if notes is not None:
            session.notes = notes
        if exercises is not None:
            session.exercises = []
            for idx, item in enumerate(exercises):
                session.exercises.append(
                    PlannedExercise(
                        position=idx,
                        exercise_name=str(item.get("exercise_name", "Exercise")),
                        target_sets=item.get("target_sets"),
                        target_reps=item.get("target_reps"),
                        target_weight=item.get("target_weight"),
                        target_weight_unit=item.get("target_weight_unit"),
                        duration_seconds=item.get("duration_seconds"),
                        distance_meters=item.get("distance_meters"),
                        notes=item.get("notes"),
                    )
                )
        self._commit()
        self._db.refresh(session)
        return session

    def mark_completed(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        performed_at: datetime | None = None,
    ) -> WorkoutSession:
        """Mark a planned session as completed by creating a logged workout."""
        planned = self._planned.get(session_id, user_id)
        if planned is None:
            raise NotFoundError("Planned session not found.")

        when = performed_at or _utc_date(planned.planned_date)
        workout = WorkoutSession(
            user_id=user_id,
            name=planned.title,
            performed_at=when,
            notes=planned.notes,
        )
        for idx, ex in enumerate(planned.exercises):
            weight = ex.target_weight
            weight_unit = ex.target_weight_unit
            parsed_unit: WeightUnit | None = None
            if weight_unit in {"kg", "lb"}:
                parsed_unit = WeightUnit(weight_unit)
            workout.sets.append(
                WorkoutSet(
                    position=idx,
                    exercise_name=ex.exercise_name,
                    reps=ex.target_reps,
                    weight=Decimal(weight) if weight is not None else None,
                    weight_unit=parsed_unit,
                    duration_seconds=ex.duration_seconds,
                    distance_meters=Decimal(ex.distance_meters)
                    if ex.distance_meters is not None
                    else None,
                )
            )
        self._db.add(workout)
        # The workout id is only populated by the database; flush before linking.
        self._db.flush()
        planned.status = "completed"
        planned.completed_session_id = workout.id
        self._commit()

        self._db.refresh(planned)
        self._db.refresh(workout)
        return workout

    def delete_planned_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        planned = self._planned.get(session_id, user_id)
        if planned is None:
            raise NotFoundError("Planned session not found.")
        self._planned.delete(planned)
        self._commit()

    @staticmethod
    def list_templates() -> dict[str, list[dict[str, object]]]:
        return TEMPLATES

    def apply_template(
        self,
        user_id: uuid.UUID,
        template_key: str,
        start_date: date,
    ) -> list[PlannedSession]:
        """Apply a weekly template starting from ``start_date``."""
        template = TEMPLATES.get(template_key)
        if template is None:
            raise NotFoundError("Template not found.")

        created: list[PlannedSession] = []
        for idx, day in enumerate(template):
            planned_date = start_date + timedelta(days=idx)
            session = self._planned.create(
                user_id,
                planned_date,
                title=day.get("title"),
                day_type=str(day.get("day_type", "workout")),
            )
            for eidx, item in enumerate(day.get("exercises", [])):
                session.exercises.append(
                    PlannedExercise(
                        position=eidx,
                        exercise_name=str(item.get("exercise_name", "Exercise")),
                        target_sets=item.get("target_sets"),
                        target_reps=item.get("target_reps"),
                        target_weight=item.get("target_weight"),
                        target_weight_unit=item.get("target_weight_unit"),
                        duration_seconds=item.get("duration_seconds"),
                        distance_meters=item.get("distance_meters"),
                    )
                )
            created.append(session)
        self._commit()
        for session in created:
            self._db.refresh(session)
        return created

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The plan could not be saved.") from exc
