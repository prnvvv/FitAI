"""FastAPI application entry point.

Router registration for the existing Person 1 routers happens here. Person 2's
chat router is intentionally not imported yet because it is still being
developed; it should be registered in the marked section below.
"""

from __future__ import annotations

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
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger

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

    _register_health_endpoints(app)
    _register_startup_tasks(app)

    return app


def _register_startup_tasks(app: FastAPI) -> None:
    @app.on_event("startup")
    def _reconcile_stuck_documents() -> None:
        """Mark documents that were left pending/processing across restarts as failed."""
        from datetime import datetime, timedelta, timezone

        from app.db.session import SessionLocal
        from app.models.document import Document
        from app.models.enums import DocumentStatus

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        db = SessionLocal()
        try:
            stuck = (
                db.query(Document)
                .filter(
                    Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]),
                    Document.created_at < cutoff,
                )
                .all()
            )
            for doc in stuck:
                doc.status = DocumentStatus.FAILED
                doc.failed_at = datetime.now(timezone.utc)
                doc.error_message = "Processing timed out. Try again or delete this file."
            if stuck:
                db.commit()
                logger.info("reconciled_stuck_documents", count=len(stuck))
        except Exception as exc:  # noqa: BLE001
            logger.warning("reconcile_stuck_documents_failed", error=str(exc))
        finally:
            db.close()


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": jsonable_encoder(exc.details),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request data is invalid.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
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


def _ping(db: Session) -> None:
    db.execute(text("SELECT 1"))


app = create_app()
