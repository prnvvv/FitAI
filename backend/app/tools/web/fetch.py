"""SSRF-safe web page fetcher."""

from __future__ import annotations

import ipaddress
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

USER_AGENT = "FitAI/0.1 (fitness research assistant; contact: support@example.com)"


class _TextExtractor(HTMLParser):
    """Strip scripts, styles and nav, returning readable text + title."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []
        self._title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "nav", "footer", "header", "aside", "noscript"}:
            self._skip += 1
        if lowered == "title":
            self._in_title = True
        if lowered in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "nav", "footer", "header", "aside", "noscript"}:
            self._skip = max(0, self._skip - 1)
        if lowered == "title":
            self._in_title = False
        if lowered in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
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
        cleaned = re.sub(r"\s+", " ", raw).strip()
        max_bytes = settings.web_max_content_bytes
        return cleaned[:max_bytes]

    @property
    def title(self) -> str | None:
        return self._title


def _is_private(host: str) -> bool:
    """Return True if host is private, loopback, link-local or metadata."""
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
        )
    except ValueError:
        # hostname: resolve to first IP and check
        try:
            import socket

            addrinfo = socket.getaddrinfo(host, None)
            for _, _, _, _, sockaddr in addrinfo:
                ip = ipaddress.ip_address(sockaddr[0])
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                ):
                    return True
        except Exception as exc:
            log.warning("could not resolve host %s: %s", host, exc)
            # Fail safe: block unknown hostnames
            return True
    return False


def fetch_url(url: str) -> dict[str, Any]:
    """Fetch a URL safely and return cleaned text.

    Protects against SSRF by rejecting non-http(s) schemes, private IPs,
    oversized bodies, and too many redirects.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"url": url, "title": None, "text": "", "error": "Only http/https URLs are allowed"}
    if not parsed.hostname:
        return {"url": url, "title": None, "text": "", "error": "URL has no host"}

    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local") or _is_private(host):
        return {
            "url": url,
            "title": None,
            "text": "",
            "error": "Private or internal URLs are not allowed",
        }

    try:
        with httpx.Client(
            timeout=settings.web_fetch_timeout_seconds,
            follow_redirects=True,
            max_redirects=settings.web_max_redirects,
        ) as client:
            response = client.get(
                url,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return {
                    "url": str(response.url),
                    "title": None,
                    "text": "",
                    "error": f"Non-HTML content: {content_type}",
                }

            # Guard against huge bodies even if the parser caps output.
            if len(response.content) > settings.web_max_content_bytes:
                return {
                    "url": str(response.url),
                    "title": None,
                    "text": "",
                    "error": "Page body too large",
                }

            extractor = _TextExtractor()
            extractor.feed(response.text)
            return {
                "url": str(response.url),
                "title": extractor.title or None,
                "text": extractor.text(),
            }
    except Exception as exc:
        log.warning("fetch_url failed for %s: %s", url, exc)
        return {
            "url": url,
            "title": None,
            "text": "",
            "error": f"Could not retrieve page: {type(exc).__name__}: {exc}",
        }
