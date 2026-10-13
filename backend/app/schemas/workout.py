"""Workout and measurement schemas."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import MeasurementType, WeightUnit

#: Allowed units per measurement type.
MEASUREMENT_UNITS: dict[MeasurementType, frozenset[str]] = {
    MeasurementType.WEIGHT: frozenset({"kg", "lb"}),
    MeasurementType.BODY_FAT_PERCENT: frozenset({"%"}),
    MeasurementType.CHEST: frozenset({"cm", "in"}),
    MeasurementType.WAIST: frozenset({"cm", "in"}),
    MeasurementType.HIPS: frozenset({"cm", "in"}),
    MeasurementType.ARM: frozenset({"cm", "in"}),
    MeasurementType.THIGH: frozenset({"cm", "in"}),
    MeasurementType.NECK: frozenset({"cm", "in"}),
}


class WorkoutSetIn(BaseModel):
    """A single set supplied when creating a workout session."""

    exercise_name: str = Field(min_length=1, max_length=200)
    reps: int | None = Field(default=None, ge=0, le=1000)
    weight: Decimal | None = Field(default=None, ge=0, le=2000)
    weight_unit: WeightUnit | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    distance_meters: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _require_unit_with_weight(self) -> WorkoutSetIn:
        if self.weight is not None and self.weight_unit is None:
            raise ValueError("weight_unit is required when weight is provided.")
        return self


class WorkoutSetOut(BaseModel):
    """A persisted workout set."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    exercise_name: str
    reps: int | None = None
    weight: Decimal | None = None
    weight_unit: WeightUnit | None = None
    duration_seconds: int | None = None
    distance_meters: Decimal | None = None
    notes: str | None = None


class WorkoutSessionCreate(BaseModel):
    """Payload for recording a workout session."""

    name: str | None = Field(default=None, max_length=255)
    performed_at: dt.datetime
    duration_minutes: int | None = Field(default=None, ge=0, le=1440)
    notes: str | None = None
    sets: list[WorkoutSetIn] = Field(default_factory=list)


class WorkoutSessionOut(BaseModel):
    """A persisted workout session with its sets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None = None
    performed_at: dt.datetime
    duration_minutes: int | None = None
    notes: str | None = None
    created_at: dt.datetime
    sets: list[WorkoutSetOut] = Field(default_factory=list)


class MeasurementCreate(BaseModel):
    """Payload for recording a measurement."""

    type: MeasurementType
    value: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=10)
    measured_at: dt.datetime
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_unit(self) -> MeasurementCreate:
        allowed = MEASUREMENT_UNITS[self.type]
        if self.unit not in allowed:
            raise ValueError(
                f"Unit '{self.unit}' is not valid for measurement type '{self.type.value}'. "
                f"Allowed: {sorted(allowed)}."
            )
        return self


class MeasurementOut(BaseModel):
    """A persisted measurement."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: MeasurementType
    value: Decimal
    unit: str
    measured_at: dt.datetime
    notes: str | None = None
    created_at: dt.datetime
