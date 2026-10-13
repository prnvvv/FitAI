"""DuckDuckGo search provider (keyless fallback)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from ddgs import DDGS

from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.base import SearchProvider

log = logging.getLogger(__name__)

TIMEOUT = 15.0


class DdgsProvider(SearchProvider):
    """DuckDuckGo text search via the ``ddgs`` package."""

    name = "ddgs"

    def is_available(self) -> bool:
        return True

    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
        except Exception as exc:
            log.warning("ddgs search failed: %s", exc)
            return WebSearchResponse(
                query=query,
                results=[],
                provider=self.name,
                error=f"DDGS failed: {type(exc).__name__}",
            )

        results: list[SearchResult] = []
        for rank, item in enumerate(raw[:max_results], start=1):
            url = item.get("href", "")
            results.append(
                SearchResult(
                    title=item.get("title", "") or "Untitled",
                    url=url,
                    snippet=item.get("body", ""),
                    source_domain=urlparse(url).netloc or "unknown",
                    provider=self.name,
                    rank=rank,
                    published_at=None,
                )
            )

        return WebSearchResponse(query=query, results=results, provider=self.name)
