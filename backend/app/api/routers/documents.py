"""Document upload and metadata endpoints.

Original-file storage is undecided; uploads require a configured storage
backend and otherwise fail clearly rather than silently writing to local disk.
Vector deletion is coordinated by Person 2 and is not performed here.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.config import settings
from app.core.errors import PayloadTooLargeError
from app.models.enums import ActivityEventType
from app.rag.pipeline import IngestionPipeline
from app.rag.worker import ingest_document
from app.schemas.common import Page
from app.schemas.document import DocumentOut
from app.services.activity_event_service import ActivityEventService
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

_CHUNK_SIZE = 1024 * 1024


async def _read_upload_limited(file: UploadFile) -> bytes:
    """Read an upload while enforcing the configured size limit."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"Files must be at most {settings.max_upload_size_mb} MB.",
                details={"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentOut:
    """Upload a document, record its metadata, and index it in the background.

    Parsing and embedding are slow and may need a one-off model download, so the
    request returns as soon as the file is stored. The document stays `pending`
    until the background worker updates its status.
    """
    data = await _read_upload_limited(file)
    service = DocumentService(db)
    document = service.create(
        current_user.id,
        file.filename or "upload",
        file.content_type or "application/octet-stream",
        data,
        trigger_ingestion=False,
    )
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.DOCUMENT_ADDED,
        entity_type="document",
        entity_id=str(document.id),
        payload={"filename": document.filename, "size_bytes": document.size_bytes},
    )
    background_tasks.add_task(ingest_document, current_user.id, document.id, data)
    return DocumentOut.model_validate(document)


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> Page[DocumentOut]:
    """List the authenticated user's documents, newest first."""
    items, total = DocumentService(db).list_documents(
        current_user.id, limit=pagination.limit, offset=pagination.offset
    )
    return Page[DocumentOut](
        items=[DocumentOut.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentOut:
    """Return one of the authenticated user's documents."""
    document = DocumentService(db).get(current_user.id, document_id)
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a document's metadata and its stored original file.

    ChromaDB vector deletion for this document must be completed by Person 2.
    """
    from app.rag.vector_store import VectorStore

    service = DocumentService(db)
    # Delete vectors before/after metadata removal is handled in service; also try to clean vectors
    ingestion = IngestionPipeline(VectorStore(persist_dir=settings.chromadb_persist_dir))
    try:
        ingestion.delete_user_document(str(current_user.id), str(document_id))
    except Exception:
        pass
    service.delete(current_user.id, document_id)
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.DOCUMENT_DELETED,
        entity_type="document",
        entity_id=str(document_id),
    )
