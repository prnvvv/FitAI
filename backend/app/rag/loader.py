"""Load and extract text from documents.

One central registry maps an extension to its media types, its magic-byte
signature and its handler kind. Documents (pdf, txt, md, docx) are parsed
directly. A file whose bytes do not match the signature of its extension is
rejected, so a renamed executable can never reach a parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_MAX_BYTES = 25 * 1024 * 1024

HandlerKind = Literal["document"]


class DocumentLoadError(Exception):
    """File could not be read or has no extractable text."""


class UnsupportedFileTypeError(DocumentLoadError):
    """Extension is not one of the supported types."""


class FileSignatureMismatchError(DocumentLoadError):
    """File content does not match the format implied by its extension."""


@dataclass(frozen=True)
class FileHandler:
    """A supported file type: how to recognise it and how to read it."""

    extension: str
    media_types: frozenset[str]
    kind: HandlerKind
    #: Magic-byte prefixes that identify the format. Empty means "text-like":
    #: the content is accepted when it decodes as text and contains no NUL bytes.
    magic: tuple[bytes, ...] = ()
    #: Offset applied to every magic prefix (RIFF containers check bytes 8..12).
    magic_offset: int = 0
    #: Sentinel used when the format has no magic bytes.
    validate_text: bool = False


#: The single source of truth for supported uploads.
FILE_HANDLERS: dict[str, FileHandler] = {
    ".pdf": FileHandler(
        ".pdf",
        frozenset({"application/pdf"}),
        "document",
        magic=(b"%PDF",),
    ),
    ".docx": FileHandler(
        ".docx",
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
        "document",
        magic=(b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ),
    ".txt": FileHandler(
        ".txt",
        frozenset({"text/plain"}),
        "document",
        validate_text=True,
    ),
    ".md": FileHandler(
        ".md",
        frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
        "document",
        validate_text=True,
    ),
}

SUPPORTED_EXTENSIONS = frozenset(FILE_HANDLERS)
DOCUMENT_EXTENSIONS = frozenset(k for k, h in FILE_HANDLERS.items() if h.kind == "document")


@dataclass(frozen=True)
class Section:
    """A block of text; `page` is 1-based for PDFs, else None."""

    text: str
    page: int | None = None


@dataclass(frozen=True)
class LoadedDocument:
    source: str  # file name only (no server paths)
    file_type: str  # "pdf" | "txt" | "md" | "docx"
    sections: tuple[Section, ...]
    #: Set when the source was readable but contained no text. Such a document is
    #: valid and Ready; it simply indexes no chunks.
    note: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _load_pdf(path: Path) -> list[Section]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentLoadError("pypdf is not installed") from exc
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentLoadError("PDF is password-protected")
        pages = [(i + 1, _clean(p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"could not read PDF ({type(exc).__name__})") from exc
    return [Section(t, n) for n, t in pages if t]


def _load_txt(path: Path) -> list[Section]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return [Section(_clean(raw.decode(enc)))]
        except UnicodeDecodeError:
            continue
    raise DocumentLoadError("text file encoding not recognised")


def _load_docx(path: Path) -> list[Section]:
    try:
        import docx
    except ImportError as exc:
        raise DocumentLoadError("python-docx is not installed") from exc
    try:
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:  # tables are appended after paragraphs
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
    except Exception as exc:
        raise DocumentLoadError(f"could not read DOCX ({type(exc).__name__})") from exc
    return [Section(_clean("\n".join(parts)))]


TEXT_PEEK_BYTES = 4096


def resolve_handler(filename: str, data: bytes) -> FileHandler:
    """Return the handler for ``filename``, verifying its magic bytes.

    Raises ``UnsupportedFileTypeError`` for unknown extensions and
    ``FileSignatureMismatchError`` when the content contradicts the extension.
    """
    ext = Path(filename).suffix.lower()
    handler = FILE_HANDLERS.get(ext)
    if handler is None:
        raise UnsupportedFileTypeError(f"unsupported file type {ext or '(none)'}")

    if handler.magic:
        for signature in handler.magic:
            start = handler.magic_offset
            if data[start : start + len(signature)] == signature:
                return handler
        raise FileSignatureMismatchError(f"content does not match {ext} format")

    # Text-like formats: reject binary payloads masquerading as .txt/.md.
    if handler.validate_text:
        head = data[:TEXT_PEEK_BYTES]
        if b"\x00" in head:
            raise FileSignatureMismatchError(f"content does not match {ext} format")
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            raise FileSignatureMismatchError(f"content does not match {ext} format") from None
    return handler


def _read_bytes(path: Path, max_bytes: int) -> bytes:
    if not path.is_file():
        raise DocumentLoadError("file not found")
    if path.stat().st_size > max_bytes:
        raise DocumentLoadError("file too large")
    data = path.read_bytes()
    if not data:
        raise DocumentLoadError("file is empty")
    return data


def load_file(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> LoadedDocument:
    """Extract text from a supported document file (pdf, txt, md, docx)."""
    p = Path(path)
    data = _read_bytes(p, max_bytes)
    handler = resolve_handler(p.name, data)

    loader = {".pdf": _load_pdf, ".docx": _load_docx, ".txt": _load_txt, ".md": _load_txt}
    sections = [s for s in loader[handler.extension](p) if s.text]
    if not sections:
        raise DocumentLoadError("no extractable text in this file")
    return LoadedDocument(source=p.name, file_type=handler.extension[1:], sections=tuple(sections))
