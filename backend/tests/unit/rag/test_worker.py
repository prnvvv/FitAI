"""Tests for background document ingestion."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import AuthUser
from app.models.enums import DocumentStatus
from app.rag import worker
from app.services.document_storage import LocalDocumentStorage


@pytest.fixture
def local_storage(tmp_path, monkeypatch) -> LocalDocumentStorage:
    """Use local filesystem storage so uploads succeed in unit tests."""
    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    return LocalDocumentStorage(str(tmp_path))


def _fake_pipeline(result) -> MagicMock:
    pipeline = MagicMock()
    pipeline.ingest_user_document_bytes.return_value = result
    return pipeline


def _worker_session_factory(db_session):
    """Build a SessionLocal that hands the worker its own session.

    The worker owns and closes its session, so it must not be the test's own
    session. The in-memory database uses a StaticPool, so a new session shares
    the same connection and sees the same rows.
    """
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, expire_on_commit=False)
    return factory


def test_successful_ingestion_marks_indexed(db_session, monkeypatch, local_storage) -> None:
    from app.services.document_service import DocumentService

    user_id = uuid.uuid4()
    document, _ = DocumentService(db_session, storage=local_storage).create(
        user_id, "plan.txt", "text/plain", b"data"
    )

    monkeypatch.setattr("app.db.session.SessionLocal", _worker_session_factory(db_session))
    pipeline = _fake_pipeline(MagicMock(status="indexed", chunks_indexed=2, error=None))
    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline", MagicMock(return_value=pipeline))

    worker.ingest_document(user_id, document.id, b"data")

    db_session.refresh(document)
    assert document.status == DocumentStatus.INDEXED
    assert document.completed_at is not None
    assert document.error_message is None


def test_failed_result_marks_failed(db_session, monkeypatch, local_storage) -> None:
    from app.services.document_service import DocumentService

    user_id = uuid.uuid4()
    document, _ = DocumentService(db_session, storage=local_storage).create(
        user_id, "scan.pdf", "application/pdf", b"data"
    )

    monkeypatch.setattr("app.db.session.SessionLocal", _worker_session_factory(db_session))
    pipeline = _fake_pipeline(
        MagicMock(status="failed", chunks_indexed=0, error="unsupported file type .pdf")
    )
    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline", MagicMock(return_value=pipeline))

    worker.ingest_document(user_id, document.id, b"data")

    db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Unsupported file type."


def test_pipeline_exception_marks_failed(db_session, monkeypatch, local_storage) -> None:
    from app.services.document_service import DocumentService

    user_id = uuid.uuid4()
    document, _ = DocumentService(db_session, storage=local_storage).create(
        user_id, "plan.txt", "text/plain", b"data"
    )

    monkeypatch.setattr("app.db.session.SessionLocal", _worker_session_factory(db_session))
    exploding = MagicMock(side_effect=RuntimeError("model download failed"))
    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline", exploding)

    worker.ingest_document(user_id, document.id, b"data")

    db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED


def test_deleted_document_is_not_resurrected(db_session, monkeypatch, local_storage) -> None:
    from app.services.document_service import DocumentService

    user_id = uuid.uuid4()
    document, _ = DocumentService(db_session, storage=local_storage).create(
        user_id, "plan.txt", "text/plain", b"data"
    )
    DocumentService(db_session, storage=local_storage).delete(user_id, document.id)

    monkeypatch.setattr("app.db.session.SessionLocal", _worker_session_factory(db_session))
    pipeline = _fake_pipeline(MagicMock(status="indexed", chunks_indexed=1, error=None))
    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline", MagicMock(return_value=pipeline))

    worker.ingest_document(user_id, document.id, b"data")

    pipeline.ingest_user_document_bytes.assert_not_called()


def test_ingestion_is_scoped_to_the_owning_user(db_session, monkeypatch, local_storage) -> None:
    from app.services.document_service import DocumentService

    owner = AuthUser(id=uuid.uuid4())
    document, _ = DocumentService(db_session, storage=local_storage).create(
        owner.id, "plan.txt", "text/plain", b"data"
    )

    monkeypatch.setattr("app.db.session.SessionLocal", _worker_session_factory(db_session))
    pipeline = _fake_pipeline(MagicMock(status="indexed", chunks_indexed=1, error=None))
    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline", MagicMock(return_value=pipeline))

    worker.ingest_document(uuid.uuid4(), document.id, b"data")

    pipeline.ingest_user_document_bytes.assert_not_called()
