"""Overlapping text chunking that preserves source metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .loader import LoadedDocument

Metadata = dict[str, str | int | float | bool]
_BREAKS = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ")
_RESERVED = {"doc_id", "source", "file_type", "page", "chunk_index"}


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    metadata: Metadata  # Chroma-compatible: scalar values only, no None


def split_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Split on natural boundaries (paragraph > line > sentence > word) with overlap."""
    if chunk_size < 100:
        raise ValueError("chunk_size must be >= 100")
    if not 0 <= overlap <= chunk_size // 2:
        raise ValueError("overlap must be between 0 and chunk_size // 2")
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    pieces: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            for sep in _BREAKS:
                idx = text.rfind(sep, start + chunk_size // 2, end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return pieces


def _scalar(meta: Mapping[str, object]) -> Metadata:
    out: Metadata = {}
    for k, v in meta.items():
        if v is None:
            continue
        out[str(k)] = v if isinstance(v, str | int | float | bool) else str(v)
    return out


def chunk_document(
    doc: LoadedDocument,
    doc_id: str,
    metadata: Mapping[str, object] | None = None,
    chunk_size: int = 1000,
    overlap: int = 150,
    id_prefix: str = "",
    max_chunks: int | None = None,
) -> list[Chunk]:
    """Chunk each section separately (keeps page numbers). IDs: `{id_prefix}{doc_id}:{index}`."""
    base = _scalar(metadata or {})
    chunks: list[Chunk] = []
    for section in doc.sections:
        for piece in split_text(section.text, chunk_size, overlap):
            i = len(chunks)
            meta: Metadata = {
                **base,
                "doc_id": doc_id,
                "source": doc.source,
                "file_type": doc.file_type,
                "page": section.page or -1,
                "chunk_index": i,
            }
            assert meta.keys() >= _RESERVED
            chunks.append(Chunk(id=f"{id_prefix}{doc_id}:{i}", text=piece, metadata=meta))
            if max_chunks is not None and len(chunks) > max_chunks:
                raise ValueError(f"document exceeds {max_chunks} chunks")
    return chunks
