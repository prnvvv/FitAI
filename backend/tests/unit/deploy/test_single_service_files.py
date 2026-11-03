"""Static guards for the one-service deployment: render.yaml, Dockerfile.web, requirements."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[3]
ROOT = BACKEND.parent

BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
DOCKERFILE = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")


def _req_names(path: Path) -> set[str]:
    return {
        re.split(r"[<>=\[ ]", ln.strip(), maxsplit=1)[0].lower()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def _setting_env_names() -> set[str]:
    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        alias = field.validation_alias
        choices = getattr(alias, "choices", None) or ([alias] if alias else [])
        names.update(str(c).upper() for c in choices)
    return names


def _service() -> dict:
    assert len(BLUEPRINT["services"]) == 1
    return BLUEPRINT["services"][0]


def test_blueprint_is_one_docker_web_service_with_health_check() -> None:
    s = _service()
    assert s["type"] == "web" and s["runtime"] == "docker"
    assert s["dockerfilePath"] == "./Dockerfile.web"
    assert s["dockerContext"] == "."
    assert s["healthCheckPath"] == "/health"
    assert s["autoDeployTrigger"] == "off"


def test_blueprint_env_vars_are_real_settings_and_hold_no_secrets() -> None:
    known = _setting_env_names() | {"FITAI_SERVICE"}
    for var in _service()["envVars"]:
        key = var["key"]
        if key.startswith("VITE_"):  # public build args, not backend settings
            assert var.get("sync") is False
            assert "SERVICE_ROLE" not in key and "SECRET" not in key
            continue
        assert key in known, f"{key} is not a Settings field"
        if re.search(r"KEY|SECRET|PASSWORD|TOKEN|DATABASE_URL", key):
            assert var.get("sync") is False and "value" not in var, key


def test_blueprint_production_settings_validate(monkeypatch) -> None:
    env = {
        v["key"]: v.get("value", "x")
        for v in _service()["envVars"]
        if not v["key"].startswith("VITE_")
    }
    env.update(
        DATABASE_URL="postgresql://u:p@h:5432/d",
        CORS_ORIGINS="https://fitai-web.example.com",
        SUPABASE_URL="https://abc.supabase.co",
        EMBEDDING_API_URL="https://e.example.com",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    assert settings.is_production
    assert settings.serve_documents_routes and settings.ingestion_mode == "jobs"


def test_dockerfile_builds_frontend_and_runs_one_non_root_worker() -> None:
    assert "npm ci" in DOCKERFILE and "npm run build" in DOCKERFILE
    assert "COPY --from=frontend" in DOCKERFILE
    assert re.search(r"^USER app$", DOCKERFILE, re.M)
    assert "HEALTHCHECK" in DOCKERFILE and "${PORT" in DOCKERFILE
    assert "uvicorn app.main:app" in DOCKERFILE and "--host 0.0.0.0" in DOCKERFILE
    assert not re.search(r"--workers\s+(?!1\b)\d+", DOCKERFILE)
    assert "alembic upgrade" not in DOCKERFILE  # migrations stay a deliberate manual step
    assert "SERVICE_ROLE" not in DOCKERFILE
    assert "requirements-web.txt" in DOCKERFILE


def test_web_requirements_are_the_union_of_core_and_documents_without_ml() -> None:
    web = _req_names(BACKEND / "requirements-web.txt")
    core = _req_names(BACKEND / "requirements-core.txt")
    docs = _req_names(BACKEND / "requirements-documents.txt")
    assert (core | docs) <= web
    assert not web & {"torch", "transformers", "chromadb", "onnxruntime", "numpy", "pillow"}


def test_web_dockerignore_is_an_allow_list_that_blocks_secrets() -> None:
    text = (ROOT / "Dockerfile.web.dockerignore").read_text(encoding="utf-8")
    assert "\n*\n" in text
    assert "**/.env" in text and "**/*.db" in text
    assert "!backend/.env" not in text


@pytest.mark.parametrize("name", ["VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"])
def test_frontend_build_args_are_declared(name: str) -> None:
    assert f"ARG {name}" in DOCKERFILE
