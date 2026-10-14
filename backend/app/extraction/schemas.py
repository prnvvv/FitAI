"""Pydantic schemas for structured extraction candidates.

Every candidate carries ``confidence`` (the LLM's own estimate, never proof) and
``source_text`` (the exact words that justify it) so provenance can be persisted
and low-confidence or unsupported candidates can be filtered out deterministically
before any database write.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.enums import MeasurementType
from app.schemas.workout import MEASUREMENT_RANGES, MEASUREMENT_UNITS


class _Candidate(BaseModel):
    """Fields shared by every extraction candidate."""

    confidence: float = Field(default=0.0, ge=0, le=1)
    source_text: str = Field(default="", max_length=500)


class CompletedWorkout(_Candidate):
    """An activity the user explicitly says they already completed."""

    activity: str = Field(min_length=1, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=0, le=1440)
    performed_on: date | None = None
    distance_meters: float | None = Field(default=None, ge=0)


class PlannedWorkout(_Candidate):
    """An activity the user intends to do in the future (not yet done)."""

    activity: str = Field(min_length=1, max_length=80)
    planned_on: date | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=1440)


class ProgressRecord(_Candidate):
    """A body measurement explicitly reported by the user."""

    measurement_type: MeasurementType
    value: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=10)
    measured_on: date | None = None

    @field_validator("unit")
    @classmethod
    def _unit_ok(cls, unit: str, info: ValidationInfo) -> str:
        mtype = info.data.get("measurement_type")
        if isinstance(mtype, MeasurementType):
            allowed = MEASUREMENT_UNITS.get(mtype, frozenset())
            if unit not in allowed:
                raise ValueError(
                    f"unit {unit!r} is not valid for {mtype.value}; allowed {sorted(allowed)}"
                )
        return unit

    @field_validator("value")
    @classmethod
    def _value_in_range(cls, value: float, info: ValidationInfo) -> float:
        mtype = info.data.get("measurement_type")
        if isinstance(mtype, MeasurementType) and mtype in MEASUREMENT_RANGES:
            low, high = MEASUREMENT_RANGES[mtype]
            if not Decimal(str(value)) <= high or not Decimal(str(value)) >= low:
                raise ValueError(f"{mtype.value} must be between {low} and {high}")
        return value


class UserPreference(_Candidate):
    """A stated personal preference (e.g. enjoys an activity)."""

    preference: str = Field(min_length=1, max_length=200)


class FitnessGoal(_Candidate):
    """A stated fitness goal (e.g. build chest muscle)."""

    goal: str = Field(min_length=1, max_length=200)


class ProfileFact(_Candidate):
    """Relevant explicit personal information about the user."""

    text: str = Field(min_length=1, max_length=300)


class ExtractionResult(BaseModel):
    """Validated candidates from one message.

    Empty arrays mean "nothing of that kind was identified". ``error`` is set
    only when the extraction provider itself failed; callers must treat that as
    "no records were extracted" rather than a failure to record.
    """

    completed_workouts: list[CompletedWorkout] = Field(default_factory=list)
    planned_workouts: list[PlannedWorkout] = Field(default_factory=list)
    progress_records: list[ProgressRecord] = Field(default_factory=list)
    user_preferences: list[UserPreference] = Field(default_factory=list)
    fitness_goals: list[FitnessGoal] = Field(default_factory=list)
    profile_facts: list[ProfileFact] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    error: str | None = None

    def has_any(self) -> bool:
        """True when at least one valid candidate was extracted."""
        return bool(
            self.completed_workouts
            or self.planned_workouts
            or self.progress_records
            or self.user_preferences
            or self.fitness_goals
            or self.profile_facts
        )


class RecordedOutcome(BaseModel):
    """Result of persisting one candidate, reported only after durable commit."""

    model_config = ConfigDict(use_enum_values=True)

    kind: str  # completed_workout | planned_workout | progress_record | user_preference | profile_fact
    # saved = durably committed; duplicate = already present (idempotent);
    # failed = the write did not commit; skipped = intentionally not persisted here.
    status: str
    record_id: str | None = None
    summary: str = ""
    detail: str | None = None


__all__ = [
    "CompletedWorkout",
    "PlannedWorkout",
    "ProgressRecord",
    "UserPreference",
    "FitnessGoal",
    "ProfileFact",
    "ExtractionResult",
    "RecordedOutcome",
]
