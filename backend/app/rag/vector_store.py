"""Persistent ChromaDB collections: indexing, search, filtering, deletion.

Two collections: curated knowledge (shared) and user documents (owner-scoped).
Every user-collection operation requires `owner_id` and is filtered by it.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings

from .chunker import Chunk
from .embeddings import EMBEDDING_NAME, get_embedding_function

log = logging.getLogger(__name__)

KNOWLEDGE_COLLECTION = "fitness_knowledge"
USER_COLLECTION = "user_documents"
_BATCH = 100


class VectorStoreError(Exception):
    """Chroma operation failed (possibly transient)."""


@dataclass(frozen=True)
class SearchHit:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float  # cosine distance; lower is closer


FilterDict = dict[str, Any]


def _and(*filters: FilterDict | None) -> FilterDict | None:
    parts = [f for f in filters if f]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"$and": parts}


def _persist_path(persist_dir: str | None) -> str:
    return persist_dir or os.getenv("CHROMA_PERSIST_DIR") or "./data/chroma"


class VectorStore:
    def __init__(
        self, persist_dir: str | None = None, client: Any = None, embedding_function: Any = None
    ):
        """`persist_dir` should come from project config; env CHROMA_PERSIST_DIR is the fallback."""
        self._client = client or chromadb.PersistentClient(
            path=_persist_path(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._ef = embedding_function or get_embedding_function()
        self._cols: dict[str, Any] = {}

    def _col(self, name: str) -> Any:
        if name not in (KNOWLEDGE_COLLECTION, USER_COLLECTION):
            raise ValueError(f"unknown collection {name!r}")
        if name not in self._cols:
            try:
                col = self._client.get_or_create_collection(
                    name=name,
                    embedding_function=self._ef,
                    metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_NAME},
                )
            except Exception as exc:
                raise VectorStoreError(f"cannot open collection {name}: {exc}") from exc
            stored = (col.metadata or {}).get("embedding_model")
            if stored and stored != EMBEDDING_NAME:
                raise VectorStoreError(
                    f"collection {name} was built with {stored}; re-index required"
                )
            self._cols[name] = col
        return self._cols[name]

    @staticmethod
    def _scope(
        collection: str, owner_id: str | None, where: FilterDict | None
    ) -> FilterDict | None:
        if collection == USER_COLLECTION:
            if not owner_id or not owner_id.strip():
                raise PermissionError("owner_id is required for user documents")
            return _and({"owner_id": owner_id}, where)
        return where or None

    def add_chunks(
        self, collection: str, chunks: Sequence[Chunk], owner_id: str | None = None
    ) -> int:
        """Upsert chunks. User chunks must carry metadata owner_id == owner_id."""
        self._scope(collection, owner_id, None)
        if collection == USER_COLLECTION and any(
            c.metadata.get("owner_id") != owner_id for c in chunks
        ):
            raise PermissionError("chunk owner_id does not match owner_id")
        col = self._col(collection)
        try:
            for i in range(0, len(chunks), _BATCH):
                b = chunks[i : i + _BATCH]
                col.upsert(
                    ids=[c.id for c in b],
                    documents=[c.text for c in b],
                    metadatas=[c.metadata for c in b],
                )
        except Exception as exc:
            raise VectorStoreError(f"indexing failed: {exc}") from exc
        return len(chunks)

    def query(
        self,
        collection: str,
        text: str,
        n_results: int = 4,
        where: FilterDict | None = None,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        """Similarity search with optional metadata filter."""
        if n_results < 1:
            raise ValueError("n_results must be >= 1")
        scoped = self._scope(collection, owner_id, where)
        if not text.strip():
            return []
        col = self._col(collection)
        try:
            res = col.query(
                query_texts=[text],
                n_results=n_results,
                where=scoped,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError(f"query failed: {exc}") from exc
        ids, docs = res["ids"][0], res["documents"][0]
        metas, dists = res["metadatas"][0], res["distances"][0]
        return [
            SearchHit(i, d, dict(m or {}), float(x))
            for i, d, m, x in zip(ids, docs, metas, dists, strict=False)
        ]

    def delete_document(self, collection: str, doc_id: str, owner_id: str | None = None) -> int:
        """Delete all vectors of one document. Returns the number removed."""
        scoped = self._scope(collection, owner_id, {"doc_id": doc_id})
        col = self._col(collection)
        try:
            ids = col.get(where=scoped, include=[])["ids"]
            for i in range(0, len(ids), _BATCH):
                col.delete(ids=ids[i : i + _BATCH])
        except Exception as exc:
            raise VectorStoreError(f"delete failed: {exc}") from exc
        return len(ids)

    def count(self, collection: str, owner_id: str | None = None) -> int:
        scoped = self._scope(collection, owner_id, None)
        col = self._col(collection)
        try:
            return len(col.get(where=scoped, include=[])["ids"]) if scoped else col.count()
        except Exception as exc:
            raise VectorStoreError(f"count failed: {exc}") from exc
