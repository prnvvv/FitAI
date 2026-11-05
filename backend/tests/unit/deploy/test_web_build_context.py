"""Behavioural check of the Docker build context for Dockerfile.web.

Applies the ignore rules (Docker semantics: last matching pattern wins, a
pattern also covers everything beneath a matched directory) to the real
repository file list. Both ignore files are checked because which one a builder
honours depends on the builder: BuildKit prefers ``Dockerfile.web.dockerignore``,
others read the root ``.dockerignore``. Either way the build must see every file
it COPYs and must never see a local ``.env``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DOCKERFILE = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")


def _regex(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    pattern = pattern.rstrip("/")
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out)


def _included(path: str, ignore_file: Path) -> bool:
    rules = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            negated = line.startswith("!")
            rules.append((negated, _regex(line.lstrip("!"))))
    parts = path.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    excluded = False
    for negated, rx in rules:
        if any(rx.fullmatch(p) for p in prefixes):
            excluded = not negated
    return not excluded


def _repo_files() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    # Files that exist on developer machines but are never tracked.
    return tracked + [
        "frontend/.env",
        "frontend/.env.local",
        "frontend/.env.production",
        "backend/app/.env",
        "backend/.env",
        ".env",
        "frontend/node_modules/react/index.js",
        "frontend/dist/index.html",
        "backend/data.db",
    ]


IGNORE_FILES = [ROOT / "Dockerfile.web.dockerignore", ROOT / ".dockerignore"]
REQUIRED = [
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
    "frontend/vite.config.ts",
    "frontend/src/main.tsx",
    "backend/requirements-web.txt",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "backend/migrations/env.py",
    "backend/app/main.py",
]
FORBIDDEN = [
    "frontend/.env",
    "frontend/.env.local",
    "frontend/.env.production",
    "backend/app/.env",
    "backend/.env",
    ".env",
    "frontend/node_modules/react/index.js",
    "frontend/dist/index.html",
    "backend/data.db",
]


@pytest.mark.parametrize("ignore_file", IGNORE_FILES, ids=lambda p: p.name)
def test_every_file_the_build_needs_is_in_the_context(ignore_file: Path) -> None:
    files = set(_repo_files())
    for path in REQUIRED:
        assert path in files, f"{path} is not tracked"
        assert _included(path, ignore_file), f"{path} is missing from the build context"


@pytest.mark.parametrize("ignore_file", IGNORE_FILES, ids=lambda p: p.name)
def test_local_env_files_and_artifacts_never_enter_the_context(ignore_file: Path) -> None:
    for path in FORBIDDEN:
        assert not _included(path, ignore_file), f"{path} would be sent to the builder"


def test_every_copy_source_of_the_dockerfile_is_a_required_path() -> None:
    sources = []
    for line in DOCKERFILE.splitlines():
        m = re.match(r"COPY\s+(?!--from)(.+)\s+\S+$", line.strip())
        if m:
            sources += m.group(1).split()
    for src in sources:
        assert any(r == src.rstrip("/") or r.startswith(src) for r in REQUIRED), src


def test_only_public_vite_values_are_build_args_and_no_secret_enters_a_layer() -> None:
    args = re.findall(r"^ARG\s+(\w+)", DOCKERFILE, flags=re.M)
    assert sorted(args) == ["VITE_SUPABASE_ANON_KEY", "VITE_SUPABASE_URL"]
    # ENV lines in the frontend stage may only forward those two build args.
    frontend_stage = DOCKERFILE.split("AS builder")[0]
    env_keys = re.findall(r"^\s+(\w+)=\$", frontend_stage, flags=re.M)
    assert set(env_keys) <= set(args)
    code = "
".join(ln for ln in DOCKERFILE.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"SERVICE_ROLE|GROQ|DATABASE_URL|SECRET", code, flags=re.I)
