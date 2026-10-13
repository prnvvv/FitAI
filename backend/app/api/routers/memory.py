"""Memory endpoints: current facts, history, and pending proposals."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.models.enums import PendingUpdateStatus
from app.schemas.common import Page
from app.schemas.memory import (
    MemoryCorrectRequest,
    MemoryHistoryOut,
    MemoryOut,
    PendingUpdateOut,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=Page[MemoryOut])
def list_current_memory(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[MemoryOut]:
    """List the authenticated user's active structured memory."""
    memories = MemoryService(db).list_current(current_user.id)
    return Page[MemoryOut](
        items=[MemoryOut.model_validate(memory) for memory in memories],
        total=len(memories),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/history", response_model=Page[MemoryHistoryOut])
def list_memory_history(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[MemoryHistoryOut]:
    """List the authenticated user's memory history, newest first."""
    items, total = MemoryService(db).list_history(
        current_user.id, limit=pagination.limit, offset=pagination.offset
    )
    return Page[MemoryHistoryOut](
        items=[MemoryHistoryOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/pending", response_model=Page[PendingUpdateOut])
def list_pending_updates(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    status_filter: PendingUpdateStatus | None = Query(default=None, alias="status"),
) -> Page[PendingUpdateOut]:
    """List the authenticated user's pending memory update proposals."""
    items, total = MemoryService(db).list_pending(
        current_user.id,
        status=status_filter,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[PendingUpdateOut](
        items=[PendingUpdateOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/pending/{update_id}/confirm", response_model=MemoryOut)
def confirm_pending_update(
    update_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MemoryOut:
    """Approve a proposal and apply it to current memory atomically."""
    memory = MemoryService(db).confirm(update_id, current_user.id)
    return MemoryOut.model_validate(memory)


@router.post("/pending/{update_id}/reject", response_model=PendingUpdateOut)
def reject_pending_update(
    update_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> PendingUpdateOut:
    """Reject a proposal without modifying current memory."""
    proposal = MemoryService(db).reject(update_id, current_user.id)
    return PendingUpdateOut.model_validate(proposal)


@router.patch("/{memory_id}", response_model=MemoryOut)
def correct_memory(
    memory_id: UUID,
    payload: MemoryCorrectRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MemoryOut:
    """Correct an accepted memory, preserving the previous value in history."""
    memory = MemoryService(db).correct(memory_id, current_user.id, payload.value)
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Soft-delete a current memory, preserving its history."""
    MemoryService(db).delete(memory_id, current_user.id)
