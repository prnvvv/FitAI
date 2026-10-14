"""Exercise library schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExerciseOut(BaseModel):
    """A canonical or custom exercise entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    primary_muscle_group: str | None = None
    equipment: str | None = None
    movement_type: str | None = None
    unit_mode: str
    is_custom: bool


class ExerciseCreate(BaseModel):
    """Payload for creating a custom exercise."""

    name: str = Field(min_length=1, max_length=200)
    primary_muscle_group: str | None = Field(default=None, max_length=100)
    equipment: str | None = Field(default=None, max_length=100)
    movement_type: str | None = Field(default=None, max_length=50)
    unit_mode: str = Field(default="reps_weight", max_length=50)
