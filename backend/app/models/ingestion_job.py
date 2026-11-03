"""Durable document-ingestion job with a resumable checkpoint.

One row per document (``document_id`` is unique), which is what prevents duplicate
jobs. The checkpoint (``next_unit``/``next_chunk_index``) is written in the same
transaction as the batch it describes, and chunk ids are deterministic, so a
restart resumes from the checkpoint and any re-processed batch is an idempotent
upsert. Job rows never hold document content.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_STATUSES = (JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, JOB_FAILED)


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Processing state for one document's ingestion."""

    __tablename__ = "document_ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_status_lease", "status", "locked_until"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JOB_QUEUED, server_default=JOB_QUEUED
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    #: Checkpoint: 0-based index of the next page/section to process.
    next_unit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: Checkpoint: running chunk index, so chunk ids stay stable across resumes.
    next_chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Lease expiry. A running job whose lease has lapsed is reclaimable.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
