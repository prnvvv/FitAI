"""HTTP-level hardening shared by every FitAI service: security headers and rate limits.

Both are pure ASGI middleware (not ``BaseHTTPMiddleware``) so they add no body
buffering and stay safe for streaming responses.

* :class:`SecurityHeadersMiddleware` adds the response headers a browser needs to
  refuse framing, MIME sniffing, downgrade and over-broad referrers. Headers set
  by a route (for example the SPA's own CSP) are never overwritten.
* :class:`RateLimitMiddleware` is an in-process sliding-window limiter. The
  production image runs exactly one worker, so in-process state is accurate; a
  multi-worker deployment must replace it with a shared store (documented in
  ``docs/SECURITY_AUDIT.md``).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.core.logging import get_logger

logger = get_logger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# --------------------------------------------------------------------------- #
# Security headers
# --------------------------------------------------------------------------- #

#: JSON API responses never need to load anything or be framed.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(self), gyroscope=(), magnetometer=(), "
    "microphone=(self), payment=(), usb=()"
)
HSTS = "max-age=63072000; includeSubDomains"


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def build_app_csp(supabase_url: str | None, extra_connect: Sequence[str] = ()) -> str:
    """CSP for the served single-page app.

    ``connect-src`` allows the API itself, the Supabase project (REST + realtime
    websocket) and any explicitly configured extra origins. Google Fonts are the
    only third-party assets the shell loads. ``style-src 'unsafe-inline'`` is
    required because React renders inline ``style`` attributes; scripts stay
    strictly ``'self'``.
    """
    connect = ["'self'"]
    supabase = _origin(supabase_url)
    if supabase:
        connect.append(supabase)
        connect.append(supabase.replace("https://", "wss://", 1))
    connect.extend(extra_connect)
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: blob: https:",
            f"connect-src {' '.join(connect)}",
            "media-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


class SecurityHeadersMiddleware:
    """Add baseline security headers to every HTTP response."""

    def __init__(self, app: ASGIApp, *, hsts: bool, api_prefix: str = "/api/") -> None:
        self.app = app
        self._hsts = hsts
        self._api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope.get("path", "").startswith(self._api_prefix)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}

                def add(name: str, value: str) -> None:
                    if name.encode().lower() not in present:
                        headers.append((name.encode(), value.encode()))

                add("X-Content-Type-Options", "nosniff")
                add("X-Frame-Options", "DENY")
                add("Referrer-Policy", "strict-origin-when-cross-origin")
                add("Permissions-Policy", PERMISSIONS_POLICY)
                add("Cross-Origin-Opener-Policy", "same-origin")
                if is_api:
                    add("Content-Security-Policy", API_CSP)
                    # Authenticated user data must never be stored by a shared cache.
                    add("Cache-Control", "no-store")
                if self._hsts:
                    add("Strict-Transport-Security", HSTS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RateRule:
    """``limit`` requests per ``window_s`` for matching requests, per client."""

    name: str
    path_prefix: str
    limit: int
    window_s: float = 60.0
    methods: frozenset[str] | None = None

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method not in self.methods:
            return False
        return path.startswith(self.path_prefix)


class SlidingWindowLimiter:
    """Thread-safe sliding-window counter keyed by an arbitrary string."""

    def __init__(self, max_keys: int = 20_000) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def _prune(self, key: str, now: float, window_s: float) -> deque[float]:
        bucket = self._events.setdefault(key, deque())
        while bucket and bucket[0] <= now - window_s:
            bucket.popleft()
        return bucket

    def hit(self, key: str, limit: int, window_s: float, *, now: float | None = None) -> float:
        """Record one event. Return 0 if allowed, else seconds until a slot frees."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._events) > self._max_keys:
                self._evict(now)
            bucket = self._prune(key, now, window_s)
            if len(bucket) >= limit:
                return max(bucket[0] + window_s - now, 0.001)
            bucket.append(now)
            return 0.0

    def count(self, key: str, window_s: float, *, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._events.get(key)
            if bucket is None:
                return 0
            return len(self._prune(key, now, window_s))

    def record(self, key: str, window_s: float, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(key, now, window_s).append(now)

    def reset(self) -> None:
        """Forget all counters (used by tests)."""
        with self._lock:
            self._events.clear()

    def _evict(self, now: float) -> None:
        # Bound memory under a key-flood: drop stale buckets first, then the oldest.
        for key in [k for k, v in self._events.items() if not v or v[-1] < now - 3600]:
            del self._events[key]
        while len(self._events) > self._max_keys:
            del self._events[next(iter(self._events))]


#: Process-wide state shared by every limiter instance built without an explicit one.
GLOBAL_LIMITER = SlidingWindowLimiter()


def client_ip(scope: Scope, *, trust_proxy: bool) -> str:
    """Best-effort client address.

    Behind a single trusted reverse proxy (Render) the proxy *appends* the real
    peer to ``X-Forwarded-For``, so the **rightmost** entry is the only one a
    client cannot forge. Earlier entries are attacker-controlled and ignored.
    """
    if trust_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                parts = [p.strip() for p in value.decode("latin-1").split(",") if p.strip()]
                if parts:
                    return parts[-1][:64]
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def default_rules(
    *,
    api_per_minute: int,
    chat_per_minute: int,
    upload_per_minute: int,
    location_per_minute: int,
    api_prefix: str,
) -> list[RateRule]:
    """Rules, most specific first. Expensive LLM/embedding/geocoding paths are tightest."""
    prefix = api_prefix.rstrip("/")
    write = frozenset({"POST", "PUT", "PATCH", "DELETE"})
    return [
        RateRule("chat", f"{prefix}/chat", chat_per_minute, 60.0, frozenset({"POST"})),
        RateRule("upload", f"{prefix}/documents", upload_per_minute, 60.0, frozenset({"POST"})),
        RateRule("location", f"{prefix}/location", location_per_minute, 60.0),
        RateRule("writes", prefix + "/", api_per_minute, 60.0, write),
        RateRule("api", prefix + "/", api_per_minute * 2, 60.0),
    ]


class RateLimitMiddleware:
    """Per-client sliding-window limits plus a brute-force guard on failed auth.

    Only paths under ``api_prefix`` are limited; health probes and the static app
    are exempt. Every matching rule is charged, so a chat POST counts against the
    ``chat`` rule *and* the general ``writes``/``api`` ceilings.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        rules: Sequence[RateRule],
        api_prefix: str,
        trust_proxy: bool,
        auth_failure_limit: int = 20,
        auth_failure_window_s: float = 300.0,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.app = app
        self._rules = list(rules)
        self._prefix = api_prefix.rstrip("/") + "/"
        self._trust_proxy = trust_proxy
        self._fail_limit = auth_failure_limit
        self._fail_window = auth_failure_window_s
        self._limiter = limiter or GLOBAL_LIMITER

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self._prefix):
            await self.app(scope, receive, send)
            return
        if scope.get("method") == "OPTIONS":  # CORS preflight carries no credentials
            await self.app(scope, receive, send)
            return

        ip = client_ip(scope, trust_proxy=self._trust_proxy)
        method, path = scope["method"], scope["path"]

        fail_key = f"authfail:{ip}"
        if self._limiter.count(fail_key, self._fail_window) >= self._fail_limit:
            logger.warning("rate_limited", rule="auth_failures", client=ip, path=path)
            await self._reject(scope, send, retry_after=self._fail_window)
            return

        for rule in self._rules:
            if not rule.matches(method, path):
                continue
            retry_after = self._limiter.hit(f"{rule.name}:{ip}", rule.limit, rule.window_s)
            if retry_after:
                logger.warning("rate_limited", rule=rule.name, client=ip, path=path)
                await self._reject(scope, send, retry_after=retry_after)
                return

        async def send_tracking_auth(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 401:
                self._limiter.record(fail_key, self._fail_window)
                logger.warning(
                    "auth_failure", status=message["status"], client=ip, path=path, method=method
                )
            await send(message)

        await self.app(scope, receive, send_tracking_auth)

    @staticmethod
    async def _reject(scope: Scope, send: Send, *, retry_after: float) -> None:
        seconds = max(int(retry_after) + 1, 1)
        request_id = uuid.uuid4().hex[:16]
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                request_id = value.decode("latin-1")[:64]
        body = json.dumps(
            {
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please slow down and retry shortly.",
                    "details": {"retry_after_seconds": seconds},
                    "request_id": request_id,
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(seconds).encode()),
                    (b"x-request-id", request_id.encode("latin-1", "ignore")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
