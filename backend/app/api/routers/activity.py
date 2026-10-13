"""Activity log endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.models.enums import ActivityEventType
from app.schemas.activity_event import ActivityEventOut
from app.schemas.common import Page
from app.services.activity_event_service import ActivityEventService

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=Page[ActivityEventOut])
def list_activity(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    types: list[ActivityEventType] | None = Query(default=None),
) -> Page[ActivityEventOut]:
    """List the authenticated user's recent activity events."""
    items, total = ActivityEventService(db).list(
        current_user.id,
        types=types or [],
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[ActivityEventOut](
        items=[ActivityEventOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def clear_activity(
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Clear the authenticated user's activity history."""
    ActivityEventService(db).clear(current_user.id)
