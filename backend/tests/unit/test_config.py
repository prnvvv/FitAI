"""Unit tests for configuration parsing."""

from __future__ import annotations

from app.core.config import Settings


def test_cors_origins_parses_comma_separated_string() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_jwt_algorithms_parses_comma_separated_string() -> None:
    settings = Settings(supabase_jwt_algorithms="ES256,RS256")
    assert settings.supabase_jwt_algorithms == ["ES256", "RS256"]


def test_jwks_and_issuer_derive_from_url() -> None:
    settings = Settings(supabase_url="https://example.supabase.co/")
    assert settings.jwks_url == "https://example.supabase.co/auth/v1/.well-known/jwks.json"
    assert settings.jwt_issuer == "https://example.supabase.co/auth/v1"


def test_is_production_flag() -> None:
    production = Settings(
        environment="production",
        debug=False,
        database_url="postgresql://u:p@db.example.com/fitai",
        cors_origins=["https://fitai.example.com"],
        supabase_url="https://abc.supabase.co",
        groq_api_key="gsk_test",
        document_storage_backend="local",
    )
    assert production.is_production is True
    assert Settings(environment="development").is_production is False
