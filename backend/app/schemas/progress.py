"""Progress-retrieval schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import WeightUnit


class ExerciseMaxLoadOut(BaseModel):
    """Heaviest recorded load for an exercise (descriptive aggregation only)."""

    exercise_name: str
    weight: Decimal
    weight_unit: WeightUnit | None = None
