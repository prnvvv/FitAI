"""Document metadata and processing-status business logic.

Person 1 owns authoritative metadata and status. Person 2 owns parsing and
indexing. Vector deletion in ChromaDB is *not* performed here and must be
coordinated by Person 2.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AppError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.rag.loader import FILE_HANDLERS, SUPPORTED_EXTENSIONS
from app.repositories.document_repository import DocumentRepository
from app.services.document_storage import DocumentStorage, get_document_storage

#: Derived from the ingestion registry so uploads and ingestion can never disagree.
ALLOWED_CONTENT_TYPES = {
    media_type for handler in FILE_HANDLERS.values() for media_type in handler.media_types
}
ALLOWED_EXTENSIONS = set(SUPPORTED_EXTENSIONS)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Ingestion failures that are meaningful to a user, mapped to calm copy. The
#: stored reason is short and never contains a traceback, file content or secrets.
FAILURE_COPY: dict[str, str] = {
    "unsupported file type": "Unsupported file type.",
    "content does not match": "Couldn't read this file.",
    "file is empty": "This file is empty.",
    "file too large": "File too large.",
    "no extractable text": "No readable text was found in that file.",
    "password-protected": "That PDF is password-protected.",
    "image reading isn't available": "Image reading isn't available right now.",
    "couldn't read this image": "Couldn't read this image.",
}
DEFAULT_FAILURE_REASON = "This file could not be processed."


def readable_failure(exc: BaseException | str) -> str:
    """Turn an ingestion failure into a short, user-readable reason."""
    from app.rag.loader import DocumentLoadError

    message = exc if isinstance(exc, str) else str(exc).strip()
    if isinstance(exc, DocumentLoadError) or message:
        lowered = message.lower()
        for needle, copy in FAILURE_COPY.items():
            if needle in lowered:
                return copy
    return DEFAULT_FAILURE_REASON


class DocumentService:
    """Coordinates document uploads, metadata, and status transitions."""

    def __init__(
        self, db: Session, storage: DocumentStorage | None = None, ingestion: Any = None
    ) -> None:
        self._db = db
        self._storage = storage or get_document_storage()
        self._documents = DocumentRepository(db)
        self._ingestion = ingestion

    def list_documents(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        """Return a page of the user's documents."""
        return self._documents.list_for_user(user_id, limit=limit, offset=offset)

    def get(self, user_id: UUID, document_id: UUID) -> Document:
        """Return the user's document or raise NotFoundError."""
        document = self._documents.get_for_user(document_id, user_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    def create(
        self,
        user_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
        *,
        trigger_ingestion: bool = True,
    ) -> tuple[Document, bool]:
        """Validate and store an uploaded document, then record its metadata.

        Returns ``(document, is_duplicate)``. When the same bytes are already in
        this user's library the existing row is returned unchanged instead of
        creating a second item.
        """
        self._validate_upload(filename, content_type, len(data))

        content_hash = hashlib.sha256(data).hexdigest()
        existing = self._documents.get_by_content_hash(user_id, content_hash)
        if existing is not None:
            return existing, True

        document_id = uuid4()
        key = f"{user_id}/{document_id}"
        self._storage.save(key, data, content_type)

        try:
            document = self._documents.create(
                user_id,
                filename,
                content_type,
                len(data),
                id=document_id,
                storage_backend=self._storage.backend_name,
                storage_key=key,
                status=DocumentStatus.PENDING,
                content_hash=content_hash,
            )
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            self._remove_stored(key)
            raise AppError("The document metadata could not be saved.") from exc

        self._db.refresh(document)

        if trigger_ingestion:
            self._ingest(document, data)

        return document, False

    def rename(self, user_id: UUID, document_id: UUID, filename: str) -> Document:
        """Rename one of the user's documents without touching the stored bytes."""
        cleaned = filename.strip()
        if not cleaned or len(cleaned) > 255:
            raise ValidationError("The file name must be between 1 and 255 characters.")
        document = self.get(user_id, document_id)
        document.filename = cleaned
        self._commit()
        self._db.refresh(document)
        return document

    def retry(self, user_id: UUID, document_id: UUID) -> Document:
        """Re-run ingestion for a stored document, resetting its status.

        Used when a previous attempt failed (for example a vision/OCR outage).
        The metadata row and the stored file are preserved; only the processing
        status and the ChromaDB chunks are rewritten.
        """
        document = self.get(user_id, document_id)
        if not document.storage_key:
            raise AppError(
                "This document has no stored file, so it cannot be reprocessed. "
                "Upload it again instead."
            )
        data = self._storage.read(document.storage_key)
        document.error_message = None
        document.failed_at = None
        self._commit()
        self._db.refresh(document)
        return self._ingest(document, data)

    def _ingest(self, document: Document, data: bytes) -> Document:
        """Run the ingestion pipeline and record a readable terminal status.

        Status always progresses queued -> reading -> ready|failed, and a failure
        stores a human-readable reason on the record instead of raising.
        """
        if self._ingestion is None:
            return document

        self.mark_status(document.user_id, document.id, DocumentStatus.PROCESSING)
        try:
            result = self._ingestion.ingest_user_document_bytes(
                data,
                document.filename,
                str(document.user_id),
                str(document.id),
                metadata={
                    "storage_key": document.storage_key,
                    "content_type": document.content_type,
                },
            )
        except Exception as exc:  # noqa: BLE001 - ingestion is best-effort; status records why
            from app.core.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(
                "document_ingestion_failed",
                doc_id=str(document.id),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            with suppress(Exception):
                self.mark_status(
                    document.user_id,
                    document.id,
                    DocumentStatus.FAILED,
                    error_message=readable_failure(exc),
                )
            self._db.refresh(document)
            return document

        if result.status == "indexed":
            self.mark_status(document.user_id, document.id, DocumentStatus.INDEXED)
        else:
            self.mark_status(
                document.user_id,
                document.id,
                DocumentStatus.FAILED,
                error_message=readable_failure(result.error or ""),
            )
        self._db.refresh(document)
        return document

    def delete(self, user_id: UUID, document_id: UUID) -> None:
        """Delete document metadata and the stored original file.

        The stored file is removed before the metadata row so that a metadata
        failure leaves a recoverable state (the row can be deleted again).
        ChromaDB vectors are not removed here; Person 2 must delete vectors for
        this document as a coordinated step.
        """
        document = self.get(user_id, document_id)
        storage_key = document.storage_key

        if storage_key:
            self._remove_stored(storage_key)

        self._documents.delete(document)
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The document could not be deleted.") from exc

    def mark_status(
        self,
        user_id: UUID,
        document_id: UUID,
        status: DocumentStatus,
        *,
        error_message: str | None = None,
    ) -> Document:
        """Update processing status.

        Shared interface for Person 2's ingestion pipeline.
        """
        document = self.get(user_id, document_id)
        document.status = status
        if status == DocumentStatus.PROCESSING:
            document.error_message = None
            document.failed_at = None
        elif status == DocumentStatus.INDEXED:
            document.completed_at = _utcnow()
            document.error_message = None
        elif status == DocumentStatus.FAILED:
            document.failed_at = _utcnow()
            document.error_message = (error_message or "")[:500] or None
        self._commit()
        self._db.refresh(document)
        return document

    def _validate_upload(self, filename: str, content_type: str, size: int) -> None:
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if size <= 0:
            raise UnsupportedMediaTypeError("The uploaded file is empty.")
        if size > max_bytes:
            raise PayloadTooLargeError(
                f"Files must be at most {settings.max_upload_size_mb} MB.",
                details={"max_bytes": max_bytes},
            )
        suffix = ""
        if "." in filename:
            suffix = filename[filename.rfind(".") :].lower()
        if content_type not in ALLOWED_CONTENT_TYPES and suffix not in ALLOWED_EXTENSIONS:
            raise UnsupportedMediaTypeError(
                "Only PDF, TXT, MD, DOCX, PNG, JPG and WEBP files are supported.",
                details={"content_type": content_type},
            )

    def _remove_stored(self, key: str) -> None:
        try:
            self._storage.delete(key)
        except Exception as exc:  # noqa: BLE001 - surface deletion failures explicitly
            raise AppError("The stored document file could not be removed.") from exc

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The document could not be saved.") from exc
