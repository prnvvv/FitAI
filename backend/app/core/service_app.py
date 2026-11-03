"""Plumbing shared by the Core and Documents FastAPI applications.

Every deployable service gets the same CORS policy, structured error envelope,
request-id/timing log line and ``/health`` endpoints. Only the routers and the
start-up tasks differ, so the three entrypoints stay tiny and cannot drift apart.

Importing this module must stay cheap: it may not import any router, ML library
or document/audio dependency.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

StartupTask = Callable[[], None]


def _request_id(request: Request) -> str:
    """Return the caller's request id, or mint one so every error is traceable."""
    state_id = getattr(request.state, "request_id", None)
    if state_id:
        return str(state_id)
    existing = request.headers.get("X-Request-ID")
    return existing if existing else uuid.uuid4().hex[:16]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id and log one line per request: service, endpoint, duration.

    Only the path is logged (never the query string, headers or body), so tokens
    and uploaded content cannot leak into logs.
    """

    def __init__(self, app: FastAPI, service: str) -> None:
        super().__init__(app)
        self._service = service

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id, service=self._service)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            if request.url.path != "/health":
                logger.info(
                    "request_completed",
                    method=request.method,
                    endpoint=request.url.path,
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            structlog.contextvars.clear_contextvars()


def _error_body(
    code: str, message: str, details: dict[str, object], request_id: str
) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    """Install the shared JSON error envelope for domain, validation and unexpected errors."""

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
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred.", {}, request_id),
            headers={"X-Request-ID": request_id},
        )


def _ping(db: Session) -> None:
    db.execute(text("SELECT 1"))


def register_health_endpoints(app: FastAPI, service: str) -> None:
    """``/health`` (liveness) and ``/health/ready`` (database), neither touching models."""

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe. Does not imply downstream dependencies are healthy."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def readiness(db: DbSession) -> JSONResponse:
        """Readiness probe that checks the database connection (reported separately)."""
        try:
            _ping(db)
        except Exception as exc:  # noqa: BLE001 - report dependency failure honestly
            logger.warning("readiness_database_unavailable", error=type(exc).__name__)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "service": service,
                    "checks": {"database": "unavailable"},
                },
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "service": service, "checks": {"database": "ok"}},
        )


def build_lifespan(
    tasks: Callable[[], Sequence[StartupTask]],
    on_shutdown: Callable[[], None] | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return a lifespan that runs ``tasks()`` in order at start and ``on_shutdown`` at exit.

    A failing task aborts start-up (the first one is the schema check); later
    tasks are written so they never need to.
    """
    startup_tasks = tasks()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        for task in startup_tasks:
            task()
        try:
            yield
        finally:
            if on_shutdown is not None:
                on_shutdown()

    return lifespan


def build_service_app(
    *,
    service: str,
    title: str,
    routers: Iterable[APIRouter],
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]],
    extra_routers: Iterable[APIRouter] = (),
) -> FastAPI:
    """Create a FastAPI app with the shared middleware, error handling and health checks.

    ``routers`` are mounted under ``API_V1_PREFIX``; ``extra_routers`` are mounted
    unprefixed (compatibility probes).
    """
    configure_logging()
    app = FastAPI(
        title=title,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware, service=service)
    register_error_handlers(app)
    for router in routers:
        app.include_router(router, prefix=settings.api_v1_prefix)
    for router in extra_routers:
        app.include_router(router)
    register_health_endpoints(app, service)
    return app
