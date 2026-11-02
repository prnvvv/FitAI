"""Persistent storage paths are anchored to ``backend/``, not the working directory."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR, Settings, resolve_storage_path
from app.rag.vector_store import _persist_path

REPO_ROOT = BACKEND_DIR.parent
_PROBE = (
    "import json;"
    "from app.core.config import settings;"
    "from app.rag.vector_store import _persist_path;"
    "print(json.dumps([settings.upload_dir,settings.chromadb_persist_dir,"
    "_persist_path(None),settings.database_url]))"
)


def test_relative_paths_anchor_to_backend_dir() -> None:
    assert resolve_storage_path("./uploads") == (BACKEND_DIR / "uploads").resolve()
    assert resolve_storage_path("chroma_data") == (BACKEND_DIR / "chroma_data").resolve()


def test_absolute_paths_are_used_as_given(tmp_path: Path) -> None:
    assert resolve_storage_path(tmp_path) == tmp_path


def test_settings_anchor_relative_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", "./custom_uploads")
    monkeypatch.setenv("CHROMADB_PERSIST_DIR", "custom_chroma")
    s = Settings()
    assert Path(s.upload_dir) == (BACKEND_DIR / "custom_uploads").resolve()
    assert Path(s.chromadb_persist_dir) == (BACKEND_DIR / "custom_chroma").resolve()


def test_settings_keep_absolute_env_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "u"))
    monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(tmp_path / "c"))
    s = Settings()
    assert Path(s.upload_dir) == tmp_path / "u"
    assert Path(s.chromadb_persist_dir) == tmp_path / "c"


def test_vector_store_fallback_uses_configured_dir() -> None:
    from app.core.config import settings

    assert Path(_persist_path(None)) == Path(settings.chromadb_persist_dir)
    assert Path(_persist_path("rel_dir")) == (BACKEND_DIR / "rel_dir").resolve()


def test_local_document_storage_uses_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.services import document_storage

    monkeypatch.setattr(document_storage.settings, "document_storage_backend", "local")
    monkeypatch.setattr(document_storage.settings, "upload_dir", str(tmp_path / "up"))
    storage = document_storage.get_document_storage()
    storage.save("u/doc.txt", b"hi", "text/plain")
    assert (tmp_path / "up" / "u" / "doc.txt").read_bytes() == b"hi"


def _probe(cwd: Path) -> list[str]:
    skip = {"UPLOAD_DIR", "CHROMADB_PERSIST_DIR", "CHROMA_PERSIST_DIR", "DATABASE_URL"}
    env = {k: v for k, v in os.environ.items() if k not in skip}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_paths_are_identical_from_any_working_directory(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    results = [_probe(BACKEND_DIR), _probe(REPO_ROOT), _probe(elsewhere)]
    assert results[0] == results[1] == results[2]
    upload, chroma, fallback, _db = results[0]
    assert Path(upload).is_absolute() and Path(chroma).is_absolute()
    assert fallback == chroma
    assert Path(upload).parent == BACKEND_DIR
    assert Path(chroma).parent == BACKEND_DIR
    # importing settings must not create storage directories in the cwd
    assert list(elsewhere.iterdir()) == []
