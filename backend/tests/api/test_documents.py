"""Tests for document metadata, storage, and lifecycle."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser
from app.services.document_service import DocumentService
from app.services.document_storage import LocalDocumentStorage


def test_upload_without_configured_storage_returns_503(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.document_storage.settings.document_storage_backend", "unconfigured"
    )
    files = {"file": ("plan.pdf", b"%PDF-1.4 minimal", "application/pdf")}
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_upload_rejects_unsupported_type(client) -> None:
    files = {"file": ("malware.exe", b"MZ", "application/octet-stream")}
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 415


def test_upload_defers_ingestion_to_background_task(client, monkeypatch, tmp_path) -> None:
    """The upload response must not wait for parsing and embedding."""
    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    calls: list[tuple[str, str, bytes]] = []
    monkeypatch.setattr(
        "app.api.routers.documents.ingest_document",
        lambda user_id, document_id, data: calls.append((str(user_id), str(document_id), data)),
    )

    files = {"file": ("plan.txt", b"hello world", "text/plain")}
    response = client.post("/api/v1/documents", files=files)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert len(calls) == 1
    user_id, document_id, data = calls[0]
    assert document_id == response.json()["id"]
    assert data == b"hello world"


def test_upload_does_not_index_inline(client, monkeypatch, tmp_path) -> None:
    """No ingestion pipeline may be constructed on the request path."""
    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))

    def _fail(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("ingestion ran on the request thread")

    monkeypatch.setattr("app.rag.pipeline.IngestionPipeline.__init__", _fail)
    monkeypatch.setattr("app.api.routers.documents.ingest_document", lambda *a, **k: None)

    files = {"file": ("plan.txt", b"hello world", "text/plain")}
    assert client.post("/api/v1/documents", files=files).status_code == 201


def test_list_documents_empty(client) -> None:
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_delete_unknown_document_returns_404(client) -> None:
    response = client.delete(f"/api/v1/documents/{uuid.uuid4()}")
    assert response.status_code == 404


def test_local_storage_create_and_delete(db_session, tmp_path) -> None:
    storage = LocalDocumentStorage(str(tmp_path))
    service = DocumentService(db_session, storage=storage)
    user_id = uuid.uuid4()

    document = service.create(user_id, "plan.txt", "text/plain", b"hello world")
    assert document.status == "pending"
    assert document.storage_key == f"{user_id}/{document.id}"
    assert (tmp_path / document.storage_key).read_bytes() == b"hello world"

    items, total = service.list_documents(user_id, limit=10, offset=0)
    assert total == 1
    assert items[0].id == document.id

    service.delete(user_id, document.id)
    assert not (tmp_path / document.storage_key).exists()
    _, total_after = service.list_documents(user_id, limit=10, offset=0)
    assert total_after == 0


def test_mark_status_records_completion(db_session, tmp_path) -> None:
    from app.models.enums import DocumentStatus

    storage = LocalDocumentStorage(str(tmp_path))
    service = DocumentService(db_session, storage=storage)
    user_id = uuid.uuid4()
    document = service.create(user_id, "plan.txt", "text/plain", b"data")

    updated = service.mark_status(user_id, document.id, DocumentStatus.INDEXED)
    assert updated.status == "indexed"
    assert updated.completed_at is not None


def test_document_ownership_is_enforced(make_client, db_session, tmp_path) -> None:
    owner_user = AuthUser(id=uuid.uuid4())
    other_user = AuthUser(id=uuid.uuid4())
    owner = make_client(owner_user)
    other = make_client(other_user)

    storage = LocalDocumentStorage(str(tmp_path))
    service = DocumentService(db_session, storage=storage)
    document = service.create(owner_user.id, "owner.txt", "text/plain", b"secret")

    assert other.get(f"/api/v1/documents/{document.id}").status_code == 404
    assert other.delete(f"/api/v1/documents/{document.id}").status_code == 404
    assert owner.get(f"/api/v1/documents/{document.id}").status_code == 200
