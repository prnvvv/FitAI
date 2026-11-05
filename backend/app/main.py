"""FitAI Core API entry point.

Core serves auth, chat (LangGraph + Groq), conversations, profile, workouts,
progress, memory, activity, plan, exercises and location. The document and
document route group is optional (``SERVE_DOCUMENTS_ROUTES``, true for a
single-process local run): in production it is served by the dedicated Documents
service, and Core then never imports its modules or dependencies. Dictation runs
in the browser (Web Speech API), so there is no speech-to-text backend.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, FastAPI

from app.api.routers import (
    activity,
    auth,
    chat,
    compat,
    conversations,
    exercises,
    location,
    memory,
    plan,
    profile,
    progress,
    workouts,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.service_app import build_lifespan, build_service_app
from app.core.spa import configure_frontend
from app.db.startup_checks import check_migrations_at_startup as _check_migrations_at_startup

# Quiet HuggingFace Hub "404 additional_chat_templates" probes — they're normal fallbacks
logging.getLogger("huggingface_hub.file_download").setLevel(logging.WARNING)
logging.getLogger("transformers.modeling_utils").setLevel(logging.WARNING)

logger = get_logger(__name__)


def core_routers() -> tuple[APIRouter, ...]:
    """Routers Core serves; the document group is imported only when enabled."""
    routers: list[APIRouter] = [
        auth.router,
        chat.router,
        conversations.router,
        profile.router,
        memory.router,
        workouts.router,
        progress.router,
        activity.router,
        location.router,
        plan.router,
        exercises.router,
    ]
    if settings.serve_documents_routes:
        from app.api.routers import documents

        routers.insert(5, documents.router)
    return tuple(routers)


def create_app() -> FastAPI:
    """Build and configure the Core FastAPI application."""
    app = build_service_app(
        service="core",
        title=settings.app_name,
        routers=core_routers(),
        # Unprefixed compatibility routes (discovery probe), like /health.
        extra_routers=(compat.router,),
        lifespan=_build_lifespan(),
    )
    _register_guardrails_health(app)
    # Last: the SPA catch-all must not shadow any API, health or docs route.
    configure_frontend(app)
    return app


def _build_lifespan() -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return the application lifespan that runs the startup tasks in order.

    Starlette 1.x removed ``add_event_handler``/``on_event``, so startup work is
    expressed as a lifespan. The migration check runs first and, as before, a
    failure there aborts startup. The tasks after it never block startup.
    """
    return build_lifespan(_startup_tasks, on_shutdown=_stop_ingestion_worker)


def _stop_ingestion_worker() -> None:
    if settings.serve_documents_routes:
        from app.services.ingestion_runtime import stop_worker

        stop_worker()


def _startup_tasks() -> tuple[Callable[[], None], ...]:
    def _reconcile_stuck_documents() -> None:
        """Mark documents that were left pending/processing across restarts as failed."""
        from app.db.session import SessionLocal
        from app.services.document_service import reconcile_stuck_documents

        db = SessionLocal()
        try:
            ids = reconcile_stuck_documents(db)
            if ids:
                logger.info("reconciled_stuck_documents", count=len(ids))
        except Exception:  # noqa: BLE001 - a failed sweep must not block startup
            logger.warning("reconcile_stuck_documents_failed", exc_info=True)
        finally:
            db.close()

    def _log_guardrails_mode() -> None:
        """Warn loudly if guardrails are in monitor mode."""
        from app.core.config import settings

        if settings.guardrails_enabled and settings.guardrails_mode == "monitor":
            logger.warning(
                "GUARDRAILS_MODE=monitor: guardrails will LOG violations but NOT enforce them. "
                "Set GUARDRAILS_MODE=enforce for production."
            )
        elif not settings.guardrails_enabled:
            logger.warning("GUARDRAILS_ENABLED=false: all guardrails are DISABLED.")

    tasks: list[Callable[[], None]] = [_check_migrations_at_startup]
    if settings.serve_documents_routes and settings.ingestion_mode.strip().lower() != "jobs":
        tasks.append(_reconcile_stuck_documents)
    if settings.serve_documents_routes and settings.ingestion_mode.strip().lower() == "jobs":
        # One-service deployment: Core owns the durable ingestion queue too.
        from app.services.ingestion_runtime import start_worker

        tasks.append(start_worker)
    tasks.append(_log_guardrails_mode)
    return tuple(tasks)


def _register_guardrails_health(app: FastAPI) -> None:
    @app.get("/health/guardrails", tags=["health"])
    def guardrails_health() -> dict[str, object]:
        """Guardrails status for observability.

        Unauthenticated, so production exposes only whether guardrails are on;
        mode, model and canary details stay out of public responses.
        """
        if settings.is_production:
            return {"enabled": settings.guardrails_enabled}
        return {
            "enabled": settings.guardrails_enabled,
            "mode": settings.guardrails_mode,
            "policy_version": "1.0",
            "classifier_model_configured": bool(settings.guard_model or settings.groq_model),
            "canary_configured": bool(settings.guard_canary),
        }


app = create_app()
