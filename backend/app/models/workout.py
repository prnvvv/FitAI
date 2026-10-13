"""Workout sessions and their sets."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
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
from app.models.columns import enum_type
from app.models.enums import WeightUnit
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class WorkoutSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A dated workout session containing one or more sets."""

    __tablename__ = "workout_sessions"
    __table_args__ = (Index("ix_workout_sessions_user_performed", "user_id", "performed_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="workouts")
    sets: Mapped[list[WorkoutSet]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutSet.position",
    )


class WorkoutSet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single exercise set within a workout session."""

    __tablename__ = "workout_sets"
    __table_args__ = (Index("ix_workout_sets_session", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exercise_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    weight_unit: Mapped[WeightUnit | None] = mapped_column(
        enum_type(WeightUnit, "weight_unit"),
        nullable=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    session: Mapped[WorkoutSession] = relationship(back_populates="sets")
