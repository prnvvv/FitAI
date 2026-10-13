"""Tests for document ingestion pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.rag.pipeline import IngestionPipeline


def _pipeline() -> tuple[IngestionPipeline, MagicMock]:
    store = MagicMock()
    store.delete_document.return_value = 0
    store.add_chunks.return_value = 1
    pipeline = IngestionPipeline(store)
    return pipeline, store


def test_ingest_curated_directory_skips_unsupported_files(tmp_path: Path) -> None:
    pipeline, store = _pipeline()
    (tmp_path / "readme.md").write_text("# readme")
    results = pipeline.ingest_curated_directory(tmp_path)
    assert len(results) == 0
    store.add_chunks.assert_not_called()


def test_ingest_curated_rejects_missing_file() -> None:
    pipeline, store = _pipeline()
    result = pipeline.ingest_curated("/nonexistent/file.pdf")
    assert result.status == "failed"
    store.add_chunks.assert_not_called()


def test_ingest_user_document_requires_user_id() -> None:
    pipeline, _ = _pipeline()
    with pytest.raises(ValueError, match="user_id is required"):
        pipeline.ingest_user_document("/tmp/file.pdf", "")


def test_ingest_curated_success(tmp_path: Path) -> None:
    pipeline, store = _pipeline()
    path = tmp_path / "doc.txt"
    path.write_text("Hello world")
    result = pipeline.ingest_curated(path)
    assert result.status == "indexed"
    assert result.scope == "curated"
    assert result.chunks_indexed >= 1
    store.delete_document.assert_called_once()
    store.add_chunks.assert_called_once()
