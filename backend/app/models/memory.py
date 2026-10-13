"""Current structured memory and its immutable history.

Current facts live in ``memories`` (one active row per user/key). Every change
also appends to ``memory_history`` so the user's fitness journey is preserved
and the distinction between current and historical facts is explicit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import MemoryChangeType, MemoryKey, MemoryStatus
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Memory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An accepted, current structured fact about a user."""

    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "uq_memories_user_key_active",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[MemoryKey] = mapped_column(enum_type(MemoryKey, "memory_key"), nullable=False)
    value: Mapped[object] = mapped_column(JSONType, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_type(MemoryStatus, "memory_status"),
        nullable=False,
        default=MemoryStatus.ACTIVE,
        server_default=MemoryStatus.ACTIVE.value,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="memories")


class MemoryHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable record of a change to current memory."""

    __tablename__ = "memory_history"
    __table_args__ = (Index("ix_memory_history_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
    )
    key: Mapped[MemoryKey] = mapped_column(enum_type(MemoryKey, "memory_key"), nullable=False)
    change_type: Mapped[MemoryChangeType] = mapped_column(
        enum_type(MemoryChangeType, "memory_change_type"),
        nullable=False,
    )
    previous_value: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    new_value: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="memory_history")
