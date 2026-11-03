"""FitAI Documents API entry point (``uvicorn app.documents_main:app``).

Serves only ``/api/v1/documents/*`` plus the shared health endpoints and runs the
durable ingestion worker. It never imports the chat agent or LangGraph, and with
``VECTOR_STORE_BACKEND=pgvector`` it never imports ChromaDB either.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from app.api.routers import documents
from app.core.config import settings
from app.core.service_app import build_lifespan, build_service_app
from app.db.startup_checks import check_migrations_at_startup
from app.services.ingestion_runtime import start_worker, stop_worker


def _startup_tasks() -> tuple[Callable[[], None], ...]:
    return (check_migrations_at_startup, start_worker)


def create_app() -> FastAPI:
    return build_service_app(
        service="documents",
        title=f"{settings.app_name} Documents",
        routers=(documents.router,),
        lifespan=build_lifespan(_startup_tasks, on_shutdown=stop_worker),
    )


app = create_app()
