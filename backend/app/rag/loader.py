"""Load and extract text from PDF, TXT and DOCX files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx"}
DEFAULT_MAX_BYTES = 25 * 1024 * 1024


class DocumentLoadError(Exception):
    """File could not be read or has no extractable text."""


class UnsupportedFileTypeError(DocumentLoadError):
    """Extension is not one of the supported types."""


@dataclass(frozen=True)
class Section:
    """A block of text; `page` is 1-based for PDFs, else None."""

    text: str
    page: int | None = None


@dataclass(frozen=True)
class LoadedDocument:
    source: str  # file name only (no server paths)
    file_type: str  # "pdf" | "txt" | "docx"
    sections: tuple[Section, ...]

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


def load_document(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> LoadedDocument:
    """Extract text from a supported file. Raises DocumentLoadError subclasses."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(f"unsupported file type {ext or '(none)'}")
    if not p.is_file():
        raise DocumentLoadError("file not found")
    if p.stat().st_size > max_bytes:
        raise DocumentLoadError("file too large")
    if p.stat().st_size == 0:
        raise DocumentLoadError("file is empty")
    with p.open("rb") as fh:
        head = fh.read(4)
    if (ext == ".pdf" and head != b"%PDF") or (ext == ".docx" and head[:2] != b"PK"):
        raise DocumentLoadError(f"content does not match {ext} format")

    loader = {".pdf": _load_pdf, ".txt": _load_txt, ".docx": _load_docx}[ext]
    sections = [s for s in loader(p) if s.text]
    if not sections:
        raise DocumentLoadError(
            "no extractable text (scanned documents need OCR, which is not supported)"
        )
    return LoadedDocument(source=p.name, file_type=ext[1:], sections=tuple(sections))
