"""Shared API schema primitives: pagination and error bodies."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    """Standard pagination envelope."""

    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    """The inner object of the standard error body."""

    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: ErrorDetail
