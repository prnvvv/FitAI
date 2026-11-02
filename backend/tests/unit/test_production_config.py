"""Production start-up guard and database URL normalisation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql://user:pw@db.example.com:5432/fitai",
    "CORS_ORIGINS": "https://fitai.vercel.app",
    "SUPABASE_URL": "https://abc.supabase.co",
    "GROQ_API_KEY": "gsk_test",
    "DOCUMENT_STORAGE_BACKEND": "local",
    "DEBUG": "false",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key, value in {**GOOD, **overrides}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_valid_production_configuration_is_accepted(monkeypatch) -> None:
    s = _settings(monkeypatch)
    assert s.is_production
    assert s.database_url.startswith("postgresql+psycopg2://")


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"DATABASE_URL": "sqlite:///./data.db"}, "PostgreSQL"),
        ({"CORS_ORIGINS": "*"}, "explicit origins"),
        ({"CORS_ORIGINS": "http://localhost:5173"}, "deployed frontend"),
        ({"CORS_ORIGINS": "http://fitai.example.com"}, "https://"),
        ({"SUPABASE_URL": ""}, "SUPABASE_URL"),
        ({"GROQ_API_KEY": ""}, "GROQ_API_KEY"),
        ({"DEBUG": "true"}, "DEBUG"),
        ({"DOCUMENT_STORAGE_BACKEND": "unconfigured"}, "DOCUMENT_STORAGE_BACKEND"),
    ],
)
def test_unsafe_production_configuration_is_rejected(monkeypatch, override, fragment) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, **override)
    assert fragment in str(exc.value)


def test_all_problems_are_reported_together(monkeypatch) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, DEBUG="true", GROQ_API_KEY="", SUPABASE_URL="")
    text = str(exc.value)
    assert "DEBUG" in text and "GROQ_API_KEY" in text and "SUPABASE_URL" in text


def test_development_is_not_restricted(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./x.db")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    assert not Settings(_env_file=None).is_production


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_postgres_urls_use_the_psycopg2_driver(monkeypatch, scheme) -> None:
    monkeypatch.setenv("DATABASE_URL", f"{scheme}u:p@host:5432/db?sslmode=require")
    assert (
        Settings(_env_file=None).database_url
        == "postgresql+psycopg2://u:p@host:5432/db?sslmode=require"
    )


def test_explicit_driver_is_left_alone(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@host/db")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg2://u:p@host/db"


def test_cors_origin_regex_is_optional(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    assert Settings(_env_file=None).cors_origin_regex is None
