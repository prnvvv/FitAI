"""Activity event log for agent retrieval and user history.

Events are append-only and scoped to a user. They are written in the same
transaction as the mutation that produces them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import ActivityEventType
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class ActivityEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An append-only event describing something the user (or agent) did."""

    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_activity_events_user_type", "user_id", "type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[ActivityEventType] = mapped_column(
        enum_type(ActivityEventType, "activity_event_type"),
        nullable=False,
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)

    user: Mapped[User] = relationship(back_populates="activity_events")
