"""Workout and measurement business logic (persistence only).

Advanced fitness analysis is owned by Person 2. This service validates and
persists records and returns them for analysis.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import MeasurementType
from app.models.measurement import Measurement
from app.models.workout import WorkoutSession
from app.repositories.measurement_repository import MeasurementRepository
from app.repositories.workout_repository import WorkoutRepository


class WorkoutService:
    """Coordinates workout sessions, sets, and measurements."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._workouts = WorkoutRepository(db)
        self._measurements = MeasurementRepository(db)

    # Workouts
    def list_sessions(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[WorkoutSession], int]:
        """Return a page of the user's workout sessions."""
        return self._workouts.list_sessions(user_id, limit=limit, offset=offset)

    def get_session(self, user_id: UUID, session_id: UUID) -> WorkoutSession:
        """Return the user's workout session or raise NotFoundError."""
        session = self._workouts.get_session(session_id, user_id)
        if session is None:
            raise NotFoundError("Workout session not found.")
        return session

    def create_session(
        self,
        user_id: UUID,
        performed_at: datetime,
        *,
        name: str | None = None,
        duration_minutes: int | None = None,
        notes: str | None = None,
        sets: list[dict[str, object]] | None = None,
    ) -> WorkoutSession:
        """Create a workout session with its ordered sets."""
        session = self._workouts.create_session(
            user_id,
            performed_at,
            name=name,
            duration_minutes=duration_minutes,
            notes=notes,
            sets=sets,
        )
        self._commit()
        return self.get_session(user_id, session.id)

    def delete_session(self, user_id: UUID, session_id: UUID) -> None:
        """Delete the user's workout session and its sets."""
        session = self.get_session(user_id, session_id)
        self._workouts.delete_session(session)
        self._commit()

    # Measurements
    def list_measurements(
        self,
        user_id: UUID,
        *,
        measurement_type: MeasurementType | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Measurement], int]:
        """Return a page of the user's measurements."""
        return self._measurements.list_for_user(
            user_id,
            measurement_type=measurement_type,
            limit=limit,
            offset=offset,
        )

    def create_measurement(
        self,
        user_id: UUID,
        measurement_type: MeasurementType,
        value: object,
        unit: str,
        measured_at: datetime,
        *,
        notes: str | None = None,
    ) -> Measurement:
        """Record a new measurement without overwriting prior entries.

        Heights and weights are normalised to canonical units (cm / kg) before
        storage so derived metrics such as BMI are always consistent.
        """

        normalized_value = value
        normalized_unit = unit
        if measurement_type == MeasurementType.HEIGHT:
            normalized_value, normalized_unit = self._normalize_height(value, unit)
        elif measurement_type == MeasurementType.WEIGHT:
            normalized_value, normalized_unit = self._normalize_weight(value, unit)

        measurement = self._measurements.create(
            user_id,
            measurement_type,
            normalized_value,
            normalized_unit,
            measured_at,
            notes=notes,
        )
        self._commit()
        self._db.refresh(measurement)
        return measurement

    @staticmethod
    def _normalize_height(value: object, unit: str) -> tuple[object, str]:
        from decimal import Decimal

        if unit == "cm":
            return value, "cm"
        if unit == "in":
            return Decimal(value) * Decimal("2.54"), "cm"
        if unit == "ft_in":
            # value is total inches when sent as ft_in.
            return Decimal(value) * Decimal("2.54"), "cm"
        return value, unit

    @staticmethod
    def _normalize_weight(value: object, unit: str) -> tuple[object, str]:
        from decimal import Decimal

        if unit == "kg":
            return value, "kg"
        if unit == "lb":
            return Decimal(value) * Decimal("0.45359237"), "kg"
        return value, unit

    def delete_measurement(self, user_id: UUID, measurement_id: UUID) -> None:
        """Delete the user's measurement."""
        measurement = self._measurements.get(user_id, measurement_id)
        if measurement is None:
            raise NotFoundError("Measurement not found.")
        self._measurements.delete(measurement)
        self._commit()

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The workout record could not be saved.") from exc
