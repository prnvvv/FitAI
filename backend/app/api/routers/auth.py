"""Authentication identity endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.models.user import User
from app.schemas.auth import AuthMeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeOut)
def read_current_user(current_user: CurrentUser) -> User:
    """Return the identity derived from the verified access token."""
    return current_user
