"""High-level web search tools with caching, limits and fallback."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.tools.web.cache import web_cache
from app.tools.web.limits import ToolBudget, web_rate_limiter
from app.tools.web.providers.registry import SearchClient

log = logging.getLogger(__name__)


class WebSearchKit:
    """Bundle of search client, budget and user id for one turn."""

    def __init__(self, user_id: str, budget: ToolBudget | None = None) -> None:
        self.user_id = user_id
        self.client = SearchClient()
        self.budget = budget or ToolBudget(max_calls=settings.web_max_tool_calls_per_turn)

    def _check_budget(self, tool_name: str, args: dict[str, Any]) -> bool:
        if not self.budget.can_run(tool_name):
            return False
        if not web_rate_limiter.is_allowed(self.user_id):
            log.warning("web rate limit exceeded for user %s", self.user_id)
            return False
        self.budget.spend(tool_name, args)
        web_rate_limiter.record(self.user_id)
        return True

    def web_search(
        self, query: str, *, max_results: int = 5, freshness: str | None = None
    ) -> dict[str, Any]:
        """General web search with provider fallback."""
        args = {"query": query, "max_results": max_results, "freshness": freshness}
        if not self._check_budget("web_search", args):
            return {
                "query": query,
                "results": [],
                "error": "Web search budget or rate limit reached",
            }

        cached = web_cache.get(self.user_id, "web_search", f"{query}:{freshness}:{max_results}")
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        response = self.client.search(query, max_results=max_results, freshness=freshness)
        result: dict[str, Any] = response.to_dict()
        if not response.error:
            web_cache.set(self.user_id, "web_search", f"{query}:{freshness}:{max_results}", result)
        return result

    def news_search(self, query: str, *, days: int = 7, max_results: int = 5) -> dict[str, Any]:
        """News-biased web search. Maps to freshness='week' or 'month'."""
        freshness = "week" if days <= 7 else "month" if days <= 30 else "year"
        # Augment query with news hint if the provider supports it; ddgs ignores freshness.
        result = self.web_search(query, max_results=max_results, freshness=freshness)
        result["news_hint"] = True
        return result


_WEB_KITS: dict[str, WebSearchKit] = {}


def get_web_search_kit(user_id: str) -> WebSearchKit:
    """Return a per-turn search kit."""
    return _WEB_KITS.setdefault(user_id, WebSearchKit(user_id))


def clear_web_search_kit(user_id: str) -> None:
    _WEB_KITS.pop(user_id, None)
