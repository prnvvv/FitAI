"""Document ingestion lifecycle: status transitions, retry and deletion."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.enums import DocumentStatus
from app.services.document_service import DocumentService
from app.services.document_storage import LocalDocumentStorage

TEXT_CONTENT = b"hello world, this is a test document"


class _FakeResult:
    def __init__(self, status: str, error: str | None = None, note: str | None = None) -> None:
        self.status = status
        self.error = error
        self.note = note


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
    document, _dup = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.txt", "text/plain", TEXT_CONTENT
    )

    assert ingestion.calls == [("plan.txt", str(document.id))]
    assert document.status == DocumentStatus.INDEXED
    assert document.error_message is None


def test_ingestion_failure_stores_a_readable_reason(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([_FakeResult("failed", "no extractable text in this file")])
    document, _dup = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.txt", "text/plain", TEXT_CONTENT
    )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "No readable text was found in that file."
    assert document.failed_at is not None


def test_ingestion_exception_is_turned_into_a_failure_status(db_session, tmp_path) -> None:
    ingestion = _FakeIngestion([RuntimeError("chroma unavailable")])
    document, _dup = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "plan.md", "text/markdown", TEXT_CONTENT
    )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "This file could not be processed."


def test_retry_reprocesses_a_failed_document(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    ingestion = _FakeIngestion([_FakeResult("failed", "vision model timed out")])
    service = _service(db_session, tmp_path, ingestion)
    document, _dup = service.create(user_id, "notes.txt", "text/plain", TEXT_CONTENT)
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
    document, _dup = service.create(uuid.uuid4(), "notes.txt", "text/plain", TEXT_CONTENT)

    import pytest

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.retry(uuid.uuid4(), document.id)


def test_delete_removes_row_and_stored_file(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    service = _service(db_session, tmp_path, _FakeIngestion([]))
    document, _dup = service.create(
        user_id, "notes.txt", "text/plain", TEXT_CONTENT, trigger_ingestion=False
    )

    service.delete(user_id, document.id)

    assert not (tmp_path / document.storage_key).exists()
    assert service.list_documents(user_id, limit=10, offset=0)[1] == 0


def test_upload_allowlist_comes_from_the_ingestion_registry(db_session, tmp_path) -> None:
    import app.services.document_service as document_service
    from app.rag.loader import SUPPORTED_EXTENSIONS

    assert set(SUPPORTED_EXTENSIONS) == document_service.ALLOWED_EXTENSIONS
    assert "application/pdf" in document_service.ALLOWED_CONTENT_TYPES
    assert "text/plain" in document_service.ALLOWED_CONTENT_TYPES
    assert ".exe" not in document_service.ALLOWED_EXTENSIONS


def test_identical_bytes_do_not_create_a_second_row(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    service = _service(db_session, tmp_path, _FakeIngestion([_FakeResult("indexed")]))

    first, first_duplicate = service.create(user_id, "codes.txt", "text/plain", b"same-bytes")
    second, second_duplicate = service.create(
        user_id, "codes copy.txt", "text/plain", b"same-bytes"
    )

    assert first_duplicate is False
    assert second_duplicate is True
    assert second.id == first.id
    assert service.list_documents(user_id, limit=10, offset=0)[1] == 1
    # The stored bytes of the original are untouched.
    assert (tmp_path / first.storage_key).read_bytes() == b"same-bytes"


def test_another_user_may_upload_the_same_bytes(db_session, tmp_path) -> None:
    service = _service(db_session, tmp_path, _FakeIngestion([_FakeResult("indexed")]))
    service.create(uuid.uuid4(), "shared.txt", "text/plain", b"shared")
    second, is_duplicate = service.create(uuid.uuid4(), "shared.txt", "text/plain", b"shared")

    assert is_duplicate is False
    assert second.content_hash is not None


def test_rename_updates_only_the_label(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    service = _service(db_session, tmp_path, _FakeIngestion([]))
    document, _dup = service.create(
        user_id, "notes.txt", "text/plain", b"body", trigger_ingestion=False
    )

    renamed = service.rename(user_id, document.id, "  workout notes.txt  ")
    assert renamed.filename == "workout notes.txt"
    assert (tmp_path / document.storage_key).read_bytes() == b"body"

    import pytest

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        service.rename(user_id, document.id, "   ")


def test_failure_reasons_are_short_and_human_readable(db_session, tmp_path) -> None:
    from app.services.document_service import DEFAULT_FAILURE_REASON, readable_failure

    assert readable_failure("unsupported file type .exe") == "Unsupported file type."
    assert (
        readable_failure("Image reading isn't available right now.")
        == "Image reading isn't available right now."
    )
    assert readable_failure("content does not match .jpg format") == "Couldn't read this file."
    assert readable_failure(RuntimeError("boom")) == DEFAULT_FAILURE_REASON

    # A reason never leaks a traceback, file content or secrets.
    reason = readable_failure(
        ValueError("sql: SELECT * FROM users WHERE token='secret'\nTraceback ...")
    )
    assert "Traceback" not in reason
    assert "secret" not in reason
    assert len(reason) < 120


def test_document_without_readable_text_is_ready_with_a_note(db_session, tmp_path) -> None:
    """A document with no text is a valid, Ready result - not a failure."""
    ingestion = _FakeIngestion([_FakeResult("indexed", note="No readable text found")])
    document, _dup = _service(db_session, tmp_path, ingestion).create(
        uuid.uuid4(), "empty.txt", "text/plain", TEXT_CONTENT
    )

    assert document.status == DocumentStatus.INDEXED
    assert document.error_message is None
    assert (document.ingestion_metadata or {}).get("note") == "No readable text found"


def test_a_new_note_replaces_the_previous_one(db_session, tmp_path) -> None:
    user_id = uuid.uuid4()
    ingestion = _FakeIngestion(
        [_FakeResult("indexed", note="No readable text found"), _FakeResult("indexed")]
    )
    service = _service(db_session, tmp_path, ingestion)
    document, _dup = service.create(user_id, "empty.txt", "text/plain", TEXT_CONTENT)

    retried = service.retry(user_id, document.id)

    assert retried.status == DocumentStatus.INDEXED
    assert not (retried.ingestion_metadata or {}).get("note")


def test_stuck_documents_are_failed_by_the_startup_reconciliation(db_session) -> None:
    from datetime import datetime, timedelta, timezone

    from app.repositories.document_repository import DocumentRepository
    from app.services.document_service import STUCK_REASON, reconcile_stuck_documents

    now = datetime.now(timezone.utc)
    old = DocumentRepository(db_session).create(
        uuid.uuid4(),
        "old.txt",
        "text/plain",
        10,
        status=DocumentStatus.PROCESSING,
    )
    old.created_at = now - timedelta(hours=3)
    fresh = DocumentRepository(db_session).create(
        uuid.uuid4(),
        "fresh.txt",
        "text/plain",
        10,
        status=DocumentStatus.PENDING,
    )
    db_session.commit()

    failed = reconcile_stuck_documents(db_session, timeout_minutes=30, now=now)

    assert failed == [old.id]
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert old.status == DocumentStatus.FAILED
    assert old.error_message == STUCK_REASON
    assert fresh.status == DocumentStatus.PENDING
    # Nothing is deleted: the row can still be reprocessed with Retry.
    assert len(DocumentRepository(db_session).list_all()) == 2