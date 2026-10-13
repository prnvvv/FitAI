"""Current memory and memory history persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import MemoryChangeType, MemoryKey, MemoryStatus
from app.models.memory import Memory, MemoryHistory


class MemoryRepository:
    """Persistence operations for current memory and its history."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active(self, user_id: UUID) -> list[Memory]:
        """Return all active current-memory rows for ``user_id``."""
        statement = (
            select(Memory)
            .where(Memory.user_id == user_id, Memory.status == MemoryStatus.ACTIVE)
            .order_by(Memory.key)
        )
        return list(self._db.scalars(statement))

    def get_active(self, user_id: UUID, key: MemoryKey) -> Memory | None:
        """Return the active memory row for a key, if any."""
        statement = select(Memory).where(
            Memory.user_id == user_id,
            Memory.key == key,
            Memory.status == MemoryStatus.ACTIVE,
        )
        return self._db.scalar(statement)

    def get_for_user(self, memory_id: UUID, user_id: UUID) -> Memory | None:
        """Return a memory row only when it belongs to ``user_id``."""
        statement = select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
        return self._db.scalar(statement)

    def get_for_update(self, memory_id: UUID, user_id: UUID) -> Memory | None:
        """Lock and return a memory row for a transactional update."""
        statement = (
            select(Memory)
            .where(Memory.id == memory_id, Memory.user_id == user_id)
            .with_for_update()
        )
        return self._db.scalar(statement)

    def create(
        self,
        user_id: UUID,
        key: MemoryKey,
        value: object,
        *,
        confidence: Decimal | None = None,
        source: str | None = None,
        effective_at: datetime | None = None,
    ) -> Memory:
        """Create and persist an active memory row."""
        memory = Memory(
            user_id=user_id,
            key=key,
            value=value,
            status=MemoryStatus.ACTIVE,
            confidence=confidence,
            source=source,
            effective_at=effective_at,
        )
        self._db.add(memory)
        self._db.flush()
        return memory

    def add_history(
        self,
        user_id: UUID,
        memory_id: UUID | None,
        key: MemoryKey,
        change_type: MemoryChangeType,
        *,
        previous_value: object | None = None,
        new_value: object | None = None,
        confidence: Decimal | None = None,
        source: str | None = None,
        effective_at: datetime | None = None,
    ) -> MemoryHistory:
        """Append an immutable history entry."""
        history = MemoryHistory(
            user_id=user_id,
            memory_id=memory_id,
            key=key,
            change_type=change_type,
            previous_value=previous_value,
            new_value=new_value,
            confidence=confidence,
            source=source,
            effective_at=effective_at,
        )
        self._db.add(history)
        self._db.flush()
        return history

    def list_history(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[MemoryHistory], int]:
        """Return a page of memory history for ``user_id`` and the total count."""
        total = self._db.scalar(
            select(func.count()).select_from(MemoryHistory).where(MemoryHistory.user_id == user_id)
        )
        statement = (
            select(MemoryHistory)
            .where(MemoryHistory.user_id == user_id)
            .order_by(MemoryHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)
