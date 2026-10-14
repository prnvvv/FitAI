"""Plan endpoints: day summaries, planned sessions, templates."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import ActivityEventType
from app.schemas.common import Page
from app.schemas.plan import (
    ApplyTemplateIn,
    DaySummaryOut,
    PlannedSessionCreate,
    PlannedSessionOut,
    PlannedSessionUpdate,
    TemplateOut,
)
from app.services.activity_event_service import ActivityEventService
from app.services.plan_service import PlanService

router = APIRouter(prefix="/plan", tags=["plan"])

TEMPLATE_NAMES = {
    "push_pull_legs": "Push / Pull / Legs",
    "upper_lower": "Upper / Lower",
    "full_body_3": "Full body 3-day",
    "beginner_strength": "Beginner strength",
    "walk_mobility": "Walk + mobility",
}


@router.get("/summary", response_model=list[DaySummaryOut])
def day_summary(
    current_user: CurrentUser,
    db: DbSession,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
) -> list[dict[str, object]]:
    """Return per-day plan aggregates for the inclusive date range."""
    return PlanService(db).day_summary(current_user.id, from_date, to_date)


@router.post(
    "/sessions",
    response_model=PlannedSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: PlannedSessionCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> PlannedSessionOut:
    """Create a planned session for a date."""
    session = PlanService(db).create_planned_session(
        current_user.id,
        payload.planned_date,
        title=payload.title,
        day_type=payload.day_type,
        notes=payload.notes,
        exercises=[e.model_dump() for e in payload.exercises],
    )
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.SESSION_PLANNED,
        entity_type="planned_session",
        entity_id=str(session.id),
        occurred_at=datetime.combine(payload.planned_date, time.min, tzinfo=timezone.utc),
        payload={"day_type": payload.day_type, "exercise_count": len(payload.exercises)},
    )
    return PlannedSessionOut.model_validate(session)


@router.get("/sessions", response_model=Page[PlannedSessionOut])
def list_sessions(
    current_user: CurrentUser,
    db: DbSession,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[PlannedSessionOut]:
    """List planned sessions in a date range."""
    items, total = PlanService(db).list_sessions(
        current_user.id, from_date=from_date, to_date=to_date, limit=limit, offset=offset
    )
    return Page[PlannedSessionOut](
        items=[PlannedSessionOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/sessions/{session_id}", response_model=PlannedSessionOut)
def update_session(
    session_id: UUID,
    payload: PlannedSessionUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> PlannedSessionOut:
    """Update a planned session."""
    session = PlanService(db).update_planned_session(
        session_id,
        current_user.id,
        title=payload.title,
        day_type=payload.day_type,
        notes=payload.notes,
        exercises=[e.model_dump() for e in payload.exercises]
        if payload.exercises is not None
        else None,
    )
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.PLAN_EDITED,
        entity_type="planned_session",
        entity_id=str(session.id),
        occurred_at=datetime.combine(session.planned_date, time.min, tzinfo=timezone.utc),
        payload={"fields": sorted(payload.model_fields_set)},
    )
    return PlannedSessionOut.model_validate(session)


@router.post("/sessions/{session_id}/complete", response_model=PlannedSessionOut)
def complete_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> PlannedSessionOut:
    """Mark a planned session as completed (creates a logged workout)."""
    PlanService(db).mark_completed(session_id, current_user.id)
    session = PlanService(db).get(session_id, current_user.id)
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.SESSION_COMPLETED,
        entity_type="planned_session",
        entity_id=str(session.id),
        occurred_at=datetime.combine(session.planned_date, time.min, tzinfo=timezone.utc),
        payload={"from_plan": True},
    )
    return PlannedSessionOut.model_validate(session)


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a planned session."""
    PlanService(db).delete_planned_session(session_id, current_user.id)


@router.get("/templates", response_model=list[TemplateOut])
def list_templates() -> list[TemplateOut]:
    """Return available starter templates."""
    return [
        TemplateOut(key=key, name=TEMPLATE_NAMES.get(key, key.replace("_", " ").title()), days=days)
        for key, days in PlanService.list_templates().items()
    ]


@router.post("/templates/apply", response_model=list[PlannedSessionOut])
def apply_template(
    payload: ApplyTemplateIn,
    current_user: CurrentUser,
    db: DbSession,
) -> list[PlannedSessionOut]:
    """Apply a starter template to a week."""
    sessions = PlanService(db).apply_template(
        current_user.id, payload.template_key, payload.start_date
    )
    return [PlannedSessionOut.model_validate(s) for s in sessions]
