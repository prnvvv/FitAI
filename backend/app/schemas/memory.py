"""Memory, memory history, and pending-update schemas."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MemoryChangeType, MemoryKey, MemoryStatus, PendingUpdateStatus


class MemoryOut(BaseModel):
    """A current structured memory record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: MemoryKey
    value: Any
    status: MemoryStatus
    confidence: Decimal | None = None
    source: str | None = None
    effective_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class MemoryHistoryOut(BaseModel):
    """An immutable record of a memory change."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memory_id: UUID | None = None
    key: MemoryKey
    change_type: MemoryChangeType
    previous_value: Any = None
    new_value: Any = None
    confidence: Decimal | None = None
    source: str | None = None
    effective_at: dt.datetime | None = None
    created_at: dt.datetime


class MemoryCorrectRequest(BaseModel):
    """Payload for a direct user correction of a current memory."""

    value: Any = Field(...)


class PendingUpdateCreate(BaseModel):
    """Payload for proposing a memory change (internally or by the AI layer)."""

    key: MemoryKey
    proposed_value: Any = Field(...)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)


class PendingUpdateOut(BaseModel):
    """A proposed memory change awaiting confirmation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: MemoryKey
    proposed_value: Any
    previous_value: Any = None
    confidence: Decimal | None = None
    source: str | None = None
    reason: str | None = None
    status: PendingUpdateStatus
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None
