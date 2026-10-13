"""Pending memory update persistence."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import MemoryKey, PendingUpdateStatus
from app.models.pending_update import PendingMemoryUpdate


class PendingUpdateRepository:
    """Persistence operations for pending memory update proposals."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self,
        user_id: UUID,
        *,
        status: PendingUpdateStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PendingMemoryUpdate], int]:
        """Return a page of proposals for ``user_id`` and the total count."""
        filters = [PendingMemoryUpdate.user_id == user_id]
        if status is not None:
            filters.append(PendingMemoryUpdate.status == status)
        total = self._db.scalar(
            select(func.count()).select_from(PendingMemoryUpdate).where(*filters)
        )
        statement = (
            select(PendingMemoryUpdate)
            .where(*filters)
            .order_by(PendingMemoryUpdate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def get_for_user(self, update_id: UUID, user_id: UUID) -> PendingMemoryUpdate | None:
        """Return a proposal only when it belongs to ``user_id``."""
        statement = select(PendingMemoryUpdate).where(
            PendingMemoryUpdate.id == update_id,
            PendingMemoryUpdate.user_id == user_id,
        )
        return self._db.scalar(statement)

    def get_for_update(self, update_id: UUID, user_id: UUID) -> PendingMemoryUpdate | None:
        """Lock and return a proposal for an atomic state transition."""
        statement = (
            select(PendingMemoryUpdate)
            .where(
                PendingMemoryUpdate.id == update_id,
                PendingMemoryUpdate.user_id == user_id,
            )
            .with_for_update()
        )
        return self._db.scalar(statement)

    def create(
        self,
        user_id: UUID,
        key: MemoryKey,
        proposed_value: object,
        *,
        previous_value: object | None = None,
        confidence: Decimal | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> PendingMemoryUpdate:
        """Create and persist a pending proposal."""
        update = PendingMemoryUpdate(
            user_id=user_id,
            key=key,
            proposed_value=proposed_value,
            previous_value=previous_value,
            confidence=confidence,
            source=source,
            reason=reason,
            status=PendingUpdateStatus.PENDING,
        )
        self._db.add(update)
        self._db.flush()
        return update
