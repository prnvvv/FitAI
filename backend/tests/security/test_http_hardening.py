"""Security headers, rate limiting, CORS and docs exposure."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.http_security import (
    RateLimitMiddleware,
    RateRule,
    SecurityHeadersMiddleware,
    SlidingWindowLimiter,
    build_app_csp,
    client_ip,
    default_rules,
)
from app.main import app as real_app


def _mini_app(
    *,
    hsts: bool = False,
    rules: list[RateRule] | None = None,
    trust_proxy: bool = False,
    auth_failure_limit: int = 3,
) -> FastAPI:
    mini = FastAPI()

    @mini.get("/api/v1/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @mini.post("/api/v1/chat")
    def chat() -> dict[str, str]:
        return {"ok": "yes"}

    @mini.get("/api/v1/secret")
    def secret() -> JSONResponse:
        return JSONResponse({"error": "no"}, status_code=401)

    @mini.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if rules is not None:
        mini.add_middleware(
            RateLimitMiddleware,
            rules=rules,
            api_prefix="/api/v1",
            trust_proxy=trust_proxy,
            auth_failure_limit=auth_failure_limit,
        )
    mini.add_middleware(SecurityHeadersMiddleware, hsts=hsts)
    return mini


# ---- security headers -------------------------------------------------------


def test_api_responses_carry_security_headers() -> None:
    r = TestClient(_mini_app(hsts=True)).get("/api/v1/ping")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert "camera=()" in r.headers["permissions-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_hsts_is_not_sent_when_disabled() -> None:
    r = TestClient(_mini_app(hsts=False)).get("/health")
    assert "strict-transport-security" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_real_app_error_responses_have_headers(anon_client) -> None:
    r = anon_client.get("/api/v1/profile")
    assert r.status_code == 401
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


def test_app_csp_allows_supabase_but_not_arbitrary_script_sources() -> None:
    csp = build_app_csp("https://abc.supabase.co")
    assert "script-src 'self';" in csp
    assert "https://abc.supabase.co" in csp and "wss://abc.supabase.co" in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp


# ---- rate limiting ----------------------------------------------------------


def test_sliding_window_blocks_then_recovers() -> None:
    lim = SlidingWindowLimiter()
    assert lim.hit("k", 2, 10, now=0) == 0
    assert lim.hit("k", 2, 10, now=1) == 0
    assert lim.hit("k", 2, 10, now=2) > 0
    assert lim.hit("k", 2, 10, now=11) == 0  # first event aged out


def test_limiter_memory_is_bounded() -> None:
    lim = SlidingWindowLimiter(max_keys=50)
    for i in range(500):
        lim.hit(f"k{i}", 5, 60, now=float(i))
    assert len(lim._events) <= 51


def test_chat_endpoint_is_rate_limited_with_429_envelope() -> None:
    rules = [RateRule("chat", "/api/v1/chat", 2, 60.0, frozenset({"POST"}))]
    client = TestClient(_mini_app(rules=rules))
    assert client.post("/api/v1/chat").status_code == 200
    assert client.post("/api/v1/chat").status_code == 200
    r = client.post("/api/v1/chat")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["retry-after"]) >= 1
    assert r.headers["x-content-type-options"] == "nosniff"  # headers survive a 429
    assert client.get("/api/v1/ping").status_code == 200  # other routes unaffected


def test_health_and_non_api_paths_are_exempt() -> None:
    client = TestClient(_mini_app(rules=[RateRule("api", "/", 1, 60.0)]))
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_repeated_auth_failures_lock_out_the_client() -> None:
    client = TestClient(_mini_app(rules=[], auth_failure_limit=3))
    assert [client.get("/api/v1/secret").status_code for _ in range(3)] == [401, 401, 401]
    assert client.get("/api/v1/secret").status_code == 429
    assert client.get("/api/v1/ping").status_code == 429  # whole client is throttled


def test_clients_are_limited_independently_by_rightmost_forwarded_ip() -> None:
    rules = [RateRule("chat", "/api/v1/chat", 1, 60.0, frozenset({"POST"}))]
    client = TestClient(_mini_app(rules=rules, trust_proxy=True))
    first = {"X-Forwarded-For": "6.6.6.6, 1.1.1.1"}  # leftmost is attacker-supplied
    spoofed = {"X-Forwarded-For": "7.7.7.7, 1.1.1.1"}
    other = {"X-Forwarded-For": "2.2.2.2"}
    assert client.post("/api/v1/chat", headers=first).status_code == 200
    assert client.post("/api/v1/chat", headers=spoofed).status_code == 429  # same real peer
    assert client.post("/api/v1/chat", headers=other).status_code == 200


def test_forwarded_header_ignored_when_proxy_not_trusted() -> None:
    scope = {"headers": [(b"x-forwarded-for", b"9.9.9.9")], "client": ("1.2.3.4", 1)}
    assert client_ip(scope, trust_proxy=False) == "1.2.3.4"
    assert client_ip(scope, trust_proxy=True) == "9.9.9.9"


def test_default_rules_cover_expensive_endpoints() -> None:
    rules = default_rules(
        api_per_minute=100,
        chat_per_minute=5,
        upload_per_minute=5,
        location_per_minute=5,
        api_prefix="/api/v1",
    )
    assert {"chat", "upload", "location", "writes", "api"} <= {r.name for r in rules}


# ---- CORS & docs ------------------------------------------------------------


def test_cors_rejects_unlisted_origin(anon_client) -> None:
    r = anon_client.options(
        "/api/v1/profile",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_listed_origin_with_restricted_methods(anon_client) -> None:
    r = anon_client.options(
        "/api/v1/profile",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "TRACE" not in r.headers["access-control-allow-methods"]


def test_cors_disallows_unexpected_request_headers(anon_client) -> None:
    r = anon_client.options(
        "/api/v1/profile",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-evil-header",
        },
    )
    assert r.status_code == 400


_PROD = {
    "environment": "production",
    "database_url": "postgresql+psycopg2://u:p@db.example:5432/x",
    "cors_origins": ["https://app.example.com"],
    "supabase_url": "https://abc.supabase.co",
    "groq_api_key": "k",
    "document_storage_backend": "supabase",
    "supabase_service_role_key": "s",
    "serve_documents_routes": True,
}


def test_api_docs_hidden_in_production_and_shown_in_dev() -> None:
    assert Settings(_env_file=None, **_PROD).api_docs_enabled is False
    assert Settings(_env_file=None, environment="development").api_docs_enabled is True
    assert Settings(_env_file=None, expose_api_docs=True, **_PROD).api_docs_enabled is True


def test_production_refuses_to_disable_rate_limiting() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        Settings(_env_file=None, rate_limit_enabled=False, **_PROD)


def test_real_app_registers_limiter_and_headers() -> None:
    names = {m.cls.__name__ for m in real_app.user_middleware}
    assert {"SecurityHeadersMiddleware", "RateLimitMiddleware", "CORSMiddleware"} <= names
