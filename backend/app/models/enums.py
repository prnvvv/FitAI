"""Enum types shared across the persistence layer.

Enums are declared as ``str`` subclasses so that their values are usable
directly in JSON and Pydantic schemas. They are stored as VARCHAR columns with
a CHECK constraint (``native_enum=False``) to keep migrations portable.
"""

from __future__ import annotations

import enum


class MessageRole(str, enum.Enum):
    """Role of a persisted conversation message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ActivityLevel(str, enum.Enum):
    """Self-reported general activity level."""

    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class WeightUnit(str, enum.Enum):
    """Supported units for a recorded load."""

    KG = "kg"
    LB = "lb"


class MemoryKey(str, enum.Enum):
    """Provisional registry of structured memory facts.

    NOTE: This taxonomy is provisional and must be confirmed with Person 2
    before it is treated as frozen. Unknown keys are rejected rather than
    stored as arbitrary JSON.
    """

    WEIGHT = "weight"
    HEIGHT = "height"
    GOAL = "goal"
    DIETARY_PREFERENCES = "dietary_preferences"
    DIETARY_RESTRICTIONS = "dietary_restrictions"
    ACTIVITY_LEVEL = "activity_level"
    SUPPLEMENTS = "supplements"
    EXPERIENCE_LEVEL = "experience_level"
    WORKOUT_FREQUENCY = "workout_frequency"


class MemoryStatus(str, enum.Enum):
    """Lifecycle state of a current memory record."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class MemoryChangeType(str, enum.Enum):
    """Reason a memory history row was created."""

    CREATE = "create"
    UPDATE = "update"
    CORRECTION = "correction"
    SUPERSEDE = "supersede"
    DELETE = "delete"


class PendingUpdateStatus(str, enum.Enum):
    """Lifecycle state of a pending memory update proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DocumentStatus(str, enum.Enum):
    """Processing state of an uploaded document.

    Provisional vocabulary; ingestion is driven by Person 2. Person 1 owns the
    authoritative status value.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class MeasurementType(str, enum.Enum):
    """Supported body measurement types."""

    WEIGHT = "weight"
    HEIGHT = "height"
    BODY_FAT_PERCENT = "body_fat_percent"
    CHEST = "chest"
    WAIST = "waist"
    HIPS = "hips"
    ARM = "arm"
    THIGH = "thigh"
    NECK = "neck"
    SLEEP_HOURS = "sleep_hours"
    WATER = "water"
    STEPS = "steps"
    RESTING_HEART_RATE = "resting_heart_rate"
    MOOD = "mood"
    ENERGY = "energy"


class ActivityEventType(str, enum.Enum):
    """Types of user-facing activity events."""

    SESSION_COMPLETED = "session_completed"
    SESSION_PLANNED = "session_planned"
    PLAN_EDITED = "plan_edited"
    MEAL_LOGGED = "meal_logged"
    METRIC_LOGGED = "metric_logged"
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_DELETED = "document_deleted"
    PROFILE_UPDATED = "profile_updated"
