"""Real worker thread: lifecycle, crash survival and event-loop isolation."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ingestion_job import IngestionJob
from app.services.ingestion_jobs import enqueue
from app.services.ingestion_worker import IngestionWorker
from tests.pdf_factory import make_pdf
from tests.unit.deploy.test_ingestion_jobs import PAGES, FakeStore, env  # noqa: F401


def _wait(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _status(db, job_id) -> str:
    db.expire_all()
    return db.get(IngestionJob, job_id).status


def _threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "ingestion-worker" and t.is_alive()]


def test_start_is_idempotent_and_stop_joins_the_thread(env) -> None:  # noqa: F811
    _, _, make, _ = env
    worker = IngestionWorker(make(), poll_seconds=0.01)
    worker.start()
    worker.start()
    assert len(_threads()) == 1
    worker.stop()
    assert _threads() == []
    worker.start()  # restartable after a clean stop
    assert len(_threads()) == 1
    worker.stop()
    assert _threads() == []


def test_thread_drains_a_queued_job_to_indexed(env) -> None:  # noqa: F811
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    store = FakeStore()
    worker = IngestionWorker(make(store), poll_seconds=0.01)
    worker.start()
    try:
        assert _wait(lambda: _status(db, job.id) == "succeeded")
    finally:
        worker.stop()
    db.expire_all()
    assert db.get(Document, doc.id).status == DocumentStatus.INDEXED


def test_a_failing_cycle_does_not_kill_the_worker(env, monkeypatch) -> None:  # noqa: F811
    _, _, make, _ = env
    worker = IngestionWorker(make(), poll_seconds=0.01)
    calls = {"n": 0}

    def boom() -> bool:
        calls["n"] += 1
        raise RuntimeError("database blip")

    monkeypatch.setattr(worker, "run_once", boom)
    monkeypatch.setattr(worker, "sweep_orphans", lambda: 0)
    worker.start()
    try:
        assert _wait(lambda: calls["n"] >= 3)  # kept polling after each failure
        assert len(_threads()) == 1
    finally:
        worker.stop()


def test_stop_does_not_hang_on_an_in_flight_job_and_the_job_stays_resumable(env) -> None:  # noqa: F811
    """SIGTERM mid-ingestion: stop() returns promptly; the lease lets the next boot resume."""
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    release = threading.Event()
    entered = threading.Event()

    class SlowStore(FakeStore):
        def add_chunks(self, collection, chunks, owner_id=None) -> int:
            entered.set()
            release.wait(5)
            return super().add_chunks(collection, chunks, owner_id)

    worker = IngestionWorker(make(SlowStore()), poll_seconds=0.01)
    worker.start()
    assert entered.wait(5)
    started = time.monotonic()
    worker.stop(timeout=0.2)
    assert time.monotonic() - started < 2.0
    release.set()  # let the daemon thread finish so the test leaves nothing running
    assert _wait(lambda: not _threads())
    db.expire_all()
    assert db.get(IngestionJob, job.id).status in {"running", "succeeded", "queued"}


def test_event_loop_stays_responsive_while_a_job_ingests(env) -> None:  # noqa: F811
    """CPU- and wait-heavy ingestion runs in its thread; the asyncio loop is not starved."""
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    enqueue(db, doc)

    class BusyStore(FakeStore):
        def add_chunks(self, collection, chunks, owner_id=None) -> int:
            time.sleep(0.15)  # remote embedding round-trip
            end = time.monotonic() + 0.15
            while time.monotonic() < end:  # pure-Python CPU work holding the GIL
                sum(i * i for i in range(2000))
            return super().add_chunks(collection, chunks, owner_id)

    store = BusyStore()
    worker = IngestionWorker(make(store), poll_seconds=0.01)

    async def probe() -> float:
        worst = 0.0
        worker.start()
        try:
            while store.calls < 4:  # 7 pages / 2 per batch = 4 batches
                t0 = time.monotonic()
                await asyncio.sleep(0.01)
                worst = max(worst, time.monotonic() - t0 - 0.01)
            return worst
        finally:
            worker.stop()

    worst_lag = asyncio.run(asyncio.wait_for(probe(), 30))
    assert store.calls >= 4
    assert worst_lag < 0.2, f"event loop stalled {worst_lag:.3f}s during ingestion"
