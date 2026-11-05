"""Token verification: issuer, audience, expiry, algorithm and subject are all enforced."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import TokenVerifier

SECRET = "unit-test-secret-unit-test-secret-1234"
ISSUER = "https://example.supabase.co/auth/v1"


def _verifier() -> TokenVerifier:
    return TokenVerifier(
        Settings(
            _env_file=None,
            supabase_url="https://example.supabase.co",
            supabase_jwt_secret=SECRET,
            supabase_jwt_audience="authenticated",
        )
    )


def _claims(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "iss": ISSUER,
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    base.update(over)
    return base


def _enc(claims: dict[str, object]) -> str:
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_wrong_issuer_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        _verifier().verify(_enc(_claims(iss="https://evil.example/auth/v1")))


def test_missing_issuer_is_rejected() -> None:
    claims = _claims()
    del claims["iss"]
    with pytest.raises(AuthenticationError):
        _verifier().verify(_enc(claims))


def test_wrong_audience_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        _verifier().verify(_enc(_claims(aud="anon")))


def test_missing_expiry_is_rejected() -> None:
    claims = _claims()
    del claims["exp"]
    with pytest.raises(AuthenticationError):
        _verifier().verify(_enc(claims))


def test_non_uuid_subject_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        _verifier().verify(_enc(_claims(sub="admin")))


def test_alg_none_token_is_rejected() -> None:
    def b64(obj: dict[str, object]) -> str:
        raw = json.dumps(obj, default=str).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    claims = _claims(exp=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()))
    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."
    with pytest.raises(AuthenticationError):
        _verifier().verify(forged)


def test_public_health_endpoints_do_not_leak_configuration(anon_client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(type(settings), "is_production", property(lambda _s: True))
    body = anon_client.get("/health/guardrails").json()
    assert body == {"enabled": settings.guardrails_enabled}
    assert anon_client.get("/health").json() == {"status": "ok"}
