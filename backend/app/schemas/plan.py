"""Plan schemas."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlannedExerciseIn(BaseModel):
    """An exercise inside a planned session."""

    exercise_name: str = Field(min_length=1, max_length=200)
    target_sets: int | None = Field(default=None, ge=0, le=100)
    target_reps: int | None = Field(default=None, ge=0, le=1000)
    target_weight: Decimal | None = Field(default=None, ge=0, le=2000)
    target_weight_unit: str | None = Field(default=None, max_length=10)
    duration_seconds: int | None = Field(default=None, ge=0)
    distance_meters: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class PlannedExerciseOut(BaseModel):
    """A persisted planned exercise."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    exercise_name: str
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: Decimal | None = None
    target_weight_unit: str | None = None
    duration_seconds: int | None = None
    distance_meters: Decimal | None = None
    notes: str | None = None


class PlannedSessionCreate(BaseModel):
    """Payload for creating a planned session."""

    planned_date: dt.date
    title: str | None = Field(default=None, max_length=255)
    day_type: str = Field(default="workout", max_length=50)
    notes: str | None = Field(default=None, max_length=1000)
    exercises: list[PlannedExerciseIn] = Field(default_factory=list)


class PlannedSessionUpdate(BaseModel):
    """Payload for updating a planned session."""

    title: str | None = Field(default=None, max_length=255)
    day_type: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)
    exercises: list[PlannedExerciseIn] | None = None


class PlannedSessionOut(BaseModel):
    """A persisted planned session with its exercises."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planned_date: dt.date
    title: str | None = None
    day_type: str
    status: str
    completed_session_id: UUID | None = None
    notes: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    exercises: list[PlannedExerciseOut] = Field(default_factory=list)


class DaySummaryOut(BaseModel):
    """Per-day aggregate for plan views."""

    date: str
    planned_count: int
    completed_count: int
    day_type: str
    has_meals: bool


class ApplyTemplateIn(BaseModel):
    """Payload for applying a starter template."""

    template_key: str = Field(min_length=1)
    start_date: dt.date


class TemplateOut(BaseModel):
    """A named starter template."""

    key: str
    name: str
    days: list[dict[str, object]]
