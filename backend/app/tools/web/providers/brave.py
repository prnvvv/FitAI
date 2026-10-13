"""Brave Search API provider.

Docs: https://api.search.brave.com/app/documentation/web-search/get-started
Requires a BRAVE_API_KEY.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.base import SearchProvider

log = logging.getLogger(__name__)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
TIMEOUT = 15.0

_FRESHNESS_MAP = {
    "day": "d",
    "week": "w",
    "month": "m",
    "year": "y",
}


class BraveProvider(SearchProvider):
    """Brave Search API."""

    name = "brave"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.brave_api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        if not self._api_key:
            return WebSearchResponse(
                query=query, results=[], provider=self.name, error="No API key"
            )

        params: dict[str, Any] = {"q": query, "count": max(1, min(max_results, 10))}
        if freshness and freshness in _FRESHNESS_MAP:
            params["freshness"] = _FRESHNESS_MAP[freshness]

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.get(
                    BRAVE_URL,
                    params=params,
                    headers={
                        "X-Subscription-Token": self._api_key,
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.warning("brave search failed: %s", exc)
            return WebSearchResponse(
                query=query,
                results=[],
                provider=self.name,
                error=f"Brave failed: {type(exc).__name__}",
            )

        web_results = data.get("web", {}).get("results", []) if isinstance(data, dict) else []
        results: list[SearchResult] = []
        for rank, item in enumerate(web_results[:max_results], start=1):
            url = item.get("url", "")
            results.append(
                SearchResult(
                    title=item.get("title", "") or "Untitled",
                    url=url,
                    snippet=item.get("description", ""),
                    source_domain=urlparse(url).netloc or "unknown",
                    provider=self.name,
                    rank=rank,
                    published_at=None,  # Brave provides age strings, not ISO dates
                )
            )

        return WebSearchResponse(query=query, results=results, provider=self.name)
