"""Progress and measurement endpoints.

Returns ownership-scoped historical records. This is descriptive retrieval, not
Person 2's advanced fitness intelligence.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.models.enums import MeasurementType
from app.schemas.common import Page
from app.schemas.progress import ExerciseMaxLoadOut
from app.schemas.workout import MeasurementCreate, MeasurementOut
from app.services.progress_service import ProgressService
from app.services.workout_service import WorkoutService

router = APIRouter(prefix="/progress", tags=["progress"])


@router.post(
    "/measurements",
    response_model=MeasurementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_measurement(
    payload: MeasurementCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> MeasurementOut:
    """Record a dated measurement without overwriting prior entries."""
    measurement = WorkoutService(db).create_measurement(
        current_user.id,
        payload.type,
        payload.value,
        payload.unit,
        payload.measured_at,
        notes=payload.notes,
    )
    return MeasurementOut.model_validate(measurement)


@router.get("/measurements", response_model=Page[MeasurementOut])
def list_measurements(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    measurement_type: MeasurementType | None = Query(default=None, alias="type"),
) -> Page[MeasurementOut]:
    """List the authenticated user's measurements, newest first."""
    items, total = WorkoutService(db).list_measurements(
        current_user.id,
        measurement_type=measurement_type,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[MeasurementOut](
        items=[MeasurementOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/weight", response_model=list[MeasurementOut])
def weight_series(
    current_user: CurrentUser,
    db: DbSession,
) -> list[MeasurementOut]:
    """Return the user's weight measurements in chronological order."""
    measurements = ProgressService(db).weight_series(current_user.id)
    return [MeasurementOut.model_validate(item) for item in measurements]


@router.get("/records", response_model=list[ExerciseMaxLoadOut])
def exercise_records(
    current_user: CurrentUser,
    db: DbSession,
) -> list[ExerciseMaxLoadOut]:
    """Return the heaviest recorded load per exercise (descriptive only)."""
    records = ProgressService(db).exercise_max_loads(current_user.id)
    return [ExerciseMaxLoadOut.model_validate(record) for record in records]
