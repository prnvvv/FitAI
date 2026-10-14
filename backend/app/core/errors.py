"""Application error types and the shared error response shape.

Routers and services raise :class:`AppError` (or a subclass) and the handlers
installed in ``app.main`` convert them into a consistent JSON body::

    {"error": {"code": "RESOURCE_NOT_FOUND", "message": "...", "details": {}}}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected, client-facing application errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """Raised when a resource does not exist or is not visible to the caller."""

    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    message = "Resource not found."


class ConflictError(AppError):
    """Raised when an operation conflicts with the current resource state."""

    status_code = 409
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource."


class AuthenticationError(AppError):
    """Raised when authentication is missing or invalid."""

    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Authentication credentials were missing or invalid."


class PermissionDeniedError(AppError):
    """Raised when the caller is authenticated but not allowed to act."""

    status_code = 403
    code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action."


class BadRequestError(AppError):
    """Raised when a request is malformed (bad query parameters, reversed range)."""

    status_code = 400
    code = "BAD_REQUEST"
    message = "The request could not be understood."


class ValidationError(AppError):
    """Raised when request data fails domain validation."""

    status_code = 422
    code = "VALIDATION_ERROR"
    message = "The request data is invalid."


class PayloadTooLargeError(AppError):
    """Raised when an upload exceeds the configured size limit."""

    status_code = 413
    code = "PAYLOAD_TOO_LARGE"
    message = "The uploaded file is too large."


class UnsupportedMediaTypeError(AppError):
    """Raised when an uploaded file type is not supported."""

    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = "The uploaded file type is not supported."


class ServiceUnavailableError(AppError):
    """Raised when a required dependency is not configured or reachable."""

    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "A required service is not available."
