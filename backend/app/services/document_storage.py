"""Original-file storage abstraction for uploaded documents.

Backends: ``local`` (development only: not durable on Render), ``supabase``
(private Supabase Storage bucket; production) and ``unconfigured`` (refuses writes).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

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
    """Private Supabase Storage bucket, accessed through its REST API.

    Uses the service-role key, which must only ever exist in the backend's
    environment. Uploads never overwrite (``x-upsert: false``): keys are
    ``<user_id>/<document_id>`` with a fresh document id, so a collision means a
    bug, not a replace. Requests use a bounded timeout and the response body is
    never logged (it can echo credentials).
    """

    backend_name = "supabase"

    def __init__(
        self,
        base_url: str | None = None,
        service_key: str | None = None,
        bucket: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        # An explicit "" means "unset" (do not fall back to the environment).
        base = settings.supabase_url if base_url is None else base_url
        self._base = (base or "").rstrip("/")
        self._key = settings.supabase_service_role_key if service_key is None else service_key
        self._bucket = settings.supabase_storage_bucket if bucket is None else bucket
        self.is_configured = bool(self._base and self._key and self._bucket)
        self._client = client

    def _http(self) -> httpx.Client:
        if not self.is_configured:
            raise ServiceUnavailableError(
                "Supabase Storage is not configured. Set SUPABASE_URL, "
                "SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET."
            )
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(settings.supabase_storage_timeout_s, connect=10.0)
            )
        return self._client

    def _url(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ServiceUnavailableError("Refusing to access an invalid storage key.")
        quoted = "/".join(quote(part, safe="") for part in key.split("/"))
        return f"{self._base}/storage/v1/object/{quote(self._bucket, safe='')}/{quoted}"

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._key}", "apikey": str(self._key)}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _send(self, method: str, key: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http().request(method, self._url(key), **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("supabase_storage_unreachable", error_type=type(exc).__name__)
            raise ServiceUnavailableError("Document storage is temporarily unavailable.") from exc

    def save(self, key: str, data: bytes, content_type: str) -> None:
        headers = {**self._headers(content_type), "x-upsert": "false"}
        response = self._send("POST", key, content=data, headers=headers)
        if response.status_code >= 400:
            logger.warning("supabase_storage_save_failed", status=response.status_code)
            raise ServiceUnavailableError("The file could not be stored. Please try again.")

    def delete(self, key: str) -> None:
        response = self._send("DELETE", key, headers=self._headers())
        if response.status_code >= 400 and response.status_code != 404:
            logger.warning("supabase_storage_delete_failed", status=response.status_code)
            raise ServiceUnavailableError("The stored file could not be removed.")

    def read(self, key: str) -> bytes:
        response = self._send("GET", key, headers=self._headers())
        if response.status_code in (400, 404):
            raise ServiceUnavailableError("The stored file is no longer available.")
        if response.status_code >= 400:
            logger.warning("supabase_storage_read_failed", status=response.status_code)
            raise ServiceUnavailableError("The stored file could not be read.")
        return response.content


_SUPABASE: SupabaseDocumentStorage | None = None


def _supabase_singleton() -> SupabaseDocumentStorage:
    """One storage object per process so its HTTP client is shared."""
    global _SUPABASE
    if _SUPABASE is None:
        _SUPABASE = SupabaseDocumentStorage()
    return _SUPABASE


def get_document_storage() -> DocumentStorage:
    """Return the storage backend selected by configuration."""
    backend = settings.document_storage_backend.strip().lower()
    if backend == "local":
        return LocalDocumentStorage(settings.upload_dir)
    if backend == "supabase":
        return _supabase_singleton()
    return UnconfiguredDocumentStorage()
