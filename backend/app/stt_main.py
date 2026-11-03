"""FitAI STT API entry point (``uvicorn app.stt_main:app``).

Serves only ``/api/v1/stt/*`` plus the shared health endpoints. It never imports
the chat agent, RAG, vector store or document-processing code. With
``STT_PROVIDER=remote`` (required in production) it loads no model at all.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from app.core.config import settings
from app.core.service_app import build_lifespan, build_service_app
from app.db.startup_checks import check_migrations_at_startup
from app.stt import router as stt_router


def _startup_tasks() -> tuple[Callable[[], None], ...]:
    tasks: list[Callable[[], None]] = [check_migrations_at_startup]
    if settings.stt_provider.strip().lower() == "local":
        from app.stt.startup import warm_stt_model

        tasks.append(warm_stt_model)
    return tuple(tasks)


def create_app() -> FastAPI:
    return build_service_app(
        service="stt",
        title=f"{settings.app_name} STT",
        routers=(stt_router,),
        lifespan=build_lifespan(_startup_tasks),
    )


app = create_app()
