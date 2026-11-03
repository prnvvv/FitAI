"""The three deployable services: isolation, routes, health and authentication."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[3]

HEAVY = [
    "torch",
    "torchaudio",
    "transformers",
    "chromadb",
    "onnxruntime",
    "av",
    "scipy",
    "soundfile",
    "pypdf",
    "docx",
    "rapidocr_onnxruntime",
    "cv2",
    "accelerate",
]

_PROBE = """
import json, sys
__import__(sys.argv[1])
print(json.dumps(sorted(m for m in sys.argv[2].split(",") if m in sys.modules)))
print(json.dumps(sorted(m for m in sys.modules if m.startswith("app."))))
"""


def _imports(module: str, env: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    import os

    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module, ",".join(HEAVY)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(BACKEND), **(env or {})},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    heavy, app_modules = (json.loads(line) for line in result.stdout.strip().splitlines()[-2:])
    return heavy, app_modules


def test_core_with_split_services_imports_no_heavy_or_peer_service_code() -> None:
    heavy, app_modules = _imports(
        "app.main", {"SERVE_DOCUMENTS_ROUTES": "false", "SERVE_STT_ROUTES": "false"}
    )
    assert heavy == []
    assert not [m for m in app_modules if m.startswith(("app.stt", "app.rag.page_source"))]
    assert "app.api.routers.documents" not in app_modules
    assert "app.services.ingestion_jobs" not in app_modules


def test_core_default_does_not_load_chroma_or_ml_libraries_at_startup() -> None:
    """Even the single-process dev default must not pay for chromadb/torch on import."""
    heavy, _ = _imports("app.main")
    assert heavy == []


@pytest.mark.parametrize("module", ["app.stt_main", "app.documents_main"])
def test_peer_services_import_no_heavy_dependencies(module: str) -> None:
    heavy, app_modules = _imports(module)
    assert heavy == []
    # Neither peer service may pull in the chat agent or the other service's code.
    assert not [m for m in app_modules if m.startswith(("app.agent", "app.services.chat_service"))]


def test_documents_service_does_not_import_stt_and_stt_does_not_import_documents() -> None:
    _, docs_modules = _imports("app.documents_main")
    _, stt_modules = _imports("app.stt_main")
    assert not [m for m in docs_modules if m.startswith("app.stt")]
    assert "app.api.routers.documents" not in stt_modules
    assert not [
        m
        for m in stt_modules
        if m.startswith(("app.rag.vector_store", "app.rag.pipeline", "app.rag.embeddings"))
    ]


def _paths(app) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_stt_app_registers_only_stt_routes_and_health() -> None:
    from app.stt_main import app

    paths = _paths(app)
    assert "/api/v1/stt/transcribe" in paths and "/health" in paths
    assert not [p for p in paths if p.startswith(("/api/v1/chat", "/api/v1/documents"))]


def test_documents_app_registers_only_document_routes_and_health() -> None:
    from app.documents_main import app

    paths = _paths(app)
    assert "/api/v1/documents" in paths and "/health" in paths
    assert not [p for p in paths if p.startswith(("/api/v1/chat", "/api/v1/stt"))]


def test_core_registers_documents_and_stt_only_when_enabled(monkeypatch) -> None:
    from app.core.config import settings
    from app.main import core_routers

    def prefixes() -> set[str]:
        return {r.prefix for r in core_routers()}

    monkeypatch.setattr(settings, "serve_documents_routes", False)
    monkeypatch.setattr(settings, "serve_stt_routes", False)
    split = prefixes()
    assert "/documents" not in split and "/stt" not in split and "/chat" in split

    monkeypatch.setattr(settings, "serve_documents_routes", True)
    monkeypatch.setattr(settings, "serve_stt_routes", True)
    assert {"/documents", "/stt", "/chat"} <= prefixes()


@pytest.mark.parametrize("module", ["app.main", "app.stt_main", "app.documents_main"])
def test_every_service_exposes_a_cheap_health_endpoint(module: str) -> None:
    app = __import__(module, fromlist=["app"]).app
    response = TestClient(app).get("/health")  # no `with`: lifespan (DB check) not run
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    ("module", "method", "path"),
    [
        ("app.stt_main", "post", "/api/v1/stt/transcribe"),
        ("app.stt_main", "get", "/api/v1/stt/status"),
        ("app.documents_main", "get", "/api/v1/documents"),
        ("app.documents_main", "post", "/api/v1/documents"),
        ("app.documents_main", "delete", "/api/v1/documents/00000000-0000-0000-0000-000000000000"),
        (
            "app.documents_main",
            "post",
            "/api/v1/documents/00000000-0000-0000-0000-000000000000/retry",
        ),
    ],
)
def test_split_service_endpoints_require_authentication(module, method, path) -> None:
    app = __import__(module, fromlist=["app"]).app
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 401


def test_readiness_reports_database_separately(monkeypatch) -> None:
    from app.api.deps import get_current_auth_user  # noqa: F401 - keep import order stable
    from app.db.session import get_db
    from app.stt_main import app

    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("db down")

        def close(self) -> None:
            pass

    app.dependency_overrides[get_db] = lambda: Broken()
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}
    assert TestClient(app).get("/health").status_code == 200  # liveness unaffected
