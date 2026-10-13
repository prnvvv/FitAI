"""Chat request/response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload for sending a message to FitAI."""

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class Source(BaseModel):
    """A citation source returned with a research-backed answer."""

    index: int
    title: str
    url: str
    snippet: str = ""


class Action(BaseModel):
    """An actionable item surfaced to the user (e.g. a pending confirmation)."""

    type: str
    proposal_id: str | None = None
    key: str | None = None
    summary: str | None = None
    title: str
    description: str


class ChatResponse(BaseModel):
    """Response from FitAI for a single turn."""

    conversation_id: UUID
    response: str
    title: str | None = None
    sources: list[Source] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
