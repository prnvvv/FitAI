"""Tests for ChromaDB vector store wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.rag.chunker import Chunk
from app.rag.vector_store import (
    KNOWLEDGE_COLLECTION,
    USER_COLLECTION,
    VectorStore,
    VectorStoreError,
)


def _mock_collection() -> MagicMock:
    col = MagicMock()
    col.metadata = {"embedding_model": "chroma-default-onnx-minilm-l6-v2"}
    col.get.return_value = {"ids": []}
    col.count.return_value = 0
    return col


def test_vector_store_opens_known_collections() -> None:
    client = MagicMock()
    client.get_or_create_collection.return_value = _mock_collection()
    store = VectorStore(client=client, embedding_function=MagicMock())
    col = store._col(KNOWLEDGE_COLLECTION)
    assert col is not None
    client.get_or_create_collection.assert_called_once()


def test_vector_store_rejects_unknown_collection() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    with pytest.raises(ValueError, match="unknown collection"):
        store._col("unknown")


def test_vector_store_add_chunks_user_requires_owner_id() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    chunk = Chunk(id="c1", text="hello", metadata={"owner_id": "user-1"})
    with pytest.raises(PermissionError, match="owner_id is required"):
        store.add_chunks(USER_COLLECTION, [chunk])


def test_vector_store_add_chunks_user_requires_matching_owner() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    chunk = Chunk(id="c1", text="hello", metadata={"owner_id": "user-2"})
    with pytest.raises(PermissionError, match="chunk owner_id does not match"):
        store.add_chunks(USER_COLLECTION, [chunk], owner_id="user-1")


def test_vector_store_query_requires_positive_n() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    with pytest.raises(ValueError, match="n_results must be >= 1"):
        store.query(KNOWLEDGE_COLLECTION, "test", n_results=0)


def test_vector_store_embedding_model_mismatch_raises() -> None:
    client = MagicMock()
    col = MagicMock()
    col.metadata = {"embedding_model": "old-model"}
    client.get_or_create_collection.return_value = col
    store = VectorStore(client=client, embedding_function=MagicMock())
    with pytest.raises(VectorStoreError, match="re-index required"):
        store._col(KNOWLEDGE_COLLECTION)


def test_delete_document_filters_by_owner_and_doc_id() -> None:
    """Deleting a document may only remove its own owner's vectors."""
    collection = _mock_collection()
    collection.get.return_value = {"ids": ["c1", "c2"]}
    client = MagicMock()
    client.get_or_create_collection.return_value = collection
    store = VectorStore(client=client, embedding_function=MagicMock())

    removed = store.delete_document(USER_COLLECTION, "doc-1", owner_id="user-1")

    assert removed == 2
    _, kwargs = collection.get.call_args
    assert kwargs["where"] == {"$and": [{"owner_id": "user-1"}, {"doc_id": "doc-1"}]}
    collection.delete.assert_called_once_with(ids=["c1", "c2"])


def test_delete_document_requires_an_owner_for_user_collection() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    with pytest.raises(PermissionError, match="owner_id is required"):
        store.delete_document(USER_COLLECTION, "doc-1")


def test_query_requires_an_owner_for_user_collection() -> None:
    store = VectorStore(client=MagicMock(), embedding_function=MagicMock())
    with pytest.raises(PermissionError, match="owner_id is required"):
        store.query(USER_COLLECTION, "squat")
