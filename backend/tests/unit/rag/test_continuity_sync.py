"""Incremental continuity synchronisation.

A full re-index per turn is wasteful: it re-embeds every remembered fact even
when nothing changed. These tests pin the incremental behaviour, the pruning of
deleted facts, owner isolation, and the resulting correctness of retrieval.
"""

from __future__ import annotations

import pytest

from app.rag.continuity_store import KIND_MEMORY, ContinuityStore
from app.rag.vector_store import CONTINUITY_COLLECTION, VectorStore


class _FakeStore:
    """Minimal VectorStore stand-in that records upserts and deletions."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.embed_calls: list[list[str]] = []

    def add_chunks(self, collection, chunks, owner_id=None) -> int:
        self.embed_calls.append([c.text for c in chunks])
        for chunk in chunks:
            self.rows[chunk.id] = dict(chunk.metadata)
        return len(chunks)

    def list_vectors(self, collection, owner_id=None, where=None) -> list:
        kind = (where or {}).get("kind")
        return [
            type("Hit", (), {"metadata": meta})()
            for meta in self.rows.values()
            if meta.get("owner_id") == owner_id and (kind is None or meta.get("kind") == kind)
        ]

    def delete_document(self, collection, doc_id, owner_id=None) -> int:
        key = f"{owner_id}:{doc_id}:0"
        return 1 if self.rows.pop(key, None) is not None else 0

    def query(self, collection, query, n_results=4, where=None, owner_id=None) -> list:
        kind = (where or {}).get("kind")
        hits = []
        for meta in self.rows.values():
            if meta.get("owner_id") != owner_id:
                continue
            if kind and meta.get("kind") != kind:
                continue
            text = next((c[0] for c in self.embed_calls if meta["text_hash"] in str(c)), "")
            hits.append(type("Hit", (), {"metadata": meta, "text": text, "distance": 0.1})())
        return hits[:n_results]


def _store() -> tuple[ContinuityStore, _FakeStore]:
    fake = _FakeStore()
    return ContinuityStore(fake), fake  # type: ignore[arg-type]


def test_first_sync_embeds_every_fact() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling", "b": "likes rowing"})
    assert len(fake.rows) == 2
    assert sum(len(c) for c in fake.embed_calls) == 2


def test_unchanged_sync_re_embeds_nothing() -> None:
    continuity, fake = _store()
    memories = {"a": "likes cycling", "b": "likes rowing"}
    continuity.sync_memories("u1", memories)
    fake.embed_calls.clear()

    continuity.sync_memories("u1", dict(memories))

    assert fake.embed_calls == []  # no embedding work for unchanged facts
    assert len(fake.rows) == 2


def test_only_changed_fact_is_re_embedded() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling", "b": "likes rowing"})
    fake.embed_calls.clear()

    continuity.sync_memories("u1", {"a": "likes swimming", "b": "likes rowing"})

    assert fake.embed_calls == [["likes swimming"]]


def test_deleted_fact_is_removed_and_does_not_come_back() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling", "b": "likes rowing"})
    assert len(fake.rows) == 2

    continuity.sync_memories("u1", {"a": "likes cycling"})

    assert len(fake.rows) == 1
    assert all(meta["key"] != "b" for meta in fake.rows.values())


def test_reindex_updates_in_place_with_a_stable_id() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling"})
    first_ids = set(fake.rows)

    continuity.sync_memories("u1", {"a": "likes swimming"})

    assert set(fake.rows) == first_ids  # same document id, no duplicate vector
    assert fake.rows[next(iter(first_ids))]["text_hash"] != ""


def test_sync_is_scoped_per_user() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling"})
    continuity.sync_memories("u2", {"a": "likes rowing"})

    assert len(fake.rows) == 2
    continuity.sync_memories("u1", {"a": "likes cycling", "b": "likes swimming"})
    # Deleting u2's only fact must not touch u1's documents.
    continuity.sync_memories("u2", {})
    assert sum(1 for m in fake.rows.values() if m["owner_id"] == "u1") == 2
    assert sum(1 for m in fake.rows.values() if m["owner_id"] == "u2") == 0


def test_blank_text_is_ignored_not_indexed() -> None:
    continuity, fake = _store()
    continuity.sync_memories("u1", {"a": "likes cycling", "b": "   "})
    assert [m["key"] for m in fake.rows.values()] == ["a"]


def test_sync_without_user_id_is_a_noop() -> None:
    continuity, fake = _store()
    continuity.sync_memories("", {"a": "likes cycling"})
    assert fake.rows == {}


def test_missing_owner_id_is_rejected_by_the_real_store() -> None:
    """The real VectorStore refuses an unscoped continuity write."""
    from app.rag.chunker import Chunk

    store = VectorStore.__new__(VectorStore)  # no client needed: scoping runs first
    with pytest.raises(PermissionError):
        store.add_chunks(CONTINUITY_COLLECTION, [Chunk(id="x:0", text="t", metadata={})])
    # A mismatch between the caller's owner and the chunk's owner is refused too.
    with pytest.raises(PermissionError):
        store.add_chunks(
            CONTINUITY_COLLECTION,
            [Chunk(id="x:0", text="t", metadata={"owner_id": "someone-else"})],
            owner_id="u1",
        )
    assert KIND_MEMORY == "memory"
