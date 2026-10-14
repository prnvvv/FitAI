"""Model registry.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``metadata.create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.activity_event import ActivityEvent
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.enums import (
    ActivityEventType,
    ActivityLevel,
    DocumentStatus,
    MeasurementType,
    MemoryChangeType,
    MemoryKey,
    MemoryStatus,
    MessageRole,
    PendingActionStatus,
    PendingActionType,
    PendingUpdateStatus,
    WeightUnit,
)
from app.models.measurement import Measurement
from app.models.memory import Memory, MemoryHistory
from app.models.pending_action import PendingChatAction
from app.models.pending_update import PendingMemoryUpdate
from app.models.profile import Profile
from app.models.user import User
from app.models.workout import WorkoutSession, WorkoutSet

__all__ = [
    "Base",
    "ActivityEvent",
    "ActivityEventType",
    "ActivityLevel",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Measurement",
    "MeasurementType",
    "Memory",
    "MemoryChangeType",
    "MemoryHistory",
    "MemoryKey",
    "MemoryStatus",
    "Message",
    "MessageRole",
    "PendingActionStatus",
    "PendingActionType",
    "PendingChatAction",
    "PendingMemoryUpdate",
    "PendingUpdateStatus",
    "Profile",
    "User",
    "WeightUnit",
    "WorkoutSession",
    "WorkoutSet",
]
