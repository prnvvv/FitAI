"""Memory business logic and transactional workflows.

Person 2 proposes changes; this service validates and commits approved changes.
A pending proposal never mutates current memory before approval, and every
applied change appends an immutable history record in the same transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.enums import MemoryChangeType, MemoryKey, MemoryStatus, PendingUpdateStatus
from app.models.memory import Memory, MemoryHistory
from app.models.pending_update import PendingMemoryUpdate
from app.repositories.memory_repository import MemoryRepository
from app.repositories.pending_update_repository import PendingUpdateRepository
from app.services.memory_validation import validate_memory_value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryService:
    """Coordinates current memory, history, and pending proposals."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._memory = MemoryRepository(db)
        self._pending = PendingUpdateRepository(db)

    # ------------------------------------------------------------------
    # Current memory
    # ------------------------------------------------------------------
    def list_current(self, user_id: UUID) -> list[Memory]:
        """Return all active current-memory rows for the user."""
        return self._memory.list_active(user_id)

    def get(self, memory_id: UUID, user_id: UUID) -> Memory:
        """Return a memory row belonging to the user or raise NotFoundError."""
        memory = self._memory.get_for_user(memory_id, user_id)
        if memory is None:
            raise NotFoundError("Memory not found.")
        return memory

    def list_history(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[MemoryHistory], int]:
        """Return a page of the user's memory history."""
        return self._memory.list_history(user_id, limit=limit, offset=offset)

    def record_history(
        self,
        user_id: UUID,
        key: MemoryKey,
        *,
        change_type: MemoryChangeType,
        previous_value: object | None,
        new_value: object,
        confidence: Decimal | None = None,
        source: str | None = None,
        effective_at: datetime | None = None,
    ) -> None:
        """Append a single immutable history row and commit.

        Used for dated historical events that must be preserved without
        changing the current memory value (e.g. "I weighed 80 kg last year").
        The appended row is not linked to a current memory (``memory_id`` NULL),
        so it survives even if that memory is later deleted.
        """
        self._memory.add_history(
            user_id,
            None,
            key,
            change_type,
            previous_value=previous_value,
            new_value=new_value,
            confidence=confidence,
            source=source,
            effective_at=effective_at,
        )
        self._commit()

    def correct(self, memory_id: UUID, user_id: UUID, new_value: object) -> Memory:
        """Apply a direct user correction to an accepted memory.

        The current value is updated and a history record is appended within a
        single transaction.
        """
        memory = self._memory.get_for_update(memory_id, user_id)
        if memory is None:
            raise NotFoundError("Memory not found.")
        if memory.status != MemoryStatus.ACTIVE:
            raise ConflictError("Only an active memory can be corrected.")
        validate_memory_value(memory.key, new_value)

        previous = memory.value
        memory.value = new_value
        memory.status = MemoryStatus.ACTIVE
        self._memory.add_history(
            user_id,
            memory.id,
            memory.key,
            MemoryChangeType.CORRECTION,
            previous_value=previous,
            new_value=new_value,
            source="user_correction",
        )
        self._commit()
        self._db.refresh(memory)
        return memory

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
        """Create a new current memory fact with a CREATE history record.

        Shared interface for Person 2's memory updates. Refuses to create a new
        row while an active memory already exists for the key.
        """
        validate_memory_value(key, value)
        if self._memory.get_active(user_id, key) is not None:
            raise ConflictError("An active memory already exists for this key.")
        memory = self._memory.create(
            user_id,
            key,
            value,
            confidence=confidence,
            source=source,
            effective_at=effective_at,
        )
        self._memory.add_history(
            user_id,
            memory.id,
            key,
            MemoryChangeType.CREATE,
            previous_value=None,
            new_value=value,
            confidence=confidence,
            source=source,
            effective_at=effective_at,
        )
        self._commit()
        self._db.refresh(memory)
        return memory

    def delete(self, memory_id: UUID, user_id: UUID) -> None:
        """Soft-delete a current memory, preserving history."""
        memory = self._memory.get_for_update(memory_id, user_id)
        if memory is None:
            raise NotFoundError("Memory not found.")
        if memory.status == MemoryStatus.DELETED:
            raise ConflictError("This memory has already been deleted.")

        previous = memory.value
        memory.status = MemoryStatus.DELETED
        self._memory.add_history(
            user_id,
            memory.id,
            memory.key,
            MemoryChangeType.DELETE,
            previous_value=previous,
            new_value=None,
            source="user_delete",
        )
        self._commit()

    # ------------------------------------------------------------------
    # Pending proposals
    # ------------------------------------------------------------------
    def list_pending(
        self,
        user_id: UUID,
        *,
        status: PendingUpdateStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PendingMemoryUpdate], int]:
        """Return a page of the user's pending update proposals."""
        return self._pending.list_for_user(user_id, status=status, limit=limit, offset=offset)

    def create_proposal(
        self,
        user_id: UUID,
        key: MemoryKey,
        proposed_value: object,
        *,
        confidence: Decimal | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> PendingMemoryUpdate:
        """Create a pending proposal.

        Shared interface for Person 2. The current value is snapshotted so that
        a later confirmation can detect staleness. Current memory is not touched.
        """
        validate_memory_value(key, proposed_value)
        current = self._memory.get_active(user_id, key)
        proposal = self._pending.create(
            user_id,
            key,
            proposed_value,
            previous_value=current.value if current is not None else None,
            confidence=confidence,
            source=source,
            reason=reason,
        )
        self._commit()
        self._db.refresh(proposal)
        return proposal

    def confirm(self, update_id: UUID, user_id: UUID) -> Memory:
        """Atomically approve a proposal and apply it to current memory.

        Raises:
            NotFoundError: if the proposal does not exist for this user.
            ConflictError: if the proposal was already resolved or has become
                stale relative to the current value.
        """
        proposal = self._pending.get_for_update(update_id, user_id)
        if proposal is None:
            raise NotFoundError("Pending memory update not found.")
        if proposal.status != PendingUpdateStatus.PENDING:
            raise ConflictError(
                "This update has already been resolved.",
                details={"status": proposal.status.value},
            )

        validate_memory_value(proposal.key, proposal.proposed_value)

        memory = self._memory.get_active(user_id, proposal.key)
        current_value = memory.value if memory is not None else None
        if proposal.previous_value != current_value:
            raise ConflictError(
                "This update is stale because the current value has changed.",
                details={"key": proposal.key.value},
            )

        if memory is None:
            memory = self._memory.create(
                user_id,
                proposal.key,
                proposal.proposed_value,
                confidence=proposal.confidence,
                source=proposal.source,
            )
            change_type = MemoryChangeType.CREATE
            previous_value: object | None = None
        else:
            previous_value = memory.value
            memory.value = proposal.proposed_value
            memory.status = MemoryStatus.ACTIVE
            if proposal.confidence is not None:
                memory.confidence = proposal.confidence
            if proposal.source is not None:
                memory.source = proposal.source
            change_type = MemoryChangeType.UPDATE

        self._memory.add_history(
            user_id,
            memory.id,
            proposal.key,
            change_type,
            previous_value=previous_value,
            new_value=proposal.proposed_value,
            confidence=proposal.confidence,
            source=proposal.source,
        )
        proposal.status = PendingUpdateStatus.APPROVED
        proposal.resolved_at = _utcnow()
        self._commit()
        self._db.refresh(memory)
        return memory

    def reject(self, update_id: UUID, user_id: UUID) -> PendingMemoryUpdate:
        """Reject a proposal without modifying current memory."""
        proposal = self._pending.get_for_update(update_id, user_id)
        if proposal is None:
            raise NotFoundError("Pending memory update not found.")
        if proposal.status != PendingUpdateStatus.PENDING:
            raise ConflictError(
                "This update has already been resolved.",
                details={"status": proposal.status.value},
            )
        proposal.status = PendingUpdateStatus.REJECTED
        proposal.resolved_at = _utcnow()
        self._commit()
        self._db.refresh(proposal)
        return proposal

    # ------------------------------------------------------------------
    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The memory change could not be saved.") from exc
