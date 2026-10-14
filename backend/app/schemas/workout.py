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
    MeasurementType.HEIGHT: frozenset({"cm", "in", "ft_in"}),
    MeasurementType.BODY_FAT_PERCENT: frozenset({"%"}),
    MeasurementType.CHEST: frozenset({"cm", "in"}),
    MeasurementType.WAIST: frozenset({"cm", "in"}),
    MeasurementType.HIPS: frozenset({"cm", "in"}),
    MeasurementType.ARM: frozenset({"cm", "in"}),
    MeasurementType.THIGH: frozenset({"cm", "in"}),
    MeasurementType.NECK: frozenset({"cm", "in"}),
    MeasurementType.SLEEP_HOURS: frozenset({"h"}),
    MeasurementType.WATER: frozenset({"ml", "oz", "L", "cups"}),
    MeasurementType.STEPS: frozenset({"steps"}),
    MeasurementType.RESTING_HEART_RATE: frozenset({"bpm"}),
    MeasurementType.MOOD: frozenset({"1-5"}),
    MeasurementType.ENERGY: frozenset({"1-5"}),
}


#: Plausible ranges per metric. Values outside these are rejected with a clear
#: 422 instead of being stored, so charts and BMI stay meaningful.
MEASUREMENT_RANGES: dict[MeasurementType, tuple[Decimal, Decimal]] = {
    MeasurementType.WEIGHT: (Decimal("20"), Decimal("500")),
    MeasurementType.HEIGHT: (Decimal("50"), Decimal("260")),
    MeasurementType.BODY_FAT_PERCENT: (Decimal("1"), Decimal("70")),
    MeasurementType.SLEEP_HOURS: (Decimal("0"), Decimal("24")),
    MeasurementType.WATER: (Decimal("0"), Decimal("20000")),
    MeasurementType.STEPS: (Decimal("0"), Decimal("200000")),
    MeasurementType.RESTING_HEART_RATE: (Decimal("25"), Decimal("250")),
    MeasurementType.MOOD: (Decimal("1"), Decimal("5")),
    MeasurementType.ENERGY: (Decimal("1"), Decimal("5")),
    MeasurementType.CHEST: (Decimal("30"), Decimal("250")),
    MeasurementType.WAIST: (Decimal("30"), Decimal("250")),
    MeasurementType.HIPS: (Decimal("30"), Decimal("250")),
    MeasurementType.ARM: (Decimal("10"), Decimal("90")),
    MeasurementType.THIGH: (Decimal("20"), Decimal("120")),
    MeasurementType.NECK: (Decimal("20"), Decimal("80")),
}


class MeasurementUpdate(BaseModel):
    """Correction payload for an existing measurement."""

    value: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


def metric_definitions() -> list[dict[str, object]]:
    """Static metadata for every trackable metric (label, units, bounds)."""
    labels = {
        MeasurementType.WEIGHT: "Weight",
        MeasurementType.HEIGHT: "Height",
        MeasurementType.BODY_FAT_PERCENT: "Body fat",
        MeasurementType.CHEST: "Chest",
        MeasurementType.WAIST: "Waist",
        MeasurementType.HIPS: "Hips",
        MeasurementType.ARM: "Upper arm",
        MeasurementType.THIGH: "Thigh",
        MeasurementType.NECK: "Neck",
        MeasurementType.SLEEP_HOURS: "Sleep",
        MeasurementType.WATER: "Water",
        MeasurementType.STEPS: "Steps",
        MeasurementType.RESTING_HEART_RATE: "Resting heart rate",
        MeasurementType.MOOD: "Mood",
        MeasurementType.ENERGY: "Energy",
    }
    definitions: list[dict[str, object]] = []
    for measurement_type in MeasurementType:
        low, high = MEASUREMENT_RANGES[measurement_type]
        units = sorted(MEASUREMENT_UNITS[measurement_type])
        definitions.append(
            {
                "type": measurement_type.value,
                "label": labels[measurement_type],
                "canonical_unit": units[0],
                "units": units,
                "min": low,
                "max": high,
                "derived": False,
            }
        )
    definitions.append(
        {
            "type": "bmi",
            "label": "BMI",
            "canonical_unit": "bmi",
            "units": ["bmi"],
            "min": Decimal("0"),
            "max": Decimal("100"),
            "derived": True,
        }
    )
    return definitions


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
        low, high = MEASUREMENT_RANGES[self.type]
        if not low <= self.value <= high:
            raise ValueError(
                f"{self.type.value.replace('_', ' ')} must be between {low} and {high} {self.unit}."
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
