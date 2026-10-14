"""Document ingestion lifecycle: status transitions, retry and deletion."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.enums import DocumentStatus
from app.services.document_service import DocumentService
from app.services.document_storage import LocalDocumentStorage

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _FakeResult:
    def __init__(self, status: str, error: str | None = None) -> None:
        self.status = status
        self.error = error


class _FakeIngestion:
    """Records calls and returns a scripted result (or raises)."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str]] = []

    def ingest_user_document_bytes(
        self, data: bytes, filename: str, user_id: str, doc_id: str | None = None, **_: object
    ) -> Any:
        self.calls.append((filename, doc_id or ""))
        outcome = self.outcomes.pop(0) if self.outcomes else _FakeResult("indexed")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _service(db_session, tmp_path, ingestion) -> DocumentService:
    return DocumentService(
        db_session, storage=LocalDocumentStorage(str(tmp_path)), ingestion=ingestion
    )


def test_ingestion_progresses_queued_reading_ready(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([_FakeResult("indexed")])
    document = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.jpg", "image/jpeg", JPEG
    )

    assert ingestion.calls == [("plan.jpg", str(document.id))]
    assert document.status == DocumentStatus.INDEXED
    assert document.error_message is None


def test_ingestion_failure_stores_a_readable_reason(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([_FakeResult("failed", "no extractable text in image")])
    document = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.jpg", "image/jpeg", JPEG
    )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "no extractable text in image"
    assert document.failed_at is not None


def test_ingestion_exception_is_turned_into_a_failure_status(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([RuntimeError("chroma unavailable")])
    document = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.png", "image/png", PNG
    )

    assert document.status == DocumentStatus.FAILED
    assert "chroma unavailable" in (document.error_message or "")


def test_retry_reprocesses_a_failed_document(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    ingestion = _FakeIngestion([_FakeResult("failed", "vision model timed out")])
    service = _service(db_session, tmp_path, ingestion)
    document = service.create(user_id, "photo.jpg", "image/jpeg", JPEG)
    assert document.status == DocumentStatus.FAILED

    ingestion.outcomes = [_FakeResult("indexed")]
    retried = service.retry(user_id, document.id)

    assert retried.status == DocumentStatus.INDEXED
    assert retried.error_message is None
    assert len(ingestion.calls) == 2
    # The metadata row and stored file are preserved.
    assert service.list_documents(user_id, limit=10, offset=0)[1] == 1


def test_retry_of_another_users_document_is_404(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([_FakeResult("indexed")])
    service = _service(db_session, tmp_path, ingestion)
    document = service.create(uuid.uuid4(), "notes.txt", "text/plain", b"hello")

    import pytest

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.retry(uuid.uuid4(), document.id)


def test_delete_removes_row_and_stored_file(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    service = _service(db_session, tmp_path, _FakeIngestion([]))
    document = service.create(user_id, "notes.txt", "text/plain", b"hello", trigger_ingestion=False)

    service.delete(user_id, document.id)

    assert not (tmp_path / document.storage_key).exists()
    assert service.list_documents(user_id, limit=10, offset=0)[1] == 0


def test_upload_allowlist_comes_from_the_ingestion_registry(db_session, tmp_path) -> None:
    import app.services.document_service as document_service
    from app.rag.loader import SUPPORTED_EXTENSIONS

    assert set(SUPPORTED_EXTENSIONS) == document_service.ALLOWED_EXTENSIONS
    assert "image/jpeg" in document_service.ALLOWED_CONTENT_TYPES
    assert "application/pdf" in document_service.ALLOWED_CONTENT_TYPES
    assert ".exe" not in document_service.ALLOWED_EXTENSIONS
