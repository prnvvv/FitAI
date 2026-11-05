"""Upload hardening: content must match its type; names are sanitised; size capped."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.document_service import sanitize_filename


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "document_storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "ingestion_mode", "inline")
    monkeypatch.setattr("app.api.routers.documents.ingest_document", lambda *a, **k: None)


def _upload(client, name: str, data: bytes, content_type: str):
    return client.post("/api/v1/documents", files={"file": (name, data, content_type)})


def test_executable_disguised_as_pdf_is_rejected_before_storage(client, tmp_path) -> None:
    r = _upload(client, "invoice.pdf", b"MZ\x90\x00 this is a windows exe", "application/pdf")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert list(tmp_path.rglob("*")) == []  # nothing was persisted


def test_html_script_disguised_as_txt_is_accepted_only_as_inert_text(client) -> None:
    # Plain text is stored as opaque bytes and never served back or executed.
    r = _upload(client, "note.txt", b"<script>alert(1)</script>", "text/plain")
    assert r.status_code == 201


def test_binary_payload_named_txt_is_rejected(client) -> None:
    r = _upload(client, "notes.txt", b"abc\x00\x01\x02binary", "text/plain")
    assert r.status_code == 415


def test_zip_named_pdf_is_rejected(client) -> None:
    r = _upload(client, "a.pdf", b"PK\x03\x04zipcontent", "application/pdf")
    assert r.status_code == 415


def test_unsupported_extension_is_rejected_even_with_allowed_mime(client) -> None:
    r = _upload(client, "run.exe", b"MZ\x90\x00", "application/octet-stream")
    assert r.status_code == 415


def test_oversized_upload_is_rejected(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    r = _upload(client, "big.txt", b"a" * (1024 * 1024 + 1), "text/plain")
    assert r.status_code == 413


def test_valid_pdf_is_accepted(client) -> None:
    r = _upload(client, "plan.pdf", b"%PDF-1.4\n%fake but signed\n", "application/pdf")
    assert r.status_code == 201
    assert r.json()["filename"] == "plan.pdf"


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\evil.pdf", "evil.pdf"),
        ("report\x00.pdf", "report.pdf"),
        ("a\nb\r.txt", "ab.txt"),
        ("", "upload"),
        ("...", "upload"),
    ],
)
def test_filenames_are_sanitised(raw: str, clean: str) -> None:
    assert sanitize_filename(raw) == clean


def test_filename_length_is_bounded() -> None:
    assert len(sanitize_filename("x" * 1000 + ".pdf")) <= 255


def test_storage_key_ignores_user_supplied_filename(client, tmp_path) -> None:
    r = _upload(client, "../../../evil.txt", b"hello", "text/plain")
    assert r.status_code == 201
    for path in tmp_path.rglob("*"):
        assert tmp_path in path.resolve().parents or path.resolve() == tmp_path
    assert not (tmp_path.parent / "evil.txt").exists()
