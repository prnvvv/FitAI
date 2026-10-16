"""Owner-scoped continuity vectors: memory facts and per-conversation summaries.

Backed by the ``user_continuity`` Chroma collection. Every operation is filtered
by ``owner_id`` so semantic recall can never cross users. Memory facts and
conversation summaries share the collection but are distinguished by the
``kind`` metadata field, which lets retrieval ask for one or both.

This layer is best-effort: callers treat a :class:`VectorStoreError` as "no
recall available" rather than failing the turn.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from .chunker import Chunk
from .vector_store import CONTINUITY_COLLECTION, VectorStore

log = logging.getLogger(__name__)

KIND_MEMORY = "memory"
KIND_SUMMARY = "summary"


def _text_hash(text: str) -> str:
    """Stable fingerprint of an indexed fact's text."""
    return hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:16]


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
        """Make the stored memory vectors equal ``memories`` (incremental).

        ``memories`` maps a memory key to its display text. Only records whose
        text actually changed are re-embedded; keys absent from the map are
        removed so a deleted or superseded fact stops being recalled. The result
        is identical to a full re-index, but an unchanged fact costs a metadata
        read instead of an embedding.

        Documents are identified by the stable id ``<owner>:<kind>:<key>:0``, so
        re-indexing is an upsert of the same vector rather than a duplicate, and
        retrieval sees a change on the very next turn.
        """
        if not user_id:
            return
        wanted = {key: text for key, text in memories.items() if (text or "").strip()}
        indexed: dict[str, str] = {}
        for hit in self._store.list_vectors(
            CONTINUITY_COLLECTION, owner_id=str(user_id), where={"kind": KIND_MEMORY}
        ):
            key = str(hit.metadata.get("key", ""))
            if key:
                indexed[key] = str(hit.metadata.get("text_hash", ""))

        changed: list[tuple[str, str]] = []
        for key, text in wanted.items():
            digest = _text_hash(text)
            if indexed.get(key) != digest:
                changed.append((key, text))
        # Batch the upserts so one embedding call covers every changed fact.
        if changed:
            self._upsert_many(user_id, changed)
        for key in indexed:
            if key not in wanted:
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
    def _upsert_many(self, user_id: str, items: list[tuple[str, str]]) -> None:
        """Upsert several memory facts (key, text) in one embedding batch."""
        chunks = [
            Chunk(
                id=f"{user_id}:{KIND_MEMORY}:{key}:0",
                text=text,
                metadata=self._metadata(
                    user_id,
                    f"{KIND_MEMORY}:{key}",
                    {"kind": KIND_MEMORY, "key": key, "source": "memory"},
                    text,
                ),
            )
            for key, text in items
        ]
        self._store.add_chunks(CONTINUITY_COLLECTION, chunks, owner_id=str(user_id))

    def _upsert(self, user_id: str, doc_id: str, text: str, meta: dict[str, Any]) -> None:
        stripped = (text or "").strip()
        if not stripped or not user_id:
            return
        self._store.add_chunks(
            CONTINUITY_COLLECTION,
            [
                Chunk(
                    id=f"{user_id}:{doc_id}:0",
                    text=stripped,
                    metadata=self._metadata(user_id, doc_id, meta, stripped),
                )
            ],
            owner_id=str(user_id),
        )

    @staticmethod
    def _metadata(
        user_id: str, doc_id: str, meta: dict[str, Any], text: str
    ) -> dict[str, str | int | float | bool]:
        """Owner-scoped metadata for one continuity vector.

        ``text_hash`` lets :meth:`sync_memories` skip unchanged facts without
        re-embedding them, and detect when a record really changed.
        """
        stripped = (text or "").strip()
        metadata: dict[str, str | int | float | bool] = {
            "owner_id": str(user_id),
            "doc_id": doc_id,
            "file_type": "continuity",
            "page": -1,
            "chunk_index": 0,
            "text_hash": _text_hash(stripped),
        }
        for key, value in meta.items():
            if value is not None:
                metadata[key] = value if isinstance(value, str | int | float | bool) else str(value)
        return metadata
