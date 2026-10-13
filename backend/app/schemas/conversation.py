"""Conversation and message schemas."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole


class ConversationCreate(BaseModel):
    """Payload for creating a conversation."""

    title: str | None = Field(default=None, max_length=255)


class ConversationUpdate(BaseModel):
    """Payload for renaming a conversation."""

    title: str | None = Field(default=None, max_length=255)


class ConversationOut(BaseModel):
    """Conversation representation returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class MessageCreate(BaseModel):
    """Payload used internally to persist a message."""

    role: MessageRole
    content: str = Field(min_length=1)
    metadata: dict[str, object] | None = None


class MessageOut(BaseModel):
    """Message representation returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    message_metadata: dict[str, object] | None = Field(
        default=None,
        serialization_alias="metadata",
        validation_alias="message_metadata",
    )
    created_at: dt.datetime
