"""Progress and measurement endpoints.

Returns ownership-scoped historical records. This is descriptive retrieval, not
Person 2's advanced fitness intelligence.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.errors import BadRequestError
from app.models.enums import ActivityEventType, MeasurementType
from app.schemas.common import Page
from app.schemas.progress import BmiPointOut, DerivedMetricsOut, ExerciseMaxLoadOut
from app.schemas.workout import MeasurementCreate, MeasurementOut
from app.services.activity_event_service import ActivityEventService
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
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.METRIC_LOGGED,
        entity_type="measurement",
        entity_id=str(measurement.id),
        occurred_at=payload.measured_at,
        payload={"type": payload.type.value, "value": str(payload.value), "unit": payload.unit},
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


@router.delete(
    "/measurements/{measurement_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_measurement(
    measurement_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete one of the authenticated user's measurements."""
    WorkoutService(db).delete_measurement(current_user.id, measurement_id)


@router.get("/weight", response_model=list[MeasurementOut])
def weight_series(
    current_user: CurrentUser,
    db: DbSession,
) -> list[MeasurementOut]:
    """Return the user's weight measurements in chronological order."""
    measurements = ProgressService(db).weight_series(current_user.id)
    return [MeasurementOut.model_validate(item) for item in measurements]


@router.get("/height", response_model=list[MeasurementOut])
def height_series(
    current_user: CurrentUser,
    db: DbSession,
) -> list[MeasurementOut]:
    """Return the user's height measurements in chronological order."""
    measurements = ProgressService(db).height_series(current_user.id)
    return [MeasurementOut.model_validate(item) for item in measurements]


@router.get("/bmi", response_model=list[BmiPointOut])
def bmi_series(
    current_user: CurrentUser,
    db: DbSession,
) -> list[BmiPointOut]:
    """Return the user's derived BMI series in chronological order."""
    points = ProgressService(db).bmi_series(current_user.id)
    return [BmiPointOut.model_validate(point) for point in points]


@router.get("/derived", response_model=DerivedMetricsOut)
def derived_metrics(
    current_user: CurrentUser,
    db: DbSession,
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
) -> DerivedMetricsOut:
    """Return metrics computed from the user's sessions (volume, streaks, PRs)."""
    if from_date and to_date and from_date > to_date:
        raise BadRequestError("The 'from' date must not be after the 'to' date.")
    metrics = ProgressService(db).derived_metrics(
        current_user.id, from_date=from_date, to_date=to_date
    )
    return DerivedMetricsOut.model_validate(metrics)


@router.get("/records", response_model=list[ExerciseMaxLoadOut])
def exercise_records(
    current_user: CurrentUser,
    db: DbSession,
) -> list[ExerciseMaxLoadOut]:
    """Return the heaviest recorded load per exercise (descriptive only)."""
    records = ProgressService(db).exercise_max_loads(current_user.id)
    return [ExerciseMaxLoadOut.model_validate(record) for record in records]
