"""Owner-scoped continuity vectors: memory facts and per-conversation summaries.

Backed by the ``user_continuity`` Chroma collection. Every operation is filtered
by ``owner_id`` so semantic recall can never cross users. Memory facts and
conversation summaries share the collection but are distinguished by the
``kind`` metadata field, which lets retrieval ask for one or both.

This layer is best-effort: callers treat a :class:`VectorStoreError` as "no
recall available" rather than failing the turn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .chunker import Chunk
from .vector_store import CONTINUITY_COLLECTION, VectorStore

log = logging.getLogger(__name__)

KIND_MEMORY = "memory"
KIND_SUMMARY = "summary"


@dataclass(frozen=True)
class ContinuityHit:
    """One owner-scoped continuity vector."""

    kind: str
    text: str
    metadata: dict[str, Any]
    distance: float

    @property
    def score(self) -> float:
        return max(0.0, min(1.0, 1.0 - self.distance))


class ContinuityStore:
    """Index and recall a user's memories and past-chat summaries."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    # -- indexing ---------------------------------------------------------
    def index_memory(self, user_id: str, key: str, text: str) -> None:
        """Upsert one memory fact as a single owner-scoped vector."""
        self._upsert(
            user_id,
            f"{KIND_MEMORY}:{key}",
            text,
            {"kind": KIND_MEMORY, "key": str(key), "source": "memory"},
        )

    def index_summary(
        self, user_id: str, conversation_id: str, text: str, title: str | None = None
    ) -> None:
        """Upsert one conversation summary as a single owner-scoped vector."""
        self._upsert(
            user_id,
            f"{KIND_SUMMARY}:{conversation_id}",
            text,
            {
                "kind": KIND_SUMMARY,
                "conversation_id": str(conversation_id),
                "source": "past_chat",
                "title": (title or "Past chat")[:200],
            },
        )

    def sync_memories(self, user_id: str, memories: dict[str, str]) -> None:
        """Make the stored memory vectors equal ``memories`` (upsert + prune).

        ``memories`` maps a memory key to its display text. Keys absent from the
        map are removed so a deleted or superseded fact stops being recalled.
        """
        for key, text in memories.items():
            self.index_memory(user_id, key, text)
        for hit in self._store.list_vectors(
            CONTINUITY_COLLECTION, owner_id=str(user_id), where={"kind": KIND_MEMORY}
        ):
            key = str(hit.metadata.get("key", ""))
            if key and key not in memories:
                self.delete_memory(user_id, key)

    # -- deletion ---------------------------------------------------------
    def delete_memory(self, user_id: str, key: str) -> int:
        return self._store.delete_document(
            CONTINUITY_COLLECTION, f"{KIND_MEMORY}:{key}", owner_id=str(user_id)
        )

    def delete_summary(self, user_id: str, conversation_id: str) -> int:
        return self._store.delete_document(
            CONTINUITY_COLLECTION, f"{KIND_SUMMARY}:{conversation_id}", owner_id=str(user_id)
        )

    # -- retrieval --------------------------------------------------------
    def search(
        self,
        user_id: str,
        query: str,
        *,
        k: int = 6,
        kind: str | None = None,
        min_score: float = 0.25,
    ) -> list[ContinuityHit]:
        """Semantic recall scoped to one user, optionally limited to one kind."""
        if not user_id or not query.strip():
            return []
        where = {"kind": kind} if kind else None
        hits = self._store.query(
            CONTINUITY_COLLECTION, query, n_results=max(1, k), where=where, owner_id=str(user_id)
        )
        out = [
            ContinuityHit(
                kind=str(h.metadata.get("kind", "")),
                text=h.text,
                metadata=h.metadata,
                distance=h.distance,
            )
            for h in hits
        ]
        return [hit for hit in out if hit.score >= min_score]

    # -- internal ---------------------------------------------------------
    def _upsert(self, user_id: str, doc_id: str, text: str, meta: dict[str, Any]) -> None:
        text = (text or "").strip()
        if not text or not user_id:
            return
        metadata: dict[str, str | int | float | bool] = {
            "owner_id": str(user_id),
            "doc_id": doc_id,
            "file_type": "continuity",
            "page": -1,
            "chunk_index": 0,
        }
        for key, value in meta.items():
            if value is not None:
                metadata[key] = value if isinstance(value, str | int | float | bool) else str(value)
        self._store.add_chunks(
            CONTINUITY_COLLECTION,
            [Chunk(id=f"{user_id}:{doc_id}:0", text=text, metadata=metadata)],
            owner_id=str(user_id),
        )
