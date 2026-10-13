"""Document metadata persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus


class DocumentRepository:
    """Persistence operations for uploaded document metadata."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        """Return a page of documents for ``user_id`` and the total count."""
        total = self._db.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )
        statement = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def get_for_user(self, document_id: UUID, user_id: UUID) -> Document | None:
        """Return a document only when it belongs to ``user_id``."""
        statement = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        return self._db.scalar(statement)

    def create(
        self,
        user_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        *,
        id: UUID | None = None,
        storage_backend: str | None = None,
        storage_key: str | None = None,
        status: DocumentStatus = DocumentStatus.PENDING,
    ) -> Document:
        """Create and persist a document metadata row."""
        document = Document(
            id=id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_backend=storage_backend,
            storage_key=storage_key,
            status=status,
        )
        self._db.add(document)
        self._db.flush()
        return document

    def delete(self, document: Document) -> None:
        """Delete a document metadata row."""
        self._db.delete(document)
        self._db.flush()
