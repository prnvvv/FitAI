"""Tests for the owner-scoped continuity store (memories + past-chat summaries)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.rag.continuity_store import (
    KIND_MEMORY,
    KIND_SUMMARY,
    ContinuityHit,
    ContinuityStore,
)
from app.rag.vector_store import CONTINUITY_COLLECTION, SearchHit, VectorStore


def _store() -> tuple[ContinuityStore, MagicMock]:
    fake = MagicMock(spec=VectorStore)
    fake.query.return_value = []
    fake.list_vectors.return_value = []
    return ContinuityStore(fake), fake


def test_index_memory_uses_owner_scoped_doc_id() -> None:
    store, fake = _store()
    store.index_memory("user-1", "weight", "weight: 72 kg")
    args, kwargs = fake.add_chunks.call_args
    assert args[0] == CONTINUITY_COLLECTION
    chunk = args[1][0]
    assert chunk.metadata["doc_id"] == "memory:weight"
    assert chunk.metadata["kind"] == KIND_MEMORY
    assert chunk.metadata["owner_id"] == "user-1"
    assert chunk.metadata["key"] == "weight"
    assert kwargs["owner_id"] == "user-1"


def test_index_summary_uses_conversation_doc_id() -> None:
    store, fake = _store()
    store.index_summary("user-1", "conv-9", "Discussed a cut.", "Cutting plan")
    _, kwargs = fake.add_chunks.call_args
    chunk = fake.add_chunks.call_args[0][1][0]
    assert chunk.metadata["doc_id"] == "summary:conv-9"
    assert chunk.metadata["kind"] == KIND_SUMMARY
    assert chunk.metadata["title"] == "Cutting plan"
    assert kwargs["owner_id"] == "user-1"


def test_index_skips_blank_text() -> None:
    store, fake = _store()
    store.index_memory("user-1", "weight", "   ")
    fake.add_chunks.assert_not_called()


def test_search_scopes_to_owner_and_kind() -> None:
    store, fake = _store()
    fake.query.return_value = [
        SearchHit(
            "id-1",
            "weight: 72 kg",
            {"kind": KIND_MEMORY, "owner_id": "user-1"},
            0.1,
        )
    ]
    hits = store.search("user-1", "what is my weight", kind=KIND_MEMORY)
    assert len(hits) == 1
    assert isinstance(hits[0], ContinuityHit)
    args, kwargs = fake.query.call_args
    assert args[0] == CONTINUITY_COLLECTION
    assert kwargs["owner_id"] == "user-1"
    assert kwargs["where"] == {"kind": KIND_MEMORY}


def test_search_filters_low_score() -> None:
    store, fake = _store()
    fake.query.return_value = [
        SearchHit("id-1", "irrelevant", {"kind": KIND_MEMORY}, 0.95),
    ]
    assert store.search("user-1", "query", min_score=0.5) == []


def test_search_blank_query_returns_empty_without_querying() -> None:
    store, fake = _store()
    assert store.search("user-1", "   ") == []
    fake.query.assert_not_called()


def test_sync_memories_prunes_removed_keys() -> None:
    store, fake = _store()
    fake.list_vectors.return_value = [
        SearchHit("id-1", "", {"doc_id": "memory:weight", "key": "weight"}, 0.0),
        SearchHit("id-2", "", {"doc_id": "memory:goal", "key": "goal"}, 0.0),
    ]
    store.sync_memories("user-1", {"weight": "weight: 72 kg"})
    # weight upserted, goal pruned (still present in memory -> not pruned)
    deleted_doc_ids = [call.args[1] for call in fake.delete_document.call_args_list]
    assert "memory:goal" in deleted_doc_ids
    assert "memory:weight" not in deleted_doc_ids
    # weight was (re)indexed
    assert fake.add_chunks.call_count == 1


def test_delete_memory_and_summary_target_owner() -> None:
    store, fake = _store()
    store.delete_memory("user-1", "weight")
    store.delete_summary("user-1", "conv-9")
    calls = [(c.args[1], c.kwargs["owner_id"]) for c in fake.delete_document.call_args_list]
    assert ("memory:weight", "user-1") in calls
    assert ("summary:conv-9", "user-1") in calls
