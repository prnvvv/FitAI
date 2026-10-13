"""Base interface for web-search providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.tools.web.models import WebSearchResponse


class SearchProvider(ABC):
    """One web-search provider with a name and a search method."""

    name: str

    @abstractmethod
    def search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> WebSearchResponse:
        """Run a search and return normalized results.

        Args:
            query: The search query.
            max_results: Maximum number of results to return.
            freshness: Optional freshness filter (e.g. "day", "week", "month").
        """
        ...

    def is_available(self) -> bool:
        """Return True if the provider is configured and can be used."""
        return True

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "available": self.is_available()}
