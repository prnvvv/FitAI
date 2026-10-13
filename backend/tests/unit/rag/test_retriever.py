"""Tests for RAG retriever."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.rag.retriever import Retriever
from app.rag.vector_store import VectorStore, VectorStoreError


def _hit(text: str, source: str, doc_id: str, page: int, distance: float,
         owner_id: str | None = None) -> MagicMock:
    hit = MagicMock()
    hit.text = text
    hit.distance = distance
    hit.metadata = {"source": source, "doc_id": doc_id, "page": page}
    if owner_id:
        hit.metadata["owner_id"] = owner_id
    return hit


def test_retriever_search_formats_citations() -> None:
    store = MagicMock(spec=VectorStore)
    store.query.return_value = [
        _hit("protein info", "guide.pdf", "doc-1", 2, 0.1),
    ]
    retriever = Retriever(store, k=4, min_score=0.0)
    docs = retriever.search("protein", "user-1")
    assert len(docs) == 1
    assert "[guide.pdf p.2]" in docs[0]
    assert "protein info" in docs[0]


def test_retriever_filters_by_min_score() -> None:
    store = MagicMock(spec=VectorStore)
    store.query.return_value = [
        _hit("good", "a.pdf", "doc-1", 1, 0.1),
        _hit("bad", "b.pdf", "doc-2", 1, 0.9),
    ]
    retriever = Retriever(store, k=4, min_score=0.5)
    docs = retriever.search("test", "user-1")
    assert len(docs) == 1
    assert "a.pdf" in docs[0]


def test_retriever_blank_user_id_gets_curated_only() -> None:
    store = MagicMock(spec=VectorStore)
    store.query.return_value = []
    retriever = Retriever(store)
    retriever.retrieve("test", "   ")
    assert store.query.call_count == 1
    args = store.query.call_args
    assert args[0][0] == "fitness_knowledge"


def test_retriever_raises_when_all_sources_fail() -> None:
    store = MagicMock(spec=VectorStore)
    store.query.side_effect = VectorStoreError("boom")
    retriever = Retriever(store)
    with pytest.raises(VectorStoreError, match="all retrieval sources failed"):
        retriever.retrieve("test", "user-1")
