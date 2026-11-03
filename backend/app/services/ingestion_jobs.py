"""Durable, restart-safe document ingestion.

Lifecycle of a job::

    queued -> running -> succeeded
                 |  ^
                 |  +-- lease expired / transient error: reclaimed with its checkpoint
                 +----> failed   (permanent error, or attempts exhausted)

* **Duplicate prevention**: ``document_ingestion_jobs.document_id`` is unique, so a
  document has at most one job; ``enqueue`` is idempotent.
* **Leases**: a worker claims a job by setting ``locked_until``. If the process is
  killed (a Render restart), the lease lapses and the next claim resumes from the
  stored checkpoint. ``FOR UPDATE SKIP LOCKED`` keeps concurrent workers safe.
* **Checkpoints**: after each bounded batch of pages, the new ``next_unit`` and
  ``next_chunk_index`` are committed with the lease extension. Chunk ids are
  deterministic, so a batch re-run after a crash is an idempotent upsert.
* **Bounded memory**: pages are extracted ``ingestion_pages_per_batch`` at a time and
  embedded in small batches by the vector store; the file is read from storage
  into a temporary file that is always removed.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import socket
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ingestion_job import (
    JOB_FAILED,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    IngestionJob,
)
from app.rag.chunker import chunk_sections
from app.rag.loader import DocumentLoadError
from app.rag.page_source import PageSource
from app.rag.vector_store import USER_COLLECTION
from app.services.document_service import readable_failure

logger = get_logger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MAX_CHUNKS = 2000
_RETRY_BACKOFF_SECONDS = 15
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def enqueue(db: Session, document: Document, *, reset: bool = False) -> IngestionJob:
    """Create the document's job, or return the existing one (idempotent).

    ``reset=True`` (explicit retry) rewinds a finished/failed job to a fresh
    attempt from page 0. A job that is currently running is never reset.
    """
    job = db.scalar(select(IngestionJob).where(IngestionJob.document_id == document.id))
    if job is None:
        job = IngestionJob(
            document_id=document.id,
            user_id=document.user_id,
            status=JOB_QUEUED,
            max_attempts=settings.ingestion_max_attempts,
        )
        db.add(job)
    elif reset and job.status != JOB_RUNNING:
        job.status = JOB_QUEUED
        job.attempts = 0
        job.next_unit = 0
        job.next_chunk_index = 0
        job.total_units = None
        job.locked_until = None
        job.locked_by = None
        job.last_error = None
        job.completed_at = None
    db.commit()
    db.refresh(job)
    return job


def claim_next(
    db: Session, *, worker_id: str = WORKER_ID, now: datetime | None = None
) -> UUID | None:
    """Claim one runnable job and return its id, or ``None`` when there is none.

    Runnable means ``queued`` (and not backing off) or ``running`` with an expired
    lease (the previous worker died). A job out of attempts is failed instead.
    """
    moment = now or _utcnow()
    stmt = (
        select(IngestionJob)
        .where(
            or_(
                (IngestionJob.status == JOB_QUEUED)
                & or_(IngestionJob.locked_until.is_(None), IngestionJob.locked_until <= moment),
                (IngestionJob.status == JOB_RUNNING) & (IngestionJob.locked_until <= moment),
            )
        )
        .order_by(IngestionJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalar(stmt)
    if job is None:
        db.rollback()
        return None
    if job.attempts >= job.max_attempts:
        _fail(db, job, "Processing was interrupted too many times. Try again or delete this file.")
        return None
    job.status = JOB_RUNNING
    job.attempts += 1
    job.locked_by = worker_id
    job.locked_until = moment + timedelta(seconds=settings.ingestion_lease_seconds)
    db.commit()
    return job.id


def _set_document_status(
    db: Session, document: Document | None, status: DocumentStatus, error: str | None = None
) -> None:
    if document is None:
        return
    document.status = status
    now = _utcnow()
    if status == DocumentStatus.PROCESSING:
        document.error_message = None
        document.failed_at = None
    elif status == DocumentStatus.INDEXED:
        document.completed_at = now
        document.error_message = None
    elif status == DocumentStatus.FAILED:
        document.failed_at = now
        document.error_message = (error or "")[:500] or None


def _fail(db: Session, job: IngestionJob, reason: str) -> None:
    job.status = JOB_FAILED
    job.last_error = reason[:500]
    job.locked_until = None
    job.locked_by = None
    _set_document_status(db, db.get(Document, job.document_id), DocumentStatus.FAILED, reason)
    db.commit()


def _release_for_retry(db: Session, job: IngestionJob, reason: str) -> None:
    """Return a job to the queue (checkpoint kept) after a transient failure."""
    if job.attempts >= job.max_attempts:
        _fail(db, job, reason)
        return
    job.status = JOB_QUEUED
    job.last_error = reason[:500]
    job.locked_by = None
    job.locked_until = _utcnow() + timedelta(seconds=_RETRY_BACKOFF_SECONDS * job.attempts)
    db.commit()


@dataclass
class JobDeps:
    """Collaborators injected so the processor is testable without Supabase/pgvector."""

    session_factory: Callable[[], Session]
    storage: Any  # DocumentStorage
    store: Any  # VectorStore | PgVectorStore
    pages_per_batch: int = 5


def process_job(
    deps: JobDeps, job_id: UUID, *, on_batch: Callable[[int], None] | None = None
) -> str:
    """Run (or resume) one claimed job; returns the resulting job status.

    Never raises: every outcome is recorded on the job and document rows.
    ``on_batch`` is a test hook invoked after each committed checkpoint.
    """
    db = deps.session_factory()
    tmp_path: Path | None = None
    try:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return JOB_FAILED
        document = db.get(Document, job.document_id)
        if document is None:
            _fail(db, job, "The document no longer exists.")
            return JOB_FAILED
        _set_document_status(db, document, DocumentStatus.PROCESSING)
        db.commit()
        owner = str(job.user_id)
        doc_id = str(document.id)

        try:
            data = deps.storage.read(document.storage_key or "")
            suffix = Path(document.filename).suffix.lower()
            fd, name = tempfile.mkstemp(suffix=suffix, prefix="fitai-ingest-")
            tmp_path = Path(name)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            del data  # drop the in-memory copy; the rest streams from the temp file
            source = PageSource(tmp_path)
        except DocumentLoadError as exc:
            _fail(db, job, readable_failure(str(exc)))
            return JOB_FAILED
        except Exception as exc:  # noqa: BLE001 - storage outage etc. is transient
            logger.warning("ingestion_read_failed", doc_id=doc_id, error_type=type(exc).__name__)
            _release_for_retry(db, job, "The stored file could not be read.")
            return job.status

        prefix = hashlib.sha256(owner.encode()).hexdigest()[:12] + ":"
        meta = {
            "scope": "user",
            "owner_id": owner,
            "storage_key": document.storage_key,
            "content_type": document.content_type,
        }
        try:
            job.total_units = source.total_units
            if job.next_unit == 0:
                # Fresh attempt: drop any stale chunks of an earlier version.
                deps.store.delete_document(USER_COLLECTION, doc_id, owner)
            while job.next_unit < source.total_units:
                sections = source.sections(job.next_unit, deps.pages_per_batch)
                chunks = chunk_sections(
                    sections,
                    document.filename,
                    source.file_type,
                    doc_id,
                    meta,
                    CHUNK_SIZE,
                    CHUNK_OVERLAP,
                    prefix,
                    start_index=job.next_chunk_index,
                    max_chunks=MAX_CHUNKS,
                )
                if chunks:
                    deps.store.add_chunks(USER_COLLECTION, chunks, owner)
                job.next_chunk_index += len(chunks)
                job.next_unit = min(job.next_unit + deps.pages_per_batch, source.total_units)
                job.locked_until = _utcnow() + timedelta(seconds=settings.ingestion_lease_seconds)
                db.commit()  # checkpoint: batch + progress become durable together
                if on_batch is not None:
                    on_batch(job.next_unit)
        except (DocumentLoadError, ValueError) as exc:
            db.rollback()
            job = db.get(IngestionJob, job_id)
            if job is None:
                return _abandon_deleted(deps, doc_id, owner)
            _fail(db, job, readable_failure(str(exc)))
            return JOB_FAILED
        except Exception as exc:  # noqa: BLE001 - embedding/vector outage is transient
            db.rollback()
            logger.warning("ingestion_batch_failed", doc_id=doc_id, error_type=type(exc).__name__)
            job = db.get(IngestionJob, job_id)
            if job is None:
                return _abandon_deleted(deps, doc_id, owner)
            _release_for_retry(db, job, "Indexing hit a temporary problem and will be retried.")
            return job.status

        if job.next_chunk_index == 0:
            _fail(db, job, readable_failure("no extractable text in this file"))
            return JOB_FAILED
        job.status = JOB_SUCCEEDED
        job.last_error = None
        job.completed_at = _utcnow()
        job.locked_until = None
        job.locked_by = None
        _set_document_status(db, document, DocumentStatus.INDEXED)
        db.commit()
        logger.info("ingestion_completed", doc_id=doc_id, chunks=job.next_chunk_index)
        return JOB_SUCCEEDED
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        db.close()


def _abandon_deleted(deps: JobDeps, doc_id: str, owner: str) -> str:
    """The document was deleted mid-ingestion: remove any vectors written so far."""
    try:
        deps.store.delete_document(USER_COLLECTION, doc_id, owner)
    except Exception:  # noqa: BLE001 - logged; a later audit/orphan sweep can retry
        logger.warning("ingestion_orphan_cleanup_failed", doc_id=doc_id, exc_info=True)
    return JOB_FAILED


def enqueue_orphans(db: Session) -> int:
    """Create jobs for ``pending``/``processing`` documents that have none.

    Covers an upload whose request died between saving the document and creating
    its job. Returns the number of jobs created.
    """
    stmt = (
        select(Document)
        .outerjoin(IngestionJob, IngestionJob.document_id == Document.id)
        .where(
            IngestionJob.id.is_(None),
            Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]),
            Document.storage_key.is_not(None),
        )
    )
    documents = list(db.scalars(stmt))
    for document in documents:
        enqueue(db, document)
    return len(documents)
