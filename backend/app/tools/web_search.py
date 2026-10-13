"""Web search tool using DuckDuckGo.

No API key is required. Results are returned as-is and must not be fabricated.
"""

from __future__ import annotations

import logging
from typing import Any

from duckduckgo_search import DDGS

log = logging.getLogger(__name__)


def web_search(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """Search the web with DuckDuckGo and return ranked results.

    Args:
        query: The search query.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A dict with ``query`` and ``results`` (list of title/snippet/url dicts).
        On failure, ``results`` is empty and ``error`` describes the issue.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        log.warning("web search failed: %s", exc)
        return {"query": query, "results": [], "error": f"Search unavailable: {type(exc).__name__}"}

    return {
        "query": query,
        "results": [
            {
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            }
            for r in results
        ],
    }
