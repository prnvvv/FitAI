"""Pydantic schemas for structured extraction candidates.

Every candidate carries ``confidence`` (the LLM's own estimate, never proof) and
``source_text`` (the exact words that justify it) so provenance can be persisted
and low-confidence or unsupported candidates can be filtered out deterministically
before any database write.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.models.enums import MeasurementType
from app.schemas.workout import MEASUREMENT_RANGES, MEASUREMENT_UNITS

#: Phrases that mean "this is not a statement of current reality".
_HYPOTHETICAL_RE = re.compile(
    r"\b(if i|would|might|maybe|suppose|imagine|what if|thinking of|thinking about|could try)\b",
    re.I,
)
#: Phrases that mean "this used to be true and is not any more".
_PAST_RE = re.compile(
    r"\b(used to|no longer|stopped|quit|formerly|previously|back in|when i was)\b",
    re.I,
)
#: Hedges that weaken an otherwise explicit statement.
_UNCERTAIN_RE = re.compile(
    r"\b(about|around|roughly|approximately|approx|i think|probably|not sure|i guess|maybe)\b",
    re.I,
)


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


class InsightStatus(str, Enum):
    """Temporal status of a durable personal fact proposed by the extractor.

    Only ``CURRENT`` and ``HISTORICAL`` are treated as real user facts.
    ``PLANNED``/``HYPOTHETICAL`` statements are never persisted as current
    personal information, and ``UNCERTAIN`` statements are stored flagged so the
    backend can ask the user instead of assuming.
    """

    CURRENT = "current"
    HISTORICAL = "historical"
    PLANNED = "planned"
    HYPOTHETICAL = "hypothetical"
    UNCERTAIN = "uncertain"


class ProposedAction(str, Enum):
    """What the extraction LLM *suggests* doing. The backend decides for real."""

    CREATE = "create"
    UPDATE = "update"
    RETAIN = "retain"
    CONFIRM = "confirm"
    IGNORE = "ignore"


#: Candidate text that tries to act as an instruction, leak internals, or reach
#: across users is never a durable personal fact.
_INJECTION_RE = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above|earlier)\b|disregard\b|"
    r"reveal (your |the )?(system|prompt|instructions|api)|system\s*[:\-]|"
    r"\bapi[_ ]?key\b|\bpassword\b|\bsecret\b|\ball users\b|\bother users\b|"
    r"you are now\b|new instructions\b)",
    re.I,
)


class MemoryInsight(_Candidate):
    """A durable personal fact worth remembering across conversations.

    Covers preferences, recurring routines, habits, skills, ongoing projects /
    learning interests, decisions, and stable personal context. The LLM only
    *proposes* it: temporal status is re-derived here from the quoted evidence
    (guards only downgrade), and persistence + reconciliation is backend code.
    """

    text: str = Field(min_length=1, max_length=300)
    category: str = Field(default="personal_context", min_length=1, max_length=40)
    status: InsightStatus = InsightStatus.CURRENT
    action: ProposedAction = ProposedAction.CREATE
    #: True when the user explicitly retracted a previously stated fact
    #: ("I no longer enjoy jogging"), so the backend can supersede it safely.
    corrects: bool = False

    @field_validator("text")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("insight text is too short to be useful")
        if _INJECTION_RE.search(cleaned):
            raise ValueError("insight text looks like an instruction, not a user fact")
        return cleaned

    @model_validator(mode="after")
    def _reconcile_temporal(self) -> MemoryInsight:
        """Downgrade the model's status using the quoted evidence.

        Guards never upgrade: a model claiming ``current`` for a clearly
        hypothetical sentence is corrected here, so persistence can trust it.
        """
        span = f"{self.source_text} {self.text}"
        if _HYPOTHETICAL_RE.search(span):
            self.status = InsightStatus.HYPOTHETICAL
            self.action = ProposedAction.IGNORE
        elif _PAST_RE.search(span):
            self.status = InsightStatus.HISTORICAL
        elif self.status is InsightStatus.CURRENT and _UNCERTAIN_RE.search(span):
            self.status = InsightStatus.UNCERTAIN
            self.action = ProposedAction.CONFIRM
            self.confidence = min(self.confidence, 0.6)
        if self.status in (InsightStatus.PLANNED, InsightStatus.HYPOTHETICAL):
            self.action = ProposedAction.IGNORE
        if self.corrects:
            # A retraction is happening NOW: "I no longer enjoy jogging" states a
            # current position, not a historical fact.
            if self.status is InsightStatus.HISTORICAL:
                self.status = InsightStatus.CURRENT
            self.action = ProposedAction.UPDATE
        return self


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
    memory_insights: list[MemoryInsight] = Field(default_factory=list)
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
            or self.memory_insights
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
    "MemoryInsight",
    "InsightStatus",
    "ProposedAction",
    "ExtractionResult",
    "RecordedOutcome",
]
