"""Tavily search provider.

Docs: https://docs.tavily.com/documentation/api-reference
Requires a TAVILY_API_KEY.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.base import SearchProvider

log = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
TIMEOUT = 15.0

_FRESHNESS_MAP = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}


class TavilyProvider(SearchProvider):
    """Tavily AI search API."""

    name = "tavily"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.tavily_api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        if not self._api_key:
            return WebSearchResponse(
                query=query, results=[], provider=self.name, error="No API key"
            )

        payload: dict[str, object] = {
            "query": query,
            "max_results": max(1, min(max_results, 10)),
            "search_depth": "basic",
            "include_answer": False,
        }
        if freshness and freshness in _FRESHNESS_MAP:
            payload["time_range"] = _FRESHNESS_MAP[freshness]

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.post(
                    TAVILY_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.warning("tavily search failed: %s", exc)
            return WebSearchResponse(
                query=query,
                results=[],
                provider=self.name,
                error=f"Tavily failed: {type(exc).__name__}",
            )

        raw_results = data.get("results", []) if isinstance(data, dict) else []
        results: list[SearchResult] = []
        for rank, item in enumerate(raw_results[:max_results], start=1):
            url = item.get("url", "")
            results.append(
                SearchResult(
                    title=item.get("title", "") or "Untitled",
                    url=url,
                    snippet=item.get("content", "") or item.get("snippet", ""),
                    source_domain=urlparse(url).netloc or "unknown",
                    provider=self.name,
                    rank=rank,
                    published_at=item.get("published_date"),
                )
            )

        return WebSearchResponse(query=query, results=results, provider=self.name)
