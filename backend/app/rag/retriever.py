"""Retrieve fitness knowledge with source metadata and per-user access control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .vector_store import (
    KNOWLEDGE_COLLECTION,
    USER_COLLECTION,
    FilterDict,
    SearchHit,
    VectorStore,
    VectorStoreError,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    score: float  # 1 - cosine distance, clipped to [0, 1]
    scope: str  # "curated" | "user"
    doc_id: str
    page: int | None
    metadata: dict[str, Any]

    def citation(self) -> str:
        return f"{self.source}" + (f" p.{self.page}" if self.page else "")


class Retriever:
    def __init__(self, store: VectorStore, k: int = 4, min_score: float = 0.2):
        self._store, self._k, self._min = store, k, min_score

    def retrieve(
        self,
        query: str,
        user_id: str | None,
        k: int | None = None,
        include_curated: bool = True,
        include_user_docs: bool = True,
        where: FilterDict | None = None,
    ) -> list[RetrievedChunk]:
        """Curated results for everyone; user-document results only for `user_id`.

        A blank user_id gets curated knowledge only. Raises VectorStoreError only if
        every attempted collection failed.
        """
        k = k or self._k
        if k < 1:
            raise ValueError("k must be >= 1")
        uid = user_id.strip() if isinstance(user_id, str) else ""
        plan = []
        if include_curated:
            plan.append((KNOWLEDGE_COLLECTION, "curated"))
        if include_user_docs and uid:
            plan.append((USER_COLLECTION, "user"))

        results: list[RetrievedChunk] = []
        failures = 0
        for collection, scope in plan:
            try:
                hits = self._store.query(
                    collection, query, k, where=where, owner_id=uid if scope == "user" else None
                )
            except VectorStoreError as exc:
                log.warning("retrieval from %s failed: %s", collection, exc)
                failures += 1
                continue
            results += [r for h in hits if (r := self._to_chunk(h, scope, uid)) is not None]
        if plan and failures == len(plan):
            raise VectorStoreError("all retrieval sources failed")

        seen: set[tuple[str, Any | None, str]] = set()
        out: list[RetrievedChunk] = []
        for r in sorted(results, key=lambda r: r.score, reverse=True):
            key = (r.doc_id, r.metadata.get("chunk_index"), r.scope)
            if r.score >= self._min and key not in seen:
                seen.add(key)
                out.append(r)
        return out[:k]

    def search(self, query: str, user_id: str, k: int = 4) -> list[str]:
        """Text form for the agent's `Retriever` protocol: '[source p.N] text'."""
        return [f"[{r.citation()}] {r.text}" for r in self.retrieve(query, user_id, k)]

    @staticmethod
    def _to_chunk(hit: SearchHit, scope: str, uid: str) -> RetrievedChunk | None:
        m = hit.metadata
        if scope == "user" and m.get("owner_id") != uid:  # defence in depth
            log.error("dropping user-scope hit with mismatched owner")
            return None
        page = m.get("page")
        return RetrievedChunk(
            text=hit.text,
            source=str(m.get("source", "unknown")),
            score=max(0.0, min(1.0, 1.0 - hit.distance)),
            scope=scope,
            doc_id=str(m.get("doc_id", hit.id)),
            page=page if isinstance(page, int) and page > 0 else None,
            metadata=m,
        )
