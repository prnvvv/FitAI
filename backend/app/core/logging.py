"""Structured logging configuration.

Logs are emitted as structured events. Secrets and access tokens must never be
passed to the logger; call sites are responsible for redacting sensitive values.
"""

from __future__ import annotations

import contextlib
import logging
import sys

import structlog

from app.core.config import settings

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "jwt",
        "service_role_key",
        "database_url",
    }
)


def _redact_sensitive_fields(
    _logger: object, _method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    """Replace values of well-known sensitive keys with a placeholder."""
    for key in list(event_dict):
        if key.lower() in SENSITIVE_FIELD_NAMES:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging() -> None:
    """Configure structlog and the standard library root logger."""
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive_fields,  # type: ignore[list-item]
    ]

    renderer: structlog.typing.Processor
    if settings.is_production:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
