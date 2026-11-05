"""Optional reranking of retrieved chunks with Hugging Face sentence similarity.

``InferenceClient.sentence_similarity`` returns one scalar score per candidate sentence.
It is used here only to *reorder* chunks that the vector store already retrieved:

* it never creates or replaces embeddings and nothing it returns is stored in pgvector;
* chunks keep their original text, metadata, document ids and citations;
* any failure (no token, auth, rate limit, timeout, provider error, malformed reply)
  yields ``None`` so the caller keeps the vector-similarity order. Reranking can degrade
  retrieval at worst back to the baseline; it can never fail a chat request.

One request is made per query, bounded to ``max_candidates`` chunks. After a failure the
reranker sits out for a cooldown so a down provider does not add its timeout to every turn.
The call is synchronous, like the vector query and remote embedding calls it follows; chat
requests already run in FastAPI's worker threads, so the event loop is not blocked.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

from app.core.config import settings

log = logging.getLogger(__name__)

PROVIDER = "hf-inference"
#: Each candidate is truncated before sending; the model only reads its first tokens anyway.
MAX_CANDIDATE_CHARS = 1500
MAX_QUERY_CHARS = 1000

T = TypeVar("T")


class SimilarityClient(Protocol):
    def sentence_similarity(
        self, sentence: str, other_sentences: list[str], *, model: str | None = None
    ) -> list[float]: ...


class SentenceSimilarityReranker:
    def __init__(
        self,
        token: str | None,
        model: str,
        *,
        max_candidates: int = 12,
        timeout_s: float = 8.0,
        cooldown_s: float = 60.0,
        client: SimilarityClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = (token or "").strip()
        self._model = model
        self.max_candidates = max(2, min(int(max_candidates), 50))
        self._timeout_s = timeout_s
        self._cooldown_s = max(0.0, cooldown_s)
        self._client = client
        self._clock = clock
        self._blocked_until = 0.0
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self._token) or self._client is not None

    def _get_client(self) -> SimilarityClient:
        with self._lock:
            if self._client is None:
                from huggingface_hub import InferenceClient  # lazy: only when reranking runs

                self._client = InferenceClient(
                    provider=PROVIDER, api_key=self._token, timeout=self._timeout_s
                )
            return self._client

    def _cooling_down(self) -> bool:
        return self._clock() < self._blocked_until

    def _fail(self, reason: str, exc: BaseException | None = None) -> None:
        # Log the failure class and HTTP status only: never the query, chunk text,
        # request headers or the exception message (which can echo request details).
        status = getattr(getattr(exc, "response", None), "status_code", None)
        log.warning(
            "hf_rerank_failed reason=%s error=%s status=%s",
            reason,
            type(exc).__name__ if exc else "-",
            status if status is not None else "-",
        )
        self._blocked_until = self._clock() + self._cooldown_s

    def scores(self, query: str, texts: Sequence[str]) -> list[float] | None:
        """One similarity score per text, or ``None`` if reranking is unavailable/failed."""
        if not texts or not query.strip():
            return None
        if not self.available:
            self._fail("missing_token")
            return None
        if self._cooling_down():
            return None
        sentences = [t[:MAX_CANDIDATE_CHARS] for t in texts]
        try:
            raw: Any = self._get_client().sentence_similarity(
                query[:MAX_QUERY_CHARS], sentences, model=self._model
            )
        except Exception as exc:  # noqa: BLE001 - auth, 429, timeout, provider/network errors
            self._fail("request_error", exc)
            return None
        if (
            not isinstance(raw, list)
            or len(raw) != len(sentences)
            or not all(isinstance(x, int | float) and not isinstance(x, bool) for x in raw)
        ):
            self._fail("malformed_response")
            return None
        return [float(x) for x in raw]

    def rerank(
        self, query: str, items: Sequence[T], text_of: Callable[[T], str]
    ) -> list[tuple[T, float]] | None:
        """Candidates (at most ``max_candidates``) with scores, best first; ``None`` on failure.

        Ties keep the incoming (vector) order, so the reorder is stable and deterministic.
        """
        pool = list(items)[: self.max_candidates]
        if len(pool) < 2:
            return None  # nothing to reorder: skip the API call
        scores = self.scores(query, [text_of(i) for i in pool])
        if scores is None:
            return None
        order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
        return [(pool[i], scores[i]) for i in order]


_shared: SentenceSimilarityReranker | None = None
_warned_missing_token = False


def get_configured_reranker() -> SentenceSimilarityReranker | None:
    """The process-wide reranker, or ``None`` when reranking is disabled or has no token."""
    global _shared, _warned_missing_token
    if not settings.hf_reranking_enabled:
        return None
    if not (settings.hf_token or "").strip():
        if not _warned_missing_token:
            _warned_missing_token = True
            log.warning("HF_RERANKING_ENABLED is true but no HF_TOKEN is set: reranking is off")
        return None
    if _shared is None:
        _shared = SentenceSimilarityReranker(
            settings.hf_token,
            settings.hf_reranking_model,
            max_candidates=settings.hf_reranking_candidates,
            timeout_s=settings.hf_reranking_timeout_s,
            cooldown_s=settings.hf_reranking_cooldown_s,
        )
    return _shared


def reset_shared_reranker() -> None:
    """Drop the cached instance (tests and settings changes)."""
    global _shared, _warned_missing_token
    _shared, _warned_missing_token = None, False
