"""Document upload and metadata endpoints.

Original-file storage is undecided; uploads require a configured storage
backend and otherwise fail clearly rather than silently writing to local disk.
Vector deletion is coordinated by Person 2 and is not performed here.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.config import settings
from app.core.errors import AppError, PayloadTooLargeError
from app.core.logging import get_logger
from app.models.enums import ActivityEventType
from app.rag.pipeline import IngestionPipeline
from app.rag.store_factory import build_vector_store
from app.rag.vector_store import VectorStore
from app.rag.worker import ingest_document
from app.schemas.common import Page
from app.schemas.document import DocumentOut, DocumentRename
from app.services.activity_event_service import ActivityEventService
from app.services.document_service import DocumentService
from app.services.ingestion_jobs import enqueue

router = APIRouter(prefix="/documents", tags=["documents"])

_CHUNK_SIZE = 1024 * 1024

logger = get_logger(__name__)


def _get_ingestion() -> IngestionPipeline:
    return IngestionPipeline(build_vector_store(VectorStore))


def _uses_jobs() -> bool:
    """True when ingestion is a durable, checkpointed job (Documents service)."""
    return settings.ingestion_mode.strip().lower() == "jobs"


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


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "The identical file is already in the library."}},
)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> JSONResponse:
    """Upload a document, record its metadata, and index it in the background.

    Uploading identical bytes twice returns the existing item with 200 and an
    ``X-Duplicate: true`` header instead of creating a second row. Parsing and
    embedding are slow, so the file is stored here and indexed by a background
    worker; the item stays ``pending`` until the worker updates its status.
    """
    data = await _read_upload_limited(file)
    service = DocumentService(db)
    document, is_duplicate = service.create(
        current_user.id,
        file.filename or "upload",
        file.content_type or "application/octet-stream",
        data,
        trigger_ingestion=False,
    )
    body = jsonable_encoder(DocumentOut.from_document(document))

    if is_duplicate:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=body,
            headers={"X-Duplicate": "true"},
        )

    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.DOCUMENT_ADDED,
        entity_type="document",
        entity_id=str(document.id),
        payload={"filename": document.filename, "size_bytes": document.size_bytes},
    )
    if _uses_jobs():
        # Durable path: the job row (not process memory) carries the work, so a
        # restart resumes it. The file is already in persistent storage.
        enqueue(db, document)
    else:
        background_tasks.add_task(ingest_document, current_user.id, document.id, data)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.patch("/{document_id}", response_model=DocumentOut)
def rename_document(
    document_id: UUID,
    payload: DocumentRename,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentOut:
    """Rename one of the user's documents."""
    document = DocumentService(db).rename(current_user.id, document_id, payload.filename)
    return DocumentOut.from_document(document)


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
        items=[DocumentOut.from_document(item) for item in items],
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
    return DocumentOut.from_document(document)


@router.post("/{document_id}/retry", response_model=DocumentOut)
def retry_document(
    document_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentOut:
    """Re-run ingestion for one of the user's documents."""
    if _uses_jobs():
        service = DocumentService(db)
        document = service.get(current_user.id, document_id)
        if not document.storage_key:
            raise AppError(
                "This document has no stored file, so it cannot be reprocessed. "
                "Upload it again instead."
            )
        service.reset_for_retry(document)
        enqueue(db, document, reset=True)
        return DocumentOut.from_document(document)
    document = DocumentService(db, ingestion=_get_ingestion()).retry(current_user.id, document_id)
    return DocumentOut.from_document(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a document's vectors, stored file and metadata row.

    Vector deletion runs first and is not silenced: leaving indexed chunks
    behind would keep deleted content retrievable by the owner. If it fails the
    metadata row is kept so the user can retry the deletion.
    """
    # Ownership check first: a document owned by someone else must 404.
    service = DocumentService(db)
    service.get(current_user.id, document_id)

    ingestion = _get_ingestion()
    try:
        ingestion.delete_user_document(str(current_user.id), str(document_id))
    except Exception as exc:  # noqa: BLE001 - surfaced as a clear error, never swallowed
        logger.warning(
            "document_vector_delete_failed",
            doc_id=str(document_id),
            error_type=type(exc).__name__,
        )
        raise AppError(
            "The document could not be deleted because its search index could not be "
            "cleaned up. Please try again."
        ) from exc

    service.delete(current_user.id, document_id)
    ActivityEventService(db).record(
        current_user.id,
        ActivityEventType.DOCUMENT_DELETED,
        entity_type="document",
        entity_id=str(document_id),
    )
