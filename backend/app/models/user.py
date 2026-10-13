"""User account anchor.

The primary key is the Supabase Auth subject (``sub``) claim. FitAI does not
manage passwords or a second authentication system; a local row is provisioned
on first authenticated request so that other tables have a stable foreign key.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activity_event import ActivityEvent
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.measurement import Measurement
    from app.models.memory import Memory, MemoryHistory
    from app.models.pending_update import PendingMemoryUpdate
    from app.models.profile import Profile
    from app.models.workout import WorkoutSession


class User(Base, TimestampMixin):
    """A FitAI user, identified by their Supabase Auth user id."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memories: Mapped[list[Memory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memory_history: Mapped[list[MemoryHistory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    pending_updates: Mapped[list[PendingMemoryUpdate]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    workouts: Mapped[list[WorkoutSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    measurements: Mapped[list[Measurement]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    activity_events: Mapped[list[ActivityEvent]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityEvent.occurred_at.desc()",
    )
