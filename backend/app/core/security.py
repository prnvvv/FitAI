"""Supabase access-token verification.

The design supports both signing methods Supabase may use:

* **Asymmetric** (ES256/RS256, the default for newer projects). The public keys
  are fetched from the project's JWKS endpoint and cached. No secret is stored.
* **Legacy symmetric** (HS256). Used only when ``SUPABASE_JWT_SECRET`` is
  explicitly configured.

The token's own ``alg`` header is never trusted on its own: it must appear in
the configured allow-list or verification fails. ``none`` is always rejected.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK
from jwt.exceptions import InvalidTokenError, PyJWKError

from app.core.config import Settings, settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)

SYMMETRIC_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Verified identity derived exclusively from token claims."""

    id: UUID
    email: str | None = None
    role: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


class _JwksCache:
    """Thread-safe, periodically refreshed cache of JWKS public keys."""

    def __init__(self, url: str, ttl_seconds: int) -> None:
        self._url = url
        self._ttl = ttl_seconds
        self._keys: dict[str, Any] = {}
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _load(self) -> None:
        response = httpx.get(self._url, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        keys: dict[str, Any] = {}
        for jwk in payload.get("keys", []):
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                keys[kid] = PyJWK.from_dict(jwk).key
            except (PyJWKError, ValueError) as exc:  # pragma: no cover - defensive
                logger.warning("jwks_key_skipped", kid=kid, error=str(exc))
        self._keys = keys
        self._expires_at = time.monotonic() + self._ttl

    def get_key(self, kid: str | None) -> Any:
        """Return the verification key for ``kid``, refreshing when necessary."""
        with self._lock:
            if not self._keys or time.monotonic() >= self._expires_at:
                self._load()
            if kid is None:
                if len(self._keys) == 1:
                    return next(iter(self._keys.values()))
                raise AuthenticationError("Token is missing a key id ('kid').")
            key = self._keys.get(kid)
            if key is None:
                # Key may have rotated; refresh once before failing.
                self._load()
                key = self._keys.get(kid)
            if key is None:
                raise AuthenticationError("Token was signed with an unknown key.")
            return key


class TokenVerifier:
    """Verifies Supabase access tokens and extracts the authenticated identity."""

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._allowed_algorithms = [
            alg.upper() for alg in config.supabase_jwt_algorithms if alg.lower() != "none"
        ]
        if config.supabase_jwt_secret:
            self._allowed_algorithms.append(SYMMETRIC_ALGORITHM)
        self._jwks: _JwksCache | None = None
        if config.jwks_url:
            self._jwks = _JwksCache(config.jwks_url, config.supabase_jwks_cache_seconds)

    def verify(self, token: str) -> AuthUser:
        """Validate ``token`` and return the authenticated identity.

        Raises:
            AuthenticationError: if the token is missing, malformed, expired,
                signed with a disallowed algorithm, or fails signature checks.
        """
        if not token:
            raise AuthenticationError("No access token was provided.")

        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise AuthenticationError("Malformed access token.") from exc

        algorithm = str(header.get("alg", "")).upper()
        if algorithm not in self._allowed_algorithms:
            raise AuthenticationError("Access token uses a disallowed algorithm.")

        key = self._resolve_key(algorithm, header.get("kid"))

        options = {
            "require": ["exp", "sub"],
            "verify_aud": self._config.supabase_jwt_audience is not None,
        }
        decode_kwargs: dict[str, Any] = {
            "algorithms": [algorithm],
            "options": options,
        }
        if self._config.supabase_jwt_audience:
            decode_kwargs["audience"] = self._config.supabase_jwt_audience
        if self._config.jwt_issuer:
            decode_kwargs["issuer"] = self._config.jwt_issuer

        try:
            claims = jwt.decode(token, key, **decode_kwargs)
        except InvalidTokenError as exc:
            raise AuthenticationError("Access token could not be validated.") from exc

        return self._to_auth_user(claims)

    def _resolve_key(self, algorithm: str, kid: str | None) -> Any:
        if algorithm == SYMMETRIC_ALGORITHM:
            if not self._config.supabase_jwt_secret:
                raise AuthenticationError(
                    "Symmetric token received but no JWT secret is configured."
                )
            return self._config.supabase_jwt_secret
        if self._jwks is None:
            raise AuthenticationError("Supabase JWKS is not configured.")
        return self._jwks.get_key(kid)

    @staticmethod
    def _to_auth_user(claims: dict[str, Any]) -> AuthUser:
        subject = claims.get("sub")
        if not subject:
            raise AuthenticationError("Access token does not identify a user.")
        try:
            user_id = UUID(str(subject))
        except (ValueError, TypeError) as exc:
            raise AuthenticationError("Access token subject is not a valid user id.") from exc
        return AuthUser(
            id=user_id,
            email=claims.get("email"),
            role=claims.get("role"),
            claims=claims,
        )


@lru_cache
def get_token_verifier() -> TokenVerifier:
    """Return a cached TokenVerifier bound to the current settings."""
    return TokenVerifier(settings)
