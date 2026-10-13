"""Shared data models for the web tool layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    """One normalized web-search result."""

    title: str
    url: str
    snippet: str
    source_domain: str
    provider: str
    rank: int
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_domain": self.source_domain,
            "provider": self.provider,
            "rank": self.rank,
            "published_at": self.published_at,
        }


@dataclass
class WebSearchResponse:
    """Result of a web-search provider call."""

    query: str
    results: list[SearchResult]
    provider: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider": self.provider,
            "results": [r.to_dict() for r in self.results],
            "error": self.error,
        }
