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
    auth,
    conversations,
    documents,
    memory,
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
    conversations.router,
    profile.router,
    memory.router,
    documents.router,
    workouts.router,
    progress.router,
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

    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_v1_prefix)

    # Person 2: register the chat router here once
    # ``app.api.routers.chat`` and ``app.services.chat_service`` are implemented.

    _register_health_endpoints(app)

    return app


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
