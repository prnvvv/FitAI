"""Serper (Google Search) provider.

Docs: https://serper.dev/docs
Requires a SERPER_API_KEY.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.base import SearchProvider

log = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"
TIMEOUT = 15.0


class SerperProvider(SearchProvider):
    """Serper Google Search API."""

    name = "serper"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.serper_api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        if not self._api_key:
            return WebSearchResponse(
                query=query, results=[], provider=self.name, error="No API key"
            )

        payload: dict[str, object] = {"q": query, "num": max(1, min(max_results, 10))}
        if freshness:
            payload["tbs"] = freshness

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                response = client.post(
                    SERPER_URL,
                    json=payload,
                    headers={"X-API-KEY": self._api_key},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.warning("serper search failed: %s", exc)
            return WebSearchResponse(
                query=query,
                results=[],
                provider=self.name,
                error=f"Serper failed: {type(exc).__name__}",
            )

        organic = data.get("organic", []) if isinstance(data, dict) else []
        results: list[SearchResult] = []
        for rank, item in enumerate(organic[:max_results], start=1):
            url = item.get("link", "")
            results.append(
                SearchResult(
                    title=item.get("title", "") or "Untitled",
                    url=url,
                    snippet=item.get("snippet", ""),
                    source_domain=urlparse(url).netloc or "unknown",
                    provider=self.name,
                    rank=rank,
                    published_at=item.get("date"),
                )
            )

        return WebSearchResponse(query=query, results=results, provider=self.name)
