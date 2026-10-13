"""In-memory TTL cache for web tools.

Personal data is never cached across users. Keys include the user id or a
session marker so two users never share lookup results.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, Generic, TypeVar

from app.core.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T")


class _CacheEntry(Generic[T]):
    def __init__(self, value: T, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class WebCache:
    """Simple thread-safe-ish in-memory TTL cache."""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.web_cache_ttl_seconds
        self._store: dict[str, _CacheEntry[Any]] = {}

    def _key(self, user_id: str, namespace: str, query: str) -> str:
        normalized = re.sub(r"\s+", " ", query.strip().lower())
        digest = hashlib.sha256(f"{user_id}:{namespace}:{normalized}".encode()).hexdigest()[:32]
        return digest

    def get(self, user_id: str, namespace: str, query: str) -> Any | None:
        key = self._key(user_id, namespace, query)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._store.pop(key, None)
            return None
        log.debug("cache hit: %s", namespace)
        return entry.value

    def set(self, user_id: str, namespace: str, query: str, value: Any) -> None:
        if self._ttl <= 0:
            return
        key = self._key(user_id, namespace, query)
        self._store[key] = _CacheEntry(value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()


# Singleton cache for the process.
web_cache = WebCache()
