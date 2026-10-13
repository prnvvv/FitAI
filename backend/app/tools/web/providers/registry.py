"""Provider registry with ordered fallback, retry and circuit breaker."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from app.core.config import settings
from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.base import SearchProvider
from app.tools.web.providers.brave import BraveProvider
from app.tools.web.providers.ddgs import DdgsProvider
from app.tools.web.providers.serper import SerperProvider
from app.tools.web.providers.tavily import TavilyProvider

log = logging.getLogger(__name__)

CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_COOLDOWN_SECONDS = 60

_PROVIDER_CLASSES: dict[str, type[SearchProvider]] = {
    "tavily": TavilyProvider,
    "brave": BraveProvider,
    "serper": SerperProvider,
    "ddgs": DdgsProvider,
}


class _Circuit:
    """Simple per-provider circuit breaker."""

    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.last_failure: dict[str, float] = {}

    def is_open(self, name: str) -> bool:
        if self.failures.get(name, 0) < CIRCUIT_FAILURE_THRESHOLD:
            return False
        last = self.last_failure.get(name, 0)
        if time.monotonic() - last > CIRCUIT_COOLDOWN_SECONDS:
            # cool-down expired; half-open
            self.failures[name] = 0
            return False
        return True

    def record(self, name: str, failed: bool) -> None:
        if failed:
            self.failures[name] = self.failures.get(name, 0) + 1
            self.last_failure[name] = time.monotonic()
        else:
            self.failures[name] = 0


class SearchClient:
    """Search across configured providers, falling back on failure."""

    def __init__(self, providers: list[str] | None = None) -> None:
        names = providers or settings.search_providers or ["ddgs"]
        self._providers: list[SearchProvider] = []
        for name in names:
            cls = _PROVIDER_CLASSES.get(name)
            if cls is None:
                log.warning("unknown search provider: %s", name)
                continue
            provider = cls()
            if provider.is_available():
                self._providers.append(provider)
            else:
                log.debug("search provider %s not available (no key)", name)
        if not self._providers:
            log.warning("no configured search providers available; falling back to ddgs")
            self._providers = [DdgsProvider()]
        self._circuit = _Circuit()

    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        """Try providers in order with one retry and circuit breaker."""
        last_error = "No providers available"
        for provider in self._providers:
            if self._circuit.is_open(provider.name):
                log.debug("provider %s circuit open; skipping", provider.name)
                continue
            for attempt in range(2):
                try:
                    response = provider.search(query, max_results=max_results, freshness=freshness)
                    if response.error:
                        raise RuntimeError(response.error)
                    self._circuit.record(provider.name, failed=False)
                    return response
                except Exception as exc:
                    log.warning(
                        "search attempt %s with %s failed: %s", attempt + 1, provider.name, exc
                    )
                    if attempt == 0:
                        time.sleep(random.uniform(0.2, 0.6))
            self._circuit.record(provider.name, failed=True)
            last_error = f"{provider.name} failed"

        return WebSearchResponse(query=query, results=[], provider="fallback", error=last_error)

    def search_all(
        self,
        queries: list[str],
        *,
        max_results: int = 5,
        freshness: str | None = None,
    ) -> list[SearchResult]:
        """Run several queries across the chain and deduplicate by URL."""
        seen: set[str] = set()
        out: list[SearchResult] = []
        for q in queries:
            response = self.search(q, max_results=max_results, freshness=freshness)
            for r in response.results:
                if r.url in seen:
                    continue
                seen.add(r.url)
                out.append(r)
        return out

    def health(self) -> list[dict[str, Any]]:
        return [p.health() for p in self._providers]
