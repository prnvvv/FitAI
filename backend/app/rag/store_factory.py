"""Select the vector backend (Chroma or pgvector) from configuration."""

from __future__ import annotations

from typing import Any

from app.core.config import settings

BACKENDS = ("chroma", "pgvector")


def vector_backend() -> str:
    """Return the configured backend, rejecting unknown values loudly."""
    backend = settings.vector_store_backend.strip().lower()
    if backend not in BACKENDS:
        raise ValueError(f"VECTOR_STORE_BACKEND must be one of {BACKENDS}, got {backend!r}")
    return backend


def build_vector_store(chroma_cls: type | None = None) -> Any:
    """Return a store for the configured backend.

    ``chroma_cls`` lets call sites keep resolving their own ``VectorStore`` name
    (which tests substitute); it is only used for the Chroma backend.
    """
    if vector_backend() == "pgvector":
        from app.rag.pg_vector_store import PgVectorStore

        return PgVectorStore()
    if chroma_cls is None:
        from app.rag.vector_store import VectorStore

        chroma_cls = VectorStore
    return chroma_cls(persist_dir=settings.chromadb_persist_dir)
