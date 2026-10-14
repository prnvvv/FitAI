"""Planned session persistence."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.planned_session import PlannedSession


class PlannedSessionRepository:
    """Persistence for planned sessions and their exercises."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[PlannedSession], int]:
        filters = [PlannedSession.user_id == user_id]
        if from_date:
            filters.append(PlannedSession.planned_date >= from_date)
        if to_date:
            filters.append(PlannedSession.planned_date <= to_date)

        total = self._db.scalar(select(func.count()).select_from(PlannedSession).where(*filters))
        statement = (
            select(PlannedSession)
            .options(selectinload(PlannedSession.exercises))
            .where(*filters)
            .order_by(PlannedSession.planned_date.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def get(self, session_id: uuid.UUID, user_id: uuid.UUID) -> PlannedSession | None:
        return self._db.scalar(
            select(PlannedSession)
            .options(selectinload(PlannedSession.exercises))
            .where(PlannedSession.id == session_id, PlannedSession.user_id == user_id)
        )

    def create(
        self,
        user_id: uuid.UUID,
        planned_date: date,
        *,
        title: str | None = None,
        day_type: str = "workout",
        status: str = "planned",
        notes: str | None = None,
    ) -> PlannedSession:
        session = PlannedSession(
            user_id=user_id,
            title=title,
            planned_date=planned_date,
            day_type=day_type,
            status=status,
            notes=notes,
        )
        self._db.add(session)
        return session

    def delete(self, session: PlannedSession) -> None:
        self._db.delete(session)
