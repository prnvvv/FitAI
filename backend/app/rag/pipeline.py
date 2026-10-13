"""Ingestion: load -> chunk -> index (with retries) for curated and user documents."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .chunker import chunk_document
from .loader import SUPPORTED_EXTENSIONS, DocumentLoadError, load_document
from .vector_store import KNOWLEDGE_COLLECTION, USER_COLLECTION, VectorStore, VectorStoreError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    doc_id: str | None
    source: str
    scope: Literal["curated", "user"]
    status: Literal["indexed", "failed"]
    chunks_indexed: int = 0
    attempts: int = 0
    error: str | None = None


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(1 << 20)
            if not block:
                break
            h.update(block)
    return h.hexdigest()[:16]


class IngestionPipeline:
    def __init__(
        self,
        store: VectorStore,
        chunk_size: int = 1000,
        overlap: int = 150,
        max_chunks: int = 2000,
        max_retries: int = 3,
        backoff_s: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._store = store
        self._size, self._overlap, self._max_chunks = chunk_size, overlap, max_chunks
        self._retries, self._backoff, self._sleep = max(1, max_retries), backoff_s, sleep

    def ingest_curated(
        self,
        path: str | Path,
        doc_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionResult:
        return self._ingest(Path(path), KNOWLEDGE_COLLECTION, None, doc_id, metadata)

    def ingest_user_document(
        self,
        path: str | Path,
        user_id: str,
        doc_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionResult:
        """`user_id` must be the authenticated user, never taken from document content."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")
        return self._ingest(Path(path), USER_COLLECTION, user_id, doc_id, metadata)

    def ingest_user_document_bytes(
        self,
        data: bytes,
        filename: str,
        user_id: str,
        doc_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionResult:
        """Ingest document from bytes (avoids temp files when possible)."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")
        if not data:
            return IngestionResult(doc_id, filename, "user", "failed", 0, 0, "file is empty")
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as f:
            f.write(data)
            tmp_path = Path(f.name)
        try:
            result = self._ingest(tmp_path, USER_COLLECTION, user_id, doc_id, metadata)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return result

    def ingest_curated_directory(self, directory: str | Path) -> list[IngestionResult]:
        files = sorted(
            p for p in Path(directory).rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        return [self.ingest_curated(p) for p in files]

    def delete_user_document(self, user_id: str, doc_id: str) -> int:
        """Remove one of the user's documents from the index; returns vectors deleted."""
        return self._store.delete_document(USER_COLLECTION, doc_id, owner_id=user_id)

    def _ingest(
        self,
        path: Path,
        collection: str,
        owner_id: str | None,
        doc_id: str | None,
        metadata: Mapping[str, object] | None,
    ) -> IngestionResult:
        scope: Literal["curated", "user"] = "user" if owner_id else "curated"

        def _fail(err: str, did: str | None = None, n: int = 0) -> IngestionResult:
            return IngestionResult(did, path.name, scope, "failed", 0, n, err)

        try:
            doc = load_document(path)
            did = doc_id or _file_hash(path)
            meta = {**(metadata or {}), "scope": scope}
            prefix = ""
            if owner_id:
                meta["owner_id"] = owner_id
                prefix = hashlib.sha256(owner_id.encode()).hexdigest()[:12] + ":"
            chunks = chunk_document(
                doc, did, meta, self._size, self._overlap, prefix, self._max_chunks
            )
        except (DocumentLoadError, ValueError, OSError) as exc:
            log.info("ingestion rejected %s: %s", path.name, exc)
            return _fail(str(exc))

        last: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                self._store.delete_document(collection, did, owner_id)  # replace, no stale chunks
                n = self._store.add_chunks(collection, chunks, owner_id)
                return IngestionResult(did, path.name, scope, "indexed", n, attempt)
            except PermissionError as exc:
                return _fail(str(exc), did, attempt)
            except VectorStoreError as exc:
                last = exc
                log.warning(
                    "index attempt %d/%d failed for %s: %s", attempt, self._retries, path.name, exc
                )
                if attempt < self._retries:
                    self._sleep(self._backoff * 2 ** (attempt - 1))
        try:  # avoid leaving a partially indexed document
            self._store.delete_document(collection, did, owner_id)
        except Exception:
            log.error("cleanup after failed ingestion of %s also failed", path.name)
        return _fail(f"indexing failed after {self._retries} attempts: {last}", did, self._retries)
