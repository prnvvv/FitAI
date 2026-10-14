"""Exercise library: seeded canonical exercises plus user-defined custom exercises."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class ExerciseLibrary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A catalogue of exercises available when building sessions.

    Rows with ``user_id IS NULL`` are seeded/canonical and visible to every user.
    Rows with a non-null ``user_id`` are private custom exercises for that user.
    """

    __tablename__ = "exercise_library"
    __table_args__ = (
        Index("ix_exercise_library_slug_user", "slug", "user_id", unique=True),
        Index("ix_exercise_library_user", "user_id"),
    )

    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_muscle_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    equipment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    movement_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="reps_weight")
    is_custom: Mapped[bool] = mapped_column(default=False, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    user: Mapped[User | None] = relationship(back_populates="exercises")
