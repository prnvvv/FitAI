"""Background ingestion for uploaded documents.

Parsing and embedding are slow and can require a one-off model download, so the
upload request must never wait for them. The API stores metadata and returns
immediately; this worker indexes the document afterwards and records the result
through ``DocumentService.ingest`` so status handling is shared with the request
path.

The worker owns its own database session because the request-scoped session is
closed once the response is sent.
"""

from __future__ import annotations

import contextlib
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import DocumentStatus
from app.services.document_service import DocumentService

logger = get_logger(__name__)


def _mark_failed(service: DocumentService, user_id: UUID, document_id: UUID, reason: str) -> None:
    with contextlib.suppress(Exception):
        service.mark_status(user_id, document_id, DocumentStatus.FAILED, error_message=reason[:500])


def ingest_document(user_id: UUID, document_id: UUID, data: bytes) -> None:
    """Index one uploaded document and update its status.

    Never raises: a failed background job must not surface as a server error,
    but the document must be left in a truthful ``failed`` state. Status
    transitions and user-readable failure reasons are owned by
    ``DocumentService`` so the worker and the request path behave identically.
    """
    from app.db.session import SessionLocal
    from app.rag.pipeline import IngestionPipeline
    from app.rag.vector_store import VectorStore

    db = SessionLocal()
    try:
        service = DocumentService(db)
        try:
            document = service.get(user_id, document_id)
        except Exception as exc:  # noqa: BLE001 - deleted before indexing finished
            logger.warning("document_ingestion_skipped", doc_id=str(document_id), error=str(exc))
            return

        if document.status == DocumentStatus.INDEXED:
            return

        try:
            pipeline = IngestionPipeline(VectorStore(persist_dir=settings.chromadb_persist_dir))
        except Exception as exc:  # noqa: BLE001
            logger.error("document_ingestion_crashed", doc_id=str(document_id), error=str(exc))
            _mark_failed(service, user_id, document_id, "Ingestion failed")
            return

        try:
            DocumentService(db, ingestion=pipeline).ingest(user_id, document_id, data)
        except Exception as exc:  # noqa: BLE001 - reported and recorded, never raised
            logger.warning("document_ingestion_failed", doc_id=str(document_id), error=str(exc))
            _mark_failed(service, user_id, document_id, str(exc) or "Ingestion failed")
    finally:
        db.close()
