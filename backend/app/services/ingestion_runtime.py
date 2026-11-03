"""Process-level lifecycle of the durable ingestion worker.

Shared by the Documents service and by a single-process deployment (Core serving
the document routes), so both start and stop the same worker the same way.
Importing this module stays cheap: the worker is imported only when started.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.ingestion_worker import IngestionWorker

logger = get_logger(__name__)

_worker: IngestionWorker | None = None


def worker_enabled() -> bool:
    """True when documents are ingested by the checkpointed job worker."""
    return settings.ingestion_mode.strip().lower() == "jobs" and settings.ingestion_worker_enabled


def start_worker() -> None:
    """Start the ingestion worker once, if the configuration asks for it."""
    global _worker
    if not worker_enabled():
        logger.info("ingestion_worker_disabled", mode=settings.ingestion_mode)
        return
    if _worker is not None:
        return
    from app.services.ingestion_worker import IngestionWorker

    _worker = IngestionWorker()
    _worker.start()


def stop_worker() -> None:
    """Stop the worker if it is running."""
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
