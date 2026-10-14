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
from app.extraction.schemas import (
    CompletedWorkout,
    ExtractionResult,
    FitnessGoal,
    PlannedWorkout,
    ProfileFact,
    ProgressRecord,
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
    "RecordedOutcome",
]
