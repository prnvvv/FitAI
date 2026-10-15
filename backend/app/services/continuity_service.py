"""Cross-chat continuity maintenance: best-effort vector cleanup and reindex.

Kept separate from :class:`~app.services.chat_service.ChatService` so lifecycle
endpoints (delete a conversation, delete/correct memory) can reconcile the
owner-scoped continuity vectors without importing the chat pipeline. Every
operation is owner-scoped and best-effort: a missing or unavailable Chroma never
breaks the API call it is attached to.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.rag.continuity_store import ContinuityStore
from app.rag.vector_store import VectorStore

log = logging.getLogger(__name__)


def _store() -> ContinuityStore | None:
    """Return a continuity store, or None when disabled/unavailable."""
    if not settings.continuity_enabled:
        return None
    try:
        return ContinuityStore(VectorStore(persist_dir=settings.chromadb_persist_dir))
    except Exception:
        log.warning("continuity store unavailable", exc_info=True)
        return None


def delete_summary_vector(user_id: UUID, conversation_id: UUID) -> None:
    """Remove the indexed summary for one deleted conversation."""
    store = _store()
    if store is None:
        return
    try:
        store.delete_summary(str(user_id), str(conversation_id))
    except Exception:
        log.warning("summary vector cleanup failed", exc_info=True)


def sync_user_memory_vectors(user_id: UUID, items: Iterable[Any]) -> None:
    """Reconcile a user's memory vectors from their current memory rows.

    ``items`` are ``Memory`` rows exposing ``key`` (a ``MemoryKey``) and
    ``value``. Keys no longer present are pruned, so a deleted or superseded
    fact stops being recalled.
    """
    store = _store()
    if store is None:
        return
    mapping: dict[str, str] = {}
    for item in items:
        value = item.value
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        mapping[item.key.value] = f"{item.key.value}: {value}"
    try:
        store.sync_memories(str(user_id), mapping)
    except Exception:
        log.warning("memory vector sync failed", exc_info=True)
