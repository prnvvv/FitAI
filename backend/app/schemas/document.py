"""Document metadata schemas."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus


class DocumentOut(BaseModel):
    """Authoritative document metadata and processing status."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_backend: str | None = None
    status: DocumentStatus
    error_message: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    completed_at: dt.datetime | None = None
    failed_at: dt.datetime | None = None
