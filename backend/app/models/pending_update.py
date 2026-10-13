"""Pending memory update proposals awaiting user confirmation."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import MemoryKey, PendingUpdateStatus
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class PendingMemoryUpdate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A proposed change to current memory that has not yet been applied.

    A pending proposal must never mutate current memory before approval. The
    ``previous_value`` snapshot is used to detect stale approvals: if it no
    longer matches the active memory value, confirmation is refused.
    """

    __tablename__ = "pending_memory_updates"
    __table_args__ = (Index("ix_pending_updates_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[MemoryKey] = mapped_column(enum_type(MemoryKey, "memory_key"), nullable=False)
    proposed_value: Mapped[object] = mapped_column(JSONType, nullable=False)
    previous_value: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PendingUpdateStatus] = mapped_column(
        enum_type(PendingUpdateStatus, "pending_update_status"),
        nullable=False,
        default=PendingUpdateStatus.PENDING,
        server_default=PendingUpdateStatus.PENDING.value,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="pending_updates")
