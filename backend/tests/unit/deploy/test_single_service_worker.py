"""Core owns the durable ingestion worker when it also serves the document routes."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.main import _startup_tasks
from app.services import ingestion_runtime


def _names(tasks) -> list[str]:
    return [getattr(t, "__name__", repr(t)) for t in tasks]


def test_jobs_mode_with_document_routes_starts_the_worker(monkeypatch) -> None:
    monkeypatch.setattr(settings, "serve_documents_routes", True)
    monkeypatch.setattr(settings, "ingestion_mode", "jobs")
    assert "start_worker" in _names(_startup_tasks())


@pytest.mark.parametrize(("serve", "mode"), [(False, "jobs"), (True, "inline"), (False, "inline")])
def test_worker_not_started_otherwise(monkeypatch, serve: bool, mode: str) -> None:
    monkeypatch.setattr(settings, "serve_documents_routes", serve)
    monkeypatch.setattr(settings, "ingestion_mode", mode)
    assert "start_worker" not in _names(_startup_tasks())


def test_runtime_starts_once_and_stops(monkeypatch) -> None:
    started: list[str] = []

    class FakeWorker:
        def start(self) -> None:
            started.append("start")

        def stop(self) -> None:
            started.append("stop")

    monkeypatch.setattr(settings, "ingestion_mode", "jobs")
    monkeypatch.setattr(settings, "ingestion_worker_enabled", True)
    monkeypatch.setattr("app.services.ingestion_worker.IngestionWorker", FakeWorker)
    monkeypatch.setattr(ingestion_runtime, "_worker", None)
    ingestion_runtime.start_worker()
    ingestion_runtime.start_worker()  # idempotent
    ingestion_runtime.stop_worker()
    ingestion_runtime.stop_worker()
    assert started == ["start", "stop"]


def test_runtime_disabled_outside_jobs_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ingestion_mode", "inline")
    monkeypatch.setattr(ingestion_runtime, "_worker", None)
    ingestion_runtime.start_worker()
    assert ingestion_runtime._worker is None
