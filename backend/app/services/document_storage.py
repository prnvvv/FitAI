"""Original-file storage abstraction for uploaded documents.

The concrete backend is intentionally undecided: the project owner has not yet
approved Supabase Storage. This module defines the interface and two honest
implementations — a local filesystem backend that is *not* safe for
multi-instance deployment, and an unconfigured backend that refuses writes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentStorage(ABC):
    """Interface for storing and deleting original uploaded files."""

    backend_name: str
    is_configured: bool = False

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Persist ``data`` under ``key``."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object stored under ``key`` if it exists."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Return the bytes stored under ``key``.

        Required to re-run ingestion for an existing document (retry).
        """


class UnconfiguredDocumentStorage(DocumentStorage):
    """Backend used until an approved storage target is configured."""

    backend_name = "unconfigured"
    is_configured = False

    def save(self, key: str, data: bytes, content_type: str) -> None:  # noqa: ARG002
        raise ServiceUnavailableError(
            "Document storage is not configured. Set DOCUMENT_STORAGE_BACKEND "
            "once the storage target is approved."
        )

    def delete(self, key: str) -> None:  # noqa: ARG002
        raise ServiceUnavailableError("Document storage is not configured.")

    def read(self, key: str) -> bytes:  # noqa: ARG002
        raise ServiceUnavailableError("Document storage is not configured.")


class LocalDocumentStorage(DocumentStorage):
    """Local filesystem storage.

    Suitable only for single-instance development. It does not provide
    durability or consistent deletion across multiple application instances.
    """

    backend_name = "local"
    is_configured = True

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise ServiceUnavailableError("Refusing to access a path outside the upload root.")
        return candidate

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise ServiceUnavailableError("The stored file is no longer available.")
        return path.read_bytes()


class SupabaseDocumentStorage(DocumentStorage):
    """Placeholder for the not-yet-approved Supabase Storage backend."""

    backend_name = "supabase"
    is_configured = False

    def save(self, key: str, data: bytes, content_type: str) -> None:  # noqa: ARG002
        raise ServiceUnavailableError(
            "Supabase Storage support has not been implemented. This requires the "
            "project owner's approval and a configured private bucket."
        )

    def delete(self, key: str) -> None:  # noqa: ARG002
        raise ServiceUnavailableError("Supabase Storage support has not been implemented.")

    def read(self, key: str) -> bytes:  # noqa: ARG002
        raise ServiceUnavailableError("Supabase Storage support has not been implemented.")


def get_document_storage() -> DocumentStorage:
    """Return the storage backend selected by configuration."""
    backend = settings.document_storage_backend.strip().lower()
    if backend == "local":
        return LocalDocumentStorage(settings.upload_dir)
    if backend == "supabase":
        return SupabaseDocumentStorage()
    return UnconfiguredDocumentStorage()
