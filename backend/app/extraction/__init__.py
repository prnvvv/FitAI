"""Structured activity / memory extraction.

This package contains a NARROWLY SCOPED extractor whose only job is to read a
user message and return validated, structured *candidates* (completed workouts,
planned workouts, progress measurements, preferences, goals, profile facts). It
never answers the user, gives fitness advice, computes results, or replaces the
primary Groq/LangGraph agent.

The LLM output is treated as untrusted input: every candidate is validated with
Pydantic and deterministic checks. The persistence layer (not this package)
decides where each candidate is durably stored.
"""

from app.extraction.extractor import GroqActivityExtractor, RecordExtractor
from app.extraction.reconciliation import (
    HISTORY_KEY,
    INSIGHTS_KEY,
    InsightDecision,
    InsightStore,
    apply_decision,
    reconcile,
)
from app.extraction.schemas import (
    CompletedWorkout,
    ExtractionResult,
    FitnessGoal,
    InsightStatus,
    MemoryInsight,
    PlannedWorkout,
    ProfileFact,
    ProgressRecord,
    ProposedAction,
    RecordedOutcome,
    UserPreference,
)

__all__ = [
    "GroqActivityExtractor",
    "RecordExtractor",
    "ExtractionResult",
    "CompletedWorkout",
    "PlannedWorkout",
    "ProgressRecord",
    "UserPreference",
    "FitnessGoal",
    "ProfileFact",
    "MemoryInsight",
    "InsightStatus",
    "ProposedAction",
    "RecordedOutcome",
    "InsightDecision",
    "InsightStore",
    "reconcile",
    "apply_decision",
    "INSIGHTS_KEY",
    "HISTORY_KEY",
]
