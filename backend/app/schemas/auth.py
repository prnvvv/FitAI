"""Authentication identity schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuthMeOut(BaseModel):
    """The authenticated user's identity as known to FitAI."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None = None
    created_at: datetime
