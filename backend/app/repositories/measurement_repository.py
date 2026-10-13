"""Measurement persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import MeasurementType
from app.models.measurement import Measurement


class MeasurementRepository:
    """Persistence operations for dated body measurements."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self,
        user_id: UUID,
        *,
        measurement_type: MeasurementType | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Measurement], int]:
        """Return a page of measurements for ``user_id`` and the total count."""
        filters = [Measurement.user_id == user_id]
        if measurement_type is not None:
            filters.append(Measurement.type == measurement_type)
        total = self._db.scalar(select(func.count()).select_from(Measurement).where(*filters))
        statement = (
            select(Measurement)
            .where(*filters)
            .order_by(Measurement.measured_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def create(
        self,
        user_id: UUID,
        measurement_type: MeasurementType,
        value: object,
        unit: str,
        measured_at: object,
        *,
        notes: str | None = None,
    ) -> Measurement:
        """Create and persist a measurement."""
        measurement = Measurement(
            user_id=user_id,
            type=measurement_type,
            value=value,
            unit=unit,
            measured_at=measured_at,
            notes=notes,
        )
        self._db.add(measurement)
        self._db.flush()
        return measurement

    def get(self, user_id: UUID, measurement_id: UUID) -> Measurement | None:
        """Return a measurement only when it belongs to ``user_id``."""
        from sqlalchemy import select

        statement = select(Measurement).where(
            Measurement.id == measurement_id, Measurement.user_id == user_id
        )
        return self._db.scalar(statement)

    def delete(self, measurement: Measurement) -> None:
        """Delete a measurement."""
        self._db.delete(measurement)
        self._db.flush()

    def series(self, user_id: UUID, measurement_type: MeasurementType) -> list[Measurement]:
        """Return all measurements of a type in chronological order."""
        statement = (
            select(Measurement)
            .where(Measurement.user_id == user_id, Measurement.type == measurement_type)
            .order_by(Measurement.measured_at)
        )
        return list(self._db.scalars(statement))
