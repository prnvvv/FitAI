"""Pending chat actions awaiting user confirmation.

An action the agent can perform on the user's behalf (log a workout, or use
stored height/weight to personalise an answer) is proposed as a row rather than
executed immediately. The action only runs once the user confirms it, and the
stored ``payload`` carries everything needed to execute it later.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import PendingActionStatus, PendingActionType
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class PendingChatAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A proposed action the agent will execute only after user confirmation."""

    __tablename__ = "pending_chat_actions"
    __table_args__ = (Index("ix_pending_chat_actions_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[PendingActionType] = mapped_column(
        enum_type(PendingActionType, "pending_action_type"),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONType, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PendingActionStatus] = mapped_column(
        enum_type(PendingActionStatus, "pending_action_status"),
        nullable=False,
        default=PendingActionStatus.PENDING,
        server_default=PendingActionStatus.PENDING.value,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="pending_actions")
