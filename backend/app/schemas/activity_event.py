"""Activity event schemas."""
from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActivityEventType


class ActivityEventOut(BaseModel):
    """A single activity event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ActivityEventType
    entity_type: str | None = None
    entity_id: str | None = None
    occurred_at: dt.datetime
    source: str
    payload: dict[str, object] | None = None
    created_at: dt.datetime
