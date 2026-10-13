"""Reusable FastAPI dependencies: database session, authentication, pagination."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.core.security import AuthUser, get_token_verifier
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PaginationParams
from app.services.auth_service import AuthService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_auth_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> AuthUser:
    """Validate the bearer token and return the verified identity.

    The user id is derived exclusively from verified token claims; no value from
    the request body or query string is trusted for identity.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("A bearer access token is required.")
    return get_token_verifier().verify(credentials.credentials)


def get_current_user(
    auth_user: Annotated[AuthUser, Depends(get_current_auth_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Return the local user row for the verified identity, provisioning it once."""
    return AuthService(db).ensure_user(auth_user)


def get_pagination() -> PaginationParams:
    """Default pagination parameters (kept for explicit dependency use)."""
    return PaginationParams()


AuthUserDep = Annotated[AuthUser, Depends(get_current_auth_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]
