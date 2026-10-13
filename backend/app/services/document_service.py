"""Document metadata and processing-status business logic.

Person 1 owns authoritative metadata and status. Person 2 owns parsing and
indexing. Vector deletion in ChromaDB is *not* performed here and must be
coordinated by Person 2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AppError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.document_storage import DocumentStorage, get_document_storage

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/webp",
}
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".png", ".jpg", ".jpeg", ".webp"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentService:
    """Coordinates document uploads, metadata, and status transitions."""

    def __init__(self, db: Session, storage: DocumentStorage | None = None) -> None:
        self._db = db
        self._storage = storage or get_document_storage()
        self._documents = DocumentRepository(db)

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
    ) -> Document:
        """Validate and store an uploaded document, then record its metadata."""
        self._validate_upload(filename, content_type, len(data))

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
            )
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            self._remove_stored(key)
            raise AppError("The document metadata could not be saved.") from exc

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
        if status == DocumentStatus.INDEXED:
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
