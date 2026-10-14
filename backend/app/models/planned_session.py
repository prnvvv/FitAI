"""Planned sessions: future workouts, rest days and recovery days.

Planned sessions are separate from logged ``WorkoutSession`` records. Marking a
planned session as completed creates a linked ``WorkoutSession`` and copies the
planned exercises into ``WorkoutSet`` rows.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workout import WorkoutSession


class PlannedSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A workout or rest day planned for a specific date."""

    __tablename__ = "planned_sessions"
    __table_args__ = (Index("ix_planned_sessions_user_date", "user_id", "planned_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_type: Mapped[str] = mapped_column(String(50), nullable=False, default="workout")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planned")
    completed_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="planned_sessions")
    completed_session: Mapped[WorkoutSession | None] = relationship()
    exercises: Mapped[list[PlannedExercise]] = relationship(
        back_populates="planned_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PlannedExercise.position",
    )


class PlannedExercise(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An exercise within a planned session."""

    __tablename__ = "planned_exercises"
    __table_args__ = (Index("ix_planned_exercises_session", "planned_session_id"),)

    planned_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("planned_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exercise_name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_weight: Mapped[Numeric | None] = mapped_column(Numeric(6, 2), nullable=True)
    target_weight_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[Numeric | None] = mapped_column(Numeric(8, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    planned_session: Mapped[PlannedSession] = relationship(back_populates="exercises")
