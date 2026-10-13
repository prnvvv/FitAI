"""Progress-history retrieval.

This service returns raw, ownership-scoped history. It intentionally performs
only trivial aggregation; trend analysis, PR *detection*, and fitness
intelligence belong to Person 2.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import MeasurementType
from app.models.measurement import Measurement
from app.repositories.measurement_repository import MeasurementRepository
from app.repositories.workout_repository import WorkoutRepository


class ProgressService:
    """Provides historical records for progress views and analysis."""

    def __init__(self, db: Session) -> None:
        self._measurements = MeasurementRepository(db)
        self._workouts = WorkoutRepository(db)

    def measurement_series(
        self, user_id: UUID, measurement_type: MeasurementType
    ) -> list[Measurement]:
        """Return all measurements of a type in chronological order."""
        return self._measurements.series(user_id, measurement_type)

    def weight_series(self, user_id: UUID) -> list[Measurement]:
        """Return the user's weight measurements in chronological order."""
        return self._measurements.series(user_id, MeasurementType.WEIGHT)

    def exercise_max_loads(self, user_id: UUID) -> list[dict[str, object]]:
        """Return the heaviest recorded load per exercise.

        This is descriptive aggregation of stored data, not PR detection logic.
        """
        best: dict[str, dict[str, object]] = {}
        for workout_set in self._workouts.list_sets_with_load(user_id):
            weight = workout_set.weight
            if weight is None:
                continue
            current = best.get(workout_set.exercise_name)
            if current is None or Decimal(weight) > Decimal(str(current["weight"])):
                best[workout_set.exercise_name] = {
                    "exercise_name": workout_set.exercise_name,
                    "weight": weight,
                    "weight_unit": (
                        workout_set.weight_unit.value if workout_set.weight_unit else None
                    ),
                }
        return sorted(best.values(), key=lambda item: str(item["exercise_name"]))
