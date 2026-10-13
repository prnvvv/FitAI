"""Unit tests for Supabase token verification (symmetric mode, no network)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import TokenVerifier

SECRET = "unit-test-secret"
ISSUER = "https://example.supabase.co/auth/v1"
AUDIENCE = "authenticated"


def _settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret=SECRET,
        supabase_jwt_audience=AUDIENCE,
    )


def _token(**overrides: object) -> str:
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "email": "user@example.com",
        "role": "authenticated",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_valid_token_returns_identity() -> None:
    verifier = TokenVerifier(_settings())
    token = _token()
    auth_user = verifier.verify(token)
    assert auth_user.email == "user@example.com"
    assert auth_user.role == "authenticated"


def test_expired_token_is_rejected() -> None:
    verifier = TokenVerifier(_settings())
    token = _token(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_wrong_signature_is_rejected() -> None:
    verifier = TokenVerifier(_settings())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": AUDIENCE,
            "iss": ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "different-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_disallowed_algorithm_is_rejected() -> None:
    verifier = TokenVerifier(_settings())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": AUDIENCE,
            "iss": ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS512",
    )
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_symmetric_token_rejected_when_no_secret_configured() -> None:
    verifier = TokenVerifier(Settings(supabase_url="https://example.supabase.co"))
    with pytest.raises(AuthenticationError):
        verifier.verify(_token())


def test_missing_subject_is_rejected() -> None:
    verifier = TokenVerifier(_settings())
    token = jwt.encode(
        {
            "aud": AUDIENCE,
            "iss": ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        verifier.verify(token)
