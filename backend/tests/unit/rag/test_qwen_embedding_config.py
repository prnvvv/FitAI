"""Qwen3-Embedding-0.6B via the HF router: config, model naming, and the 1024-d migration guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.rag import embeddings
from app.rag.embeddings import RemoteEmbedder, embedding_model_name

MIGRATION = (
    Path(__file__).resolve().parents[3] / "migrations/versions/0006_vector_dimension_1024.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("m0006", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_remote_model_name_is_recorded_with_vectors(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "remote")
    monkeypatch.setattr(settings, "embedding_remote_model", "Qwen/Qwen3-Embedding-0.6B")
    assert embedding_model_name() == "Qwen/Qwen3-Embedding-0.6B"
    monkeypatch.setattr(settings, "embedding_provider", "local")
    assert embedding_model_name() == embeddings.EMBEDDING_NAME


def test_openai_format_request_matches_the_hf_deepinfra_route() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        import json

        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(
            200, json={"data": [{"embedding": [0.1] * 1024} for _ in body["input"]]}
        )

    emb = RemoteEmbedder(
        "https://router.huggingface.co/deepinfra/v1/openai/embeddings",
        "hf_test",
        dimension=1024,
        model="Qwen/Qwen3-Embedding-0.6B",
        api_format="openai",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    out = emb.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 1024
    assert seen["body"] == {"input": ["a", "b"], "model": "Qwen/Qwen3-Embedding-0.6B"}
    assert seen["auth"] == "Bearer hf_test"


def test_a_384_dimension_vector_is_rejected_for_a_1024_index() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": [{"embedding": [0.1] * 384}]})
        )
    )
    emb = RemoteEmbedder(
        "https://x", "k", dimension=1024, model="m", api_format="openai", client=client
    )
    with pytest.raises(embeddings.EmbeddingError):
        emb.embed(["a"])


def test_openai_format_requires_a_model_in_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "remote")
    monkeypatch.setattr(settings, "embedding_api_url", "https://x")
    monkeypatch.setattr(settings, "embedding_api_key", "k")
    monkeypatch.setattr(settings, "embedding_api_format", "openai")
    monkeypatch.setattr(settings, "embedding_remote_model", None)
    assert any("EMBEDDING_REMOTE_MODEL" in p for p in settings._remote_embedding_problems())
    monkeypatch.setattr(settings, "embedding_remote_model", "Qwen/Qwen3-Embedding-0.6B")
    assert settings._remote_embedding_problems() == []


class _Bind:
    def __init__(self, rows: int, dialect: str = "postgresql") -> None:
        self.rows, self.dialect = rows, SimpleNamespace(name=dialect)

    def execute(self, _stmt):
        return SimpleNamespace(scalar_one=lambda: self.rows)


def _run(monkeypatch, mod, bind, fn) -> list[str]:
    ran: list[str] = []
    monkeypatch.setattr(
        mod, "op", SimpleNamespace(get_bind=lambda: bind, execute=lambda sql: ran.append(sql))
    )
    fn()
    return ran


def test_migration_resizes_an_empty_table_and_rebuilds_the_index(monkeypatch) -> None:
    mod = _migration()
    ran = _run(monkeypatch, mod, _Bind(0), mod.upgrade)
    assert any("TYPE vector(1024)" in s for s in ran)
    assert any("hnsw" in s for s in ran) and any(s.startswith("DROP INDEX") for s in ran)


def test_migration_refuses_when_vectors_exist_and_changes_nothing(monkeypatch) -> None:
    mod = _migration()
    ran: list[str] = []
    monkeypatch.setattr(
        mod, "op", SimpleNamespace(get_bind=lambda: _Bind(7), execute=lambda sql: ran.append(sql))
    )
    with pytest.raises(RuntimeError, match="refusing"):
        mod.upgrade()
    assert ran == []  # nothing dropped, altered or deleted


def test_migration_is_a_noop_off_postgres(monkeypatch) -> None:
    mod = _migration()
    assert _run(monkeypatch, mod, _Bind(0, "sqlite"), mod.upgrade) == []
