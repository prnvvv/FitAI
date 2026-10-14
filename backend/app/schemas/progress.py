"""Progress-retrieval schemas."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import WeightUnit


class BmiPointOut(BaseModel):
    """One derived BMI value paired with the height used to compute it."""

    measured_at: dt.datetime
    value: Decimal
    unit: str
    source: str
    weight_kg: Decimal
    height_cm: Decimal


class WeeklySessionsOut(BaseModel):
    """Sessions completed in one Monday-start week."""

    week_of: dt.date
    sessions: int


class PersonalRecordOut(BaseModel):
    """Heaviest recorded load for an exercise in the window."""

    exercise_name: str
    weight: Decimal
    weight_unit: WeightUnit | None = None
    achieved_on: dt.date


class DerivedMetricsOut(BaseModel):
    """Metrics computed from logged and planned sessions. Never stored."""

    window: dict[str, str]
    sessions_completed: int
    active_days: int
    sessions_per_week: float
    weekly_sessions: list[WeeklySessionsOut] = Field(default_factory=list)
    total_volume_kg: float
    personal_records: list[PersonalRecordOut] = Field(default_factory=list)
    current_streak_days: int
    longest_streak_days: int
    planned_sessions: int
    planned_completed: int
    planned_completion_rate: float | None = None
    source: str


class ExerciseMaxLoadOut(BaseModel):
    """Heaviest recorded load for an exercise (descriptive aggregation only)."""

    exercise_name: str
    weight: Decimal
    weight_unit: WeightUnit | None = None
