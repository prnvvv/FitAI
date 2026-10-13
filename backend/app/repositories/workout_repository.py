"""Workout persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.workout import WorkoutSession, WorkoutSet


class WorkoutRepository:
    """Persistence operations for workout sessions and sets."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_sessions(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[WorkoutSession], int]:
        """Return a page of workout sessions for ``user_id`` and the total count."""
        total = self._db.scalar(
            select(func.count())
            .select_from(WorkoutSession)
            .where(WorkoutSession.user_id == user_id)
        )
        statement = (
            select(WorkoutSession)
            .where(WorkoutSession.user_id == user_id)
            .options(selectinload(WorkoutSession.sets))
            .order_by(WorkoutSession.performed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def get_session(self, session_id: UUID, user_id: UUID) -> WorkoutSession | None:
        """Return a workout session only when it belongs to ``user_id``."""
        statement = (
            select(WorkoutSession)
            .where(WorkoutSession.id == session_id, WorkoutSession.user_id == user_id)
            .options(selectinload(WorkoutSession.sets))
        )
        return self._db.scalar(statement)

    def create_session(
        self,
        user_id: UUID,
        performed_at: object,
        *,
        name: str | None = None,
        duration_minutes: int | None = None,
        notes: str | None = None,
        sets: list[dict[str, object]] | None = None,
    ) -> WorkoutSession:
        """Create a workout session with its ordered sets."""
        session = WorkoutSession(
            user_id=user_id,
            performed_at=performed_at,
            name=name,
            duration_minutes=duration_minutes,
            notes=notes,
        )
        for position, set_fields in enumerate(sets or []):
            session.sets.append(WorkoutSet(position=position, **set_fields))
        self._db.add(session)
        self._db.flush()
        return session

    def delete_session(self, session: WorkoutSession) -> None:
        """Delete a workout session and (by cascade) its sets."""
        self._db.delete(session)
        self._db.flush()

    def list_sets_with_load(
        self, user_id: UUID, *, exercise_name: str | None = None
    ) -> list[WorkoutSet]:
        """Return sets that recorded a load, for basic progress aggregation."""
        statement = (
            select(WorkoutSet)
            .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
            .where(WorkoutSession.user_id == user_id, WorkoutSet.weight.is_not(None))
            .order_by(WorkoutSession.performed_at)
        )
        if exercise_name:
            statement = statement.where(WorkoutSet.exercise_name == exercise_name)
        return list(self._db.scalars(statement))
