"""Tests for document metadata, storage, and lifecycle."""

from __future__ import annotations

import json
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


def test_accepted_types_match_the_document_loader(client) -> None:
    """Anything we accept must be parseable, or it can only ever fail indexing."""
    from app.rag.loader import SUPPORTED_EXTENSIONS
    from app.services.document_service import ALLOWED_EXTENSIONS

    assert ALLOWED_EXTENSIONS == SUPPORTED_EXTENSIONS


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

    document, _dup = service.create(user_id, "plan.txt", "text/plain", b"hello world")
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
    document, _dup = service.create(user_id, "plan.txt", "text/plain", b"data")

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
    document, _dup = service.create(owner_user.id, "owner.txt", "text/plain", b"secret")

    assert other.get(f"/api/v1/documents/{document.id}").status_code == 404
    assert other.delete(f"/api/v1/documents/{document.id}").status_code == 404
    assert owner.get(f"/api/v1/documents/{document.id}").status_code == 200


def test_upload_of_identical_bytes_returns_the_existing_item(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    files = {"file": ("codes.txt", b"recovery-codes", "text/plain")}

    first = client.post("/api/v1/documents", files=files)
    assert first.status_code == 201
    assert first.headers.get("X-Duplicate") is None

    second = client.post("/api/v1/documents", files=files)
    assert second.status_code == 200
    assert second.headers.get("X-Duplicate") == "true"
    assert second.json()["id"] == first.json()["id"]
    assert client.get("/api/v1/documents").json()["total"] == 1


def test_upload_response_exposes_failure_reason(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    response = client.post(
        "/api/v1/documents", files={"file": ("bad.exe", b"MZ", "application/octet-stream")}
    )
    assert response.status_code == 415
    body = response.json()["error"]
    assert "Traceback" not in json.dumps(body)


def test_rename_document(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    created = client.post(
        "/api/v1/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    document_id = created.json()["id"]

    renamed = client.patch(
        f"/api/v1/documents/{document_id}", json={"filename": "Workout notes.txt"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["filename"] == "Workout notes.txt"

    assert (
        client.patch(f"/api/v1/documents/{document_id}", json={"filename": "  "}).status_code == 422
    )
    assert (
        client.patch(f"/api/v1/documents/{uuid.uuid4()}", json={"filename": "x"}).status_code == 404
    )


def test_upload_with_spaces_and_uppercase_extension_is_accepted(
    client, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "WhatsApp Document 2026-10-14 at 12.40.14 PM.TXT",
                b"hello world",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["filename"].endswith(".TXT")


def test_document_response_exposes_the_empty_text_note(db_session, tmp_path, monkeypatch) -> None:
    """A Ready-but-empty document reports its note instead of failing."""
    from app.models.enums import DocumentStatus
    from app.schemas.document import DocumentOut

    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    storage = LocalDocumentStorage(str(tmp_path))
    service = DocumentService(db_session, storage=storage)
    document, _dup = service.create(
        uuid.uuid4(), "empty.txt", "text/plain", b"   ", trigger_ingestion=False
    )
    service.mark_status(
        document.user_id,
        document.id,
        DocumentStatus.INDEXED,
        note="No readable text found",
    )

    body = DocumentOut.from_document(service.get(document.user_id, document.id)).model_dump()

    assert body["status"] == "indexed"
    assert body["failure_reason"] is None
    assert body["note"] == "No readable text found"
