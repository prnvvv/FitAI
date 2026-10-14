"""The ingestion registry must route each file type and reject spoofed ones."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.rag.loader import (
    DOCUMENT_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    FileSignatureMismatchError,
    UnsupportedFileTypeError,
    load_file,
    resolve_handler,
)

EXE_BYTES = b"MZ\x90\x00\x03" + b"\x00" * 64


def _pdf(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\nminimal")
    return p


def _txt(tmp_path: Path, name: str = "notes.txt") -> Path:
    p = tmp_path / name
    p.write_text("hello world", encoding="utf-8")
    return p


def _docx(tmp_path: Path) -> Path:
    p = tmp_path / "doc.docx"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    p.write_bytes(buffer.getvalue())
    return p


def test_registry_covers_documents() -> None:
    assert {".pdf", ".txt", ".md", ".docx"} == DOCUMENT_EXTENSIONS
    assert SUPPORTED_EXTENSIONS == DOCUMENT_EXTENSIONS


@pytest.mark.parametrize(
    ("name", "data", "kind"),
    [
        ("a.pdf", b"%PDF-1.4", "document"),
        ("a.docx", b"PK\x03\x04", "document"),
        ("a.txt", b"plain text", "document"),
        ("a.md", b"# heading", "document"),
    ],
)
def test_resolve_handler_maps_extension_to_kind(name: str, data: bytes, kind: str) -> None:
    assert resolve_handler(name, data).kind == kind


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError, match="unsupported file type .exe"):
        resolve_handler("malware.exe", EXE_BYTES)
    with pytest.raises(UnsupportedFileTypeError):
        resolve_handler("noextension", b"data")


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("payload.pdf", b"not a pdf"),
        ("payload.docx", b"not a zip"),
        ("payload.txt", EXE_BYTES),  # binary masquerading as text
    ],
)
def test_spoofed_extension_is_rejected_by_magic_bytes(name: str, data: bytes) -> None:
    with pytest.raises(FileSignatureMismatchError):
        resolve_handler(name, data)


def test_load_file_reads_text_documents(tmp_path: Path) -> None:
    loaded = load_file(_txt(tmp_path))
    assert loaded.text == "hello world"
    assert loaded.file_type == "txt"


def test_load_file_reads_markdown(tmp_path: Path) -> None:
    loaded = load_file(_txt(tmp_path, "notes.md"))
    assert loaded.file_type == "md"
    assert "hello world" in loaded.text


def test_load_file_rejects_spoofed_file(tmp_path: Path) -> None:
    p = tmp_path / "notreally.txt"
    p.write_bytes(EXE_BYTES)
    with pytest.raises(DocumentLoadError, match="does not match"):
        load_file(p)


def test_pdf_uses_its_native_parser(tmp_path: Path, monkeypatch) -> None:
    from app.rag.loader import Section

    monkeypatch.setattr("app.rag.loader._load_pdf", lambda _p: [Section("pdf text", 1)])
    loaded = load_file(_pdf(tmp_path))
    assert loaded.text == "pdf text"
    assert loaded.sections[0].page == 1


def test_docx_reaches_the_docx_parser(tmp_path: Path, monkeypatch) -> None:
    from app.rag.loader import Section

    seen: list[str] = []
    monkeypatch.setattr(
        "app.rag.loader._load_docx", lambda p: (seen.append(p.name), [Section("docx text")])[1]
    )
    loaded = load_file(_docx(tmp_path))
    assert loaded.file_type == "docx"
    assert loaded.text == "docx text"
    assert seen == ["doc.docx"]
