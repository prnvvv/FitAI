"""Startup behaviour of the application lifespan.

Starlette 1.x removed ``add_event_handler``/``on_event``, so startup work runs in
a lifespan. These tests pin its ordering and that a failed migration check
still prevents the application from starting.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main as main_module


def _tasks(record: list[str], *, fail_first: bool = False) -> tuple[Callable[[], None], ...]:
    def migrations() -> None:
        record.append("migrations")
        if fail_first:
            raise RuntimeError("schema is behind the latest migration")

    def reconcile() -> None:
        record.append("reconcile")

    def guardrails() -> None:
        record.append("guardrails")

    def warmup() -> None:
        record.append("warmup")

    return (migrations, reconcile, guardrails, warmup)


def test_startup_tasks_run_in_order_when_the_app_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list[str] = []
    monkeypatch.setattr(main_module, "_startup_tasks", lambda: _tasks(record))

    app = main_module.create_app()
    assert record == []  # nothing runs at construction time

    with TestClient(app) as client:
        assert record == ["migrations", "reconcile", "guardrails", "warmup"]
        assert client.get("/health").status_code == 200


def test_failed_migration_check_prevents_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list[str] = []
    monkeypatch.setattr(main_module, "_startup_tasks", lambda: _tasks(record, fail_first=True))

    app: FastAPI = main_module.create_app()

    with pytest.raises(RuntimeError, match="behind the latest migration"), TestClient(app):
        pass  # pragma: no cover - startup must raise before the body runs

    assert record == ["migrations"]  # later tasks never ran
