"""FitAI Documents API entry point (``uvicorn app.documents_main:app``).

Serves only ``/api/v1/documents/*`` plus the shared health endpoints and runs the
durable ingestion worker. It never imports the chat agent, LangGraph or the
speech-to-text stack, and with ``VECTOR_STORE_BACKEND=pgvector`` it never imports
ChromaDB either.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from app.api.routers import documents
from app.core.config import settings
from app.core.logging import get_logger
from app.core.service_app import build_lifespan, build_service_app
from app.db.startup_checks import check_migrations_at_startup

logger = get_logger(__name__)

_worker = None  # IngestionWorker, created at start-up so imports stay side-effect free


def _start_worker() -> None:
    global _worker
    if settings.ingestion_mode.strip().lower() != "jobs" or not settings.ingestion_worker_enabled:
        logger.info("ingestion_worker_disabled", mode=settings.ingestion_mode)
        return
    from app.services.ingestion_worker import IngestionWorker

    _worker = IngestionWorker()
    _worker.start()


def _stop_worker() -> None:
    if _worker is not None:
        _worker.stop()


def _startup_tasks() -> tuple[Callable[[], None], ...]:
    return (check_migrations_at_startup, _start_worker)


def create_app() -> FastAPI:
    return build_service_app(
        service="documents",
        title=f"{settings.app_name} Documents",
        routers=(documents.router,),
        lifespan=build_lifespan(_startup_tasks, on_shutdown=_stop_worker),
    )


app = create_app()
