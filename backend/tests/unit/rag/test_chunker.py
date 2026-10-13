"""Tests for text chunking."""
from __future__ import annotations

import pytest

from app.rag.chunker import Chunk, chunk_document, split_text
from app.rag.loader import LoadedDocument, Section


def test_split_text_short_text_returns_single() -> None:
    assert split_text("hello world") == ["hello world"]


def test_split_text_respects_chunk_size() -> None:
    text = "a " * 2000
    chunks = split_text(text, chunk_size=100, overlap=10)
    assert all(len(c) <= 100 for c in chunks)
    assert len(chunks) > 1


def test_split_text_overlap() -> None:
    text = "word " * 100
    chunks = split_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    # Last chunk of first piece should appear at start of second piece.
    first = chunks[0]
    second = chunks[1]
    overlap_text = first[-20:].strip()
    assert overlap_text in second


def test_chunk_document_preserves_metadata() -> None:
    doc = LoadedDocument(source="test.pdf", file_type="pdf",
                         sections=(Section("Hello world", page=1),))
    chunks = chunk_document(doc, "doc-1", {"author": "test"})
    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, Chunk)
    assert chunk.metadata["doc_id"] == "doc-1"
    assert chunk.metadata["source"] == "test.pdf"
    assert chunk.metadata["file_type"] == "pdf"
    assert chunk.metadata["page"] == 1
    assert chunk.metadata["author"] == "test"


def test_chunk_document_enforces_max_chunks() -> None:
    long_text = "word " * 5000
    doc = LoadedDocument(source="test.txt", file_type="txt",
                         sections=(Section(long_text),))
    with pytest.raises(ValueError, match="exceeds"):
        chunk_document(doc, "doc-1", max_chunks=1)
