"""Document metadata persistence."""

from __future__ import annotations

from datetime import datetime
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

    def list_all(self, user_id: UUID | None = None) -> list[Document]:
        """Return every document, optionally scoped to one user.

        Used by the library/ChromaDB reconciliation audit, which needs the whole
        picture (including other users' rows) to spot orphan vectors.
        """
        statement = select(Document).order_by(Document.created_at.asc())
        if user_id is not None:
            statement = statement.where(Document.user_id == user_id)
        return list(self._db.scalars(statement))

    def find_stuck(
        self,
        before: datetime,
        *,
        statuses: tuple[DocumentStatus, ...] = (DocumentStatus.PENDING, DocumentStatus.PROCESSING),
    ) -> list[Document]:
        """Return documents that have been queued/processing since ``before``."""
        statement = (
            select(Document)
            .where(Document.status.in_(statuses), Document.created_at < before)
            .order_by(Document.created_at.asc())
        )
        return list(self._db.scalars(statement))

    def get_by_content_hash(self, user_id: UUID, content_hash: str) -> Document | None:
        """Return this user's document with identical bytes, if there is one."""
        statement = select(Document).where(
            Document.user_id == user_id,
            Document.content_hash == content_hash,
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
        content_hash: str | None = None,
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
            content_hash=content_hash,
        )
        self._db.add(document)
        self._db.flush()
        return document

    def delete(self, document: Document) -> None:
        """Delete a document metadata row."""
        self._db.delete(document)
        self._db.flush()
