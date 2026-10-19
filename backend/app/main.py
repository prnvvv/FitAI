"""FastAPI application entry point.

Router registration for the existing Person 1 routers happens here. Person 2's
chat router is intentionally not imported yet because it is still being
developed; it should be registered in the marked section below.
"""

from __future__ import annotations

import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.api.routers import (
    activity,
    auth,
    chat,
    compat,
    conversations,
    documents,
    exercises,
    location,
    memory,
    plan,
    profile,
    progress,
    workouts,
)
import logging

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.stt import router as stt_router

# Quiet HuggingFace Hub "404 additional_chat_templates" probes — they're normal fallbacks
logging.getLogger("huggingface_hub.file_download").setLevel(logging.WARNING)
logging.getLogger("transformers.modeling_utils").setLevel(logging.WARNING)

logger = get_logger(__name__)

ROUTERS = (
    auth.router,
    chat.router,
    conversations.router,
    profile.router,
    memory.router,
    documents.router,
    workouts.router,
    progress.router,
    activity.router,
    location.router,
    plan.router,
    exercises.router,
    stt_router,
)


def _check_migrations_at_startup() -> None:
    """Fail loudly if the database is behind the latest migration.

    This prevents cryptic 500s from missing tables/columns and tells operators
    exactly what to do.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        try:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            # SQLite test databases created from metadata have no alembic_version table.
            return

    if current != head_revision:
        raise RuntimeError(
            f"Database migration mismatch: current={current}, head={head_revision}. "
            "Run: alembic upgrade head"
        )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_error_handlers(app)

    app.add_event_handler("startup", _check_migrations_at_startup)

    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_v1_prefix)

    # Unprefixed compatibility routes (discovery probe), like /health.
    app.include_router(compat.router)

    _register_health_endpoints(app)
    _register_startup_tasks(app)

    return app


def _register_startup_tasks(app: FastAPI) -> None:
    @app.on_event("startup")
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

    @app.on_event("startup")
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

    @app.on_event("startup")
    def _warm_stt_model() -> None:
        """Start loading the Granite STT model in the background if eager load is on.

        Loading ~900 MB of weights can take several seconds; doing it lazily on the
        first request would make the first dictation feel broken. A background
        thread keeps startup fast and never blocks health checks.
        """
        from app.stt.speech_service import get_service

        service = get_service()
        if not service.eager_load:
            logger.info("stt_warmup_skipped", reason="STT_EAGER_LOAD is disabled")
            return
        if service.status.state != "idle":
            logger.info("stt_warmup_skipped", reason=f"status is {service.status.state}")
            return

        def _warm() -> None:
            try:
                service.warmup()
                logger.info(
                    "stt_warmup_complete",
                    state=service.status.state,
                    device=service.status.device,
                    load_seconds=service.status.load_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - warmup must not crash startup
                logger.error("stt_warmup_failed", error=str(exc))

        logger.info("stt_warmup_started", model_id=service.model_id, device_request=service.device_request)
        threading.Thread(target=_warm, name="stt-warmup", daemon=True).start()


def _register_error_handlers(app: FastAPI) -> None:
    def _request_id(request: Request) -> str:
        """Return the caller's request id, or mint one so every error is traceable."""
        existing = request.headers.get("X-Request-ID")
        if existing:
            return existing
        return uuid.uuid4().hex[:16]

    def _error_body(code: str, message: str, details: dict[str, object], request_id: str) -> dict[str, object]:
        return {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        }

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = _request_id(request)
        if exc.status_code >= 500:
            logger.error(
                "application_error",
                exc_info=True,
                request_id=request_id,
                path=request.url.path,
                code=exc.code,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, jsonable_encoder(exc.details), request_id),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id(request)
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "VALIDATION_ERROR",
                "The request data is invalid.",
                {"errors": jsonable_encoder(exc.errors())},
                request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        logger.error(
            "unhandled_exception",
            exc_info=True,
            request_id=request_id,
            path=request.url.path,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=_error_body(
                "INTERNAL_ERROR",
                "An unexpected error occurred.",
                {},
                request_id,
            ),
            headers={"X-Request-ID": request_id},
        )


def _register_health_endpoints(app: FastAPI) -> None:
    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe. Does not imply downstream dependencies are healthy."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def readiness(db: DbSession) -> JSONResponse:
        """Readiness probe that checks the database connection."""
        try:
            _ping(db)
        except Exception as exc:  # noqa: BLE001 - report dependency failure honestly
            logger.warning("readiness_database_unavailable", error=str(exc))
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "checks": {"database": "unavailable"},
                },
            )
        return JSONResponse(status_code=200, content={"status": "ok", "checks": {"database": "ok"}})

    @app.get("/health/guardrails", tags=["health"])
    def guardrails_health() -> dict[str, object]:
        """Guardrails status for observability."""
        from app.core.config import settings

        return {
            "enabled": settings.guardrails_enabled,
            "mode": settings.guardrails_mode,
            "policy_version": "1.0",
            "classifier_model_configured": bool(settings.guard_model or settings.groq_model),
            "canary_configured": bool(settings.guard_canary),
        }


def _ping(db: Session) -> None:
    db.execute(text("SELECT 1"))


app = create_app()
