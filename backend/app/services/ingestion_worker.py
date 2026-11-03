"""Background loop that drains the durable ingestion-job queue.

A single daemon thread claims one job at a time (bounded memory) and sleeps when
idle. It holds no state of its own: everything needed to resume lives in the
database, so killing the process at any point loses nothing.
"""

from __future__ import annotations

import threading
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ingestion_jobs import JobDeps, claim_next, enqueue_orphans, process_job

logger = get_logger(__name__)

_ORPHAN_SWEEP_SECONDS = 60.0


def build_default_deps() -> JobDeps:
    """Production collaborators: configured storage and vector backend."""
    from app.db.session import SessionLocal
    from app.rag.store_factory import build_vector_store
    from app.services.document_storage import get_document_storage

    return JobDeps(
        session_factory=SessionLocal,
        storage=get_document_storage(),
        store=build_vector_store(),
        pages_per_batch=max(1, settings.ingestion_pages_per_batch),
    )


class IngestionWorker:
    """Polls for runnable jobs and processes them one at a time."""

    def __init__(self, deps: JobDeps | None = None, poll_seconds: float | None = None) -> None:
        self._deps = deps
        self._poll = poll_seconds if poll_seconds is not None else settings.ingestion_poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _get_deps(self) -> JobDeps:
        if self._deps is None:
            self._deps = build_default_deps()
        return self._deps

    def run_once(self) -> bool:
        """Claim and process a single job. Returns True if one was processed."""
        deps = self._get_deps()
        db = deps.session_factory()
        try:
            job_id = claim_next(db)
        finally:
            db.close()
        if job_id is None:
            return False
        status = process_job(deps, job_id)
        logger.info("ingestion_job_finished", job_id=str(job_id), status=status)
        return True

    def sweep_orphans(self) -> int:
        """Create jobs for pending documents that have none; returns the count."""
        db = self._get_deps().session_factory()
        try:
            created = enqueue_orphans(db)
        finally:
            db.close()
        if created:
            logger.info("ingestion_orphans_enqueued", count=created)
        return created

    def _loop(self) -> None:
        last_sweep = float("-inf")
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_sweep >= _ORPHAN_SWEEP_SECONDS:
                    self.sweep_orphans()
                    last_sweep = time.monotonic()
                if self.run_once():
                    continue  # drain the queue without sleeping
            except Exception:  # noqa: BLE001 - the loop must survive a bad cycle
                logger.error("ingestion_worker_cycle_failed", exc_info=True)
            self._stop.wait(self._poll)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ingestion-worker", daemon=True)
        self._thread.start()
        logger.info("ingestion_worker_started", poll_seconds=self._poll)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
