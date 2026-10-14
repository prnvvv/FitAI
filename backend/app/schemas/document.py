"""Document metadata schemas."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    #: Short, human-readable failure reason. Never a traceback or file content.
    failure_reason: str | None = None
    #: Short note for a successful-but-empty result (e.g. "No readable text found").
    note: str | None = None
    content_hash: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    completed_at: dt.datetime | None = None
    failed_at: dt.datetime | None = None

    @classmethod
    def from_document(cls, document: object) -> DocumentOut:
        """Build the response, exposing ``error_message`` as ``failure_reason``."""
        model = cls.model_validate(document)
        model.failure_reason = getattr(document, "error_message", None)
        metadata = getattr(document, "ingestion_metadata", None) or {}
        note = metadata.get("note") if isinstance(metadata, dict) else None
        model.note = str(note) if note else None
        return model


class DocumentRename(BaseModel):
    """Payload for renaming an uploaded document."""

    filename: str = Field(min_length=1, max_length=255)
