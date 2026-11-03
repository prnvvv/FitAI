"""Per-service production start-up validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql://user:pw@db.example.com:5432/fitai",
    "CORS_ORIGINS": "https://fitai.vercel.app",
    "SUPABASE_URL": "https://abc.supabase.co",
    "DEBUG": "false",
}

EMBED = {
    "VECTOR_STORE_BACKEND": "pgvector",
    "EMBEDDING_PROVIDER": "remote",
    "EMBEDDING_API_URL": "https://embed.example.com/v1",
    "EMBEDDING_API_KEY": "k",
}

CORE = {
    **BASE,
    **EMBED,
    "FITAI_SERVICE": "core",
    "GROQ_API_KEY": "gsk",
    "SERVE_DOCUMENTS_ROUTES": "false",
}
DOCUMENTS = {
    **BASE,
    **EMBED,
    "FITAI_SERVICE": "documents",
    "DOCUMENT_STORAGE_BACKEND": "supabase",
    "SUPABASE_SERVICE_ROLE_KEY": "srk",
    "INGESTION_MODE": "jobs",
}


def _settings(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], **override: str) -> Settings:
    for key in list(env) + list(override):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**env, **override}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


@pytest.mark.parametrize("env", [CORE, DOCUMENTS], ids=["core", "documents"])
def test_complete_service_configuration_is_accepted(monkeypatch, env) -> None:
    assert _settings(monkeypatch, env).is_production


def _rejected(monkeypatch, env, **override) -> str:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, env, **override)
    return str(exc.value)


def test_documents_does_not_need_a_groq_key_but_core_does(monkeypatch) -> None:
    assert "GROQ_API_KEY" not in _rejected(monkeypatch, DOCUMENTS, SUPABASE_SERVICE_ROLE_KEY="")
    assert "GROQ_API_KEY" in _rejected(monkeypatch, CORE, GROQ_API_KEY="")


def test_no_speech_to_text_settings_remain() -> None:
    """Dictation runs in the browser; the backend carries no STT configuration."""
    assert [name for name in Settings.model_fields if "stt" in name.split("_")] == []
    assert "serve_stt_routes" not in Settings.model_fields


def test_pgvector_requires_a_remote_embedding_provider(monkeypatch) -> None:
    assert "EMBEDDING_PROVIDER must be 'remote'" in _rejected(
        monkeypatch, CORE, EMBEDDING_PROVIDER="local"
    )
    assert "EMBEDDING_API_URL" in _rejected(monkeypatch, CORE, EMBEDDING_API_URL="")


def test_documents_service_requires_jobs_pgvector_and_durable_storage(monkeypatch) -> None:
    assert "INGESTION_MODE" in _rejected(monkeypatch, DOCUMENTS, INGESTION_MODE="inline")
    assert "VECTOR_STORE_BACKEND" in _rejected(
        monkeypatch, DOCUMENTS, VECTOR_STORE_BACKEND="chroma"
    )
    assert "DOCUMENT_STORAGE_BACKEND" in _rejected(
        monkeypatch, DOCUMENTS, DOCUMENT_STORAGE_BACKEND="unconfigured"
    )
    assert "SUPABASE_SERVICE_ROLE_KEY" in _rejected(
        monkeypatch, DOCUMENTS, SUPABASE_SERVICE_ROLE_KEY=""
    )


def test_core_without_document_routes_does_not_need_document_storage(monkeypatch) -> None:
    s = _settings(monkeypatch, CORE, DOCUMENT_STORAGE_BACKEND="unconfigured")
    assert s.document_storage_backend == "unconfigured"


def test_production_still_rejects_wildcard_cors_for_every_service(monkeypatch) -> None:
    for env in (CORE, DOCUMENTS):
        assert "explicit origins" in _rejected(monkeypatch, env, CORS_ORIGINS="*")


def test_development_defaults_keep_local_single_process_behaviour(monkeypatch) -> None:
    for key in ("ENVIRONMENT", "FITAI_SERVICE", "SERVE_DOCUMENTS_ROUTES", "VECTOR_STORE_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.serve_documents_routes
    assert s.vector_store_backend == "chroma" and s.embedding_provider == "local"
    assert s.ingestion_mode == "inline"
