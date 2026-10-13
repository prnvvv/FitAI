"""Workout session endpoints.

Persistence only; advanced analysis and PR detection belong to Person 2.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.workout import WorkoutSessionCreate, WorkoutSessionOut
from app.services.workout_service import WorkoutService

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.post("", response_model=WorkoutSessionOut, status_code=status.HTTP_201_CREATED)
def create_workout(
    payload: WorkoutSessionCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> WorkoutSessionOut:
    """Record a workout session with its sets."""
    service = WorkoutService(db)
    sets = [set_item.model_dump() for set_item in payload.sets]
    session = service.create_session(
        current_user.id,
        payload.performed_at,
        name=payload.name,
        duration_minutes=payload.duration_minutes,
        notes=payload.notes,
        sets=sets,
    )
    return WorkoutSessionOut.model_validate(session)


@router.get("", response_model=Page[WorkoutSessionOut])
def list_workouts(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[WorkoutSessionOut]:
    """List the authenticated user's workout sessions, newest first."""
    items, total = WorkoutService(db).list_sessions(
        current_user.id, limit=pagination.limit, offset=pagination.offset
    )
    return Page[WorkoutSessionOut](
        items=[WorkoutSessionOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{session_id}", response_model=WorkoutSessionOut)
def get_workout(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> WorkoutSessionOut:
    """Return one of the authenticated user's workout sessions."""
    session = WorkoutService(db).get_session(current_user.id, session_id)
    return WorkoutSessionOut.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_workout(
    session_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a workout session and its sets."""
    WorkoutService(db).delete_session(current_user.id, session_id)
