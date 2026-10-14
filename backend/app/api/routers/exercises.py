"""Exercise library endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.schemas.common import Page
from app.schemas.exercise import ExerciseCreate, ExerciseOut
from app.services.exercise_library_service import ExerciseLibraryService

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=Page[ExerciseOut])
def list_exercises(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    search: str | None = Query(default=None),
    muscle_group: str | None = Query(default=None),
) -> Page[ExerciseOut]:
    """Search canonical and custom exercises visible to the user."""
    items, total = ExerciseLibraryService(db).list_exercises(
        current_user.id,
        search=search,
        muscle_group=muscle_group,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[ExerciseOut](
        items=[ExerciseOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ExerciseOut:
    """Create a private custom exercise."""
    exercise = ExerciseLibraryService(db).create_custom(
        current_user.id,
        payload.name,
        primary_muscle_group=payload.primary_muscle_group,
        equipment=payload.equipment,
        movement_type=payload.movement_type,
        unit_mode=payload.unit_mode,
    )
    return ExerciseOut.model_validate(exercise)


@router.get("/muscle-groups", response_model=list[str])
def list_muscle_groups(
    current_user: CurrentUser,
    db: DbSession,
) -> list[str]:
    """Return distinct muscle groups for filtering."""
    return ExerciseLibraryService(db).list_muscle_groups(current_user.id)


@router.get("/{exercise_id}", response_model=ExerciseOut)
def get_exercise(
    exercise_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ExerciseOut:
    """Return one exercise visible to the user."""
    exercise = ExerciseLibraryService(db).get(exercise_id, current_user.id)
    return ExerciseOut.model_validate(exercise)
