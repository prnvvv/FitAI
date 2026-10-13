"""Chat request/response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload for sending a message to FitAI."""

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Response from FitAI for a single turn."""

    conversation_id: UUID
    response: str
    title: str | None = None
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
