"""Incremental access to a document's text, one page/section range at a time.

``load_file`` extracts a whole document into memory. For checkpointed ingestion
this module exposes the same content in bounded slices: a PDF is read page by
page and only the requested pages are extracted, so memory stays proportional to
the batch rather than the document. Non-PDF formats are small single sections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import (
    DEFAULT_MAX_BYTES,
    DocumentLoadError,
    Section,
    _clean,
    _load_docx,
    _load_txt,
    resolve_handler,
)

_HEAD_BYTES = 8192


class PageSource:
    """Sliceable view over one document file."""

    def __init__(self, path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        if not path.is_file():
            raise DocumentLoadError("file not found")
        size = path.stat().st_size
        if size == 0:
            raise DocumentLoadError("file is empty")
        if size > max_bytes:
            raise DocumentLoadError("file too large")
        with path.open("rb") as fh:
            head = fh.read(_HEAD_BYTES)
        handler = resolve_handler(path.name, head)
        self.source = path.name
        self.file_type = handler.extension[1:]
        self._path = path
        self._reader = None
        self._sections: list[Section] | None = None

        if handler.extension == ".pdf":
            self._reader = self._open_pdf(path)
            self.total_units = len(self._reader.pages)
        else:
            loader = _load_docx if handler.extension == ".docx" else _load_txt
            self._sections = [s for s in loader(path) if s.text]
            self.total_units = len(self._sections)

    @staticmethod
    def _open_pdf(path: Path) -> Any:  # pypdf is imported lazily
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentLoadError("pypdf is not installed") from exc
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted and not reader.decrypt(""):
                raise DocumentLoadError("PDF is password-protected")
            len(reader.pages)  # force the page tree to parse so errors surface here
            return reader
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"could not read PDF ({type(exc).__name__})") from exc

    def sections(self, start: int, count: int) -> list[Section]:
        """Return the non-empty sections for units ``[start, start + count)``."""
        end = min(start + count, self.total_units)
        if self._reader is None:
            assert self._sections is not None
            return self._sections[start:end]
        out: list[Section] = []
        for index in range(start, end):
            try:
                text = _clean(self._reader.pages[index].extract_text() or "")
            except Exception as exc:
                raise DocumentLoadError(f"could not read PDF ({type(exc).__name__})") from exc
            if text:
                out.append(Section(text, index + 1))
        return out
