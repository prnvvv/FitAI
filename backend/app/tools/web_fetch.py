"""Fetch and extract readable text from a web page.

Used to enrich search results with actual source content when the publisher
allows simple HTTP access. Falls back gracefully when a site blocks bots or
returns non-HTML content.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any

import httpx

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 12.0
USER_AGENT = "FitAI/0.1 (fitness research assistant; contact: support@example.com)"
MAX_TEXT_LEN = 3000


class _TextExtractor(HTMLParser):
    """Naive HTML-to-text extractor that ignores scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []
        self._title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "nav", "footer", "header"}:
            self._skip += 1
        if lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "nav", "footer", "header"}:
            self._skip = max(0, self._skip - 1)
        if lowered == "title":
            self._in_title = False
        if lowered in {"p", "div", "li", "h1", "h2", "h3", "h4", "br"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip > 0:
            return
        if self._in_title:
            self._title = data.strip() or self._title
        else:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        # collapse whitespace
        cleaned = re.sub(r"\s+", " ", raw).strip()
        return cleaned[:MAX_TEXT_LEN]

    @property
    def title(self) -> str | None:
        return self._title


def fetch_url(url: str) -> dict[str, Any]:
    """Fetch a URL and return extracted title + text.

    Returns:
        A dict with ``url``, ``title``, ``text`` and optionally ``error``.
    """
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return {
                    "url": url,
                    "title": None,
                    "text": "",
                    "error": f"Non-HTML content type: {content_type}",
                }
            extractor = _TextExtractor()
            extractor.feed(response.text)
            return {
                "url": url,
                "title": extractor.title or url,
                "text": extractor.text(),
            }
    except Exception as exc:
        log.warning("fetch_url failed for %s: %s", url, exc)
        return {
            "url": url,
            "title": url,
            "text": "",
            "error": f"Could not retrieve page: {type(exc).__name__}: {exc}",
        }
