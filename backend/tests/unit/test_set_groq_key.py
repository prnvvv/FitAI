"""Tests for the Groq key rotation helper.

The helper must update every key variable in one pass, keep the rest of the file
intact, and never leak the value.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "set_groq_key.py"


def _module():
    spec = importlib.util.spec_from_file_location("set_groq_key", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["set_groq_key"] = module
    spec.loader.exec_module(module)
    return module


mod = _module()

_ENV = """ENVIRONMENT=development
# a comment
GROQ_API_KEY=old-key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_EXTRACTION_API_KEY=old-key
PROMPT_GUARD_MODEL=meta-llama/llama-prompt-guard-2-86m
"""


def test_all_key_variables_are_updated() -> None:
    out = mod.update_env(_ENV, "gsk_" + "x" * 40)
    assert out.count("gsk_" + "x" * 40) == 3
    for name in mod.KEY_VARIABLES:
        assert f"{name}=gsk_" + "x" * 40 in out


def test_non_key_settings_and_comments_survive() -> None:
    out = mod.update_env(_ENV, "gsk_" + "x" * 40)
    assert "ENVIRONMENT=development" in out
    assert "GROQ_MODEL=openai/gpt-oss-120b" in out
    assert "PROMPT_GUARD_MODEL=meta-llama/llama-prompt-guard-2-86m" in out
    assert "# a comment" in out
    assert "old-key" not in out


def test_missing_variables_are_appended() -> None:
    out = mod.update_env("ENVIRONMENT=development\n", "gsk_" + "y" * 40)
    for name in mod.KEY_VARIABLES:
        assert f"{name}=gsk_" + "y" * 40 in out
    assert "ENVIRONMENT=development" in out


def test_commented_out_lines_are_not_overwritten() -> None:
    env = "# GROQ_API_KEY=disabled\nENVIRONMENT=development\n"
    out = mod.update_env(env, "gsk_" + "z" * 40)
    assert "# GROQ_API_KEY=disabled" in out
    assert "\nGROQ_API_KEY=gsk_" + "z" * 40 in out


def test_key_shape_is_validated() -> None:
    assert mod.looks_like_groq_key("gsk_" + "a" * 48) is True
    assert mod.looks_like_groq_key("gsk-short") is False
    assert mod.looks_like_groq_key("hunter2 " + "a" * 40) is False


def test_cli_refuses_a_bad_key_without_writing(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(_ENV, encoding="utf-8")
    monkeypatch.setenv("GROQ_NEW_KEY", "not-a-key")
    assert mod.main(["--env-file", str(env_file)]) == 2
    assert env_file.read_text(encoding="utf-8") == _ENV  # untouched


def test_cli_updates_the_file_and_keeps_a_backup(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(_ENV, encoding="utf-8")
    new_key = "gsk_" + "q" * 48
    monkeypatch.setenv("GROQ_NEW_KEY", new_key)

    assert mod.main(["--env-file", str(env_file)]) == 0

    written = env_file.read_text(encoding="utf-8")
    assert written.count(new_key) == 3
    assert "old-key" not in written


def test_cli_reports_a_missing_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_NEW_KEY", "gsk_" + "q" * 48)
    assert mod.main(["--env-file", str(tmp_path / "absent")]) == 2


def test_module_docstring_warns_not_to_commit_keys() -> None:
    assert (
        "never printed" in (mod.__doc__ or "").lower()
        or "never echo" in (mod.__doc__ or "").lower()
    )


@pytest.mark.parametrize(
    "name", ["GROQ_API_KEY", "GROQ_EXTRACTION_API_KEY", "PROMPT_GUARD_API_KEY"]
)
def test_every_key_variable_is_covered(name: str) -> None:
    assert name in mod.KEY_VARIABLES
