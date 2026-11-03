"""Static guards for render.yaml, the Dockerfiles and the per-service requirements."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[3]
ROOT = BACKEND.parent
SERVICES = ("core", "documents")
MODULES = {"core": "app.main:app", "documents": "app.documents_main:app"}

BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
BY_NAME = {s["name"]: s for s in BLUEPRINT["services"]}


def _setting_env_names() -> set[str]:
    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        alias = field.validation_alias
        choices = getattr(alias, "choices", None) or ([alias] if alias else [])
        names.update(str(c).upper() for c in choices)
    return names


@pytest.mark.parametrize("svc", SERVICES)
def test_blueprint_service_is_docker_single_worker_with_health_check(svc) -> None:
    s = BY_NAME[f"fitai-{svc}"]
    assert s["runtime"] == "docker"
    assert s["dockerfilePath"] == f"./backend/Dockerfile.{svc}"
    assert s["dockerContext"] == "./backend"
    assert s["healthCheckPath"] == "/health"
    assert s["branch"] == "main"
    assert s["autoDeployTrigger"] == "off"  # nothing deploys unless the owner triggers it


@pytest.mark.parametrize("svc", SERVICES)
def test_blueprint_env_vars_are_real_settings_and_hold_no_secrets(svc) -> None:
    known = _setting_env_names() | {"FITAI_SERVICE"}
    for var in BY_NAME[f"fitai-{svc}"]["envVars"]:
        assert var["key"] in known, f"{var['key']} is not a Settings field"
        is_secret = re.search(r"KEY|SECRET|PASSWORD|TOKEN|DATABASE_URL", var["key"])
        if is_secret:
            assert var.get("sync") is False and "value" not in var, var["key"]


@pytest.mark.parametrize("svc", SERVICES)
def test_blueprint_production_settings_validate_for_each_service(svc, monkeypatch) -> None:
    """The non-secret values plus plausible secrets must pass production validation."""
    env = {v["key"]: v.get("value", "x") for v in BY_NAME[f"fitai-{svc}"]["envVars"]}
    env.update(
        DATABASE_URL="postgresql://u:p@h:5432/d",
        CORS_ORIGINS="https://app.example.com",
        SUPABASE_URL="https://abc.supabase.co",
        EMBEDDING_API_URL="https://e.example.com",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Settings(_env_file=None).is_production


def test_core_blueprint_disables_document_routes() -> None:
    env = {v["key"]: v.get("value") for v in BY_NAME["fitai-core"]["envVars"]}
    assert env["SERVE_DOCUMENTS_ROUTES"] == "false"


@pytest.mark.parametrize("svc", SERVICES)
def test_dockerfile_is_minimal_non_root_and_single_worker(svc) -> None:
    text = (BACKEND / f"Dockerfile.{svc}").read_text(encoding="utf-8")
    assert f"requirements-{svc}.txt" in text
    assert re.search(r"^USER app$", text, re.M)
    assert "HEALTHCHECK" in text
    assert f"uvicorn {MODULES[svc]}" in text and "--workers 1" in text
    assert "${PORT" in text  # Render supplies the port
    assert "torch" not in text and "apt-get" not in text and "ENV .*KEY" not in text
    assert "alembic upgrade" not in text  # migrations are a deliberate manual step
    assert not re.search(r"--workers\s+(?!1\b)\d+", text)


def test_requirements_are_minimal_per_service() -> None:
    def names(svc: str) -> set[str]:
        lines = (BACKEND / f"requirements-{svc}.txt").read_text(encoding="utf-8").splitlines()
        return {
            re.split(r"[<>=\[ ]", ln.strip(), maxsplit=1)[0].lower()
            for ln in lines
            if ln.strip() and not ln.startswith("#")
        }

    forbidden = {"torch", "torchaudio", "transformers", "accelerate", "chromadb", "onnxruntime"}
    for svc in SERVICES:
        assert not names(svc) & forbidden, svc
    assert {"pypdf", "python-docx"} <= names("documents")
    assert not {"pypdf", "python-docx"} & names("core")
    assert {"langgraph", "groq"} <= names("core")
    assert not {"langgraph", "groq"} & names("documents")
    assert "numpy" not in names("core") | names("documents")


def test_dockerignore_blocks_secrets_and_local_data() -> None:
    text = (BACKEND / ".dockerignore").read_text(encoding="utf-8")
    assert text.splitlines()[2] == "*"  # allow-list
    assert "**/.env" in text and "**/*.db" in text
    for local in ("chroma_data", "uploads", "data"):
        assert f"!{local}" not in text


def test_gitignore_covers_secrets_and_local_state() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".env",
        ".venv/",
        "__pycache__/",
        "*.py[cod]",
        "chroma_data/",
        "*.db",
        "uploads/",
    ):
        assert pattern in text
