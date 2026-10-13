"""Profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.schemas.profile import ProfileOut, ProfilePatch, ProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(current_user: CurrentUser, db: DbSession) -> ProfileOut:
    """Return the authenticated user's profile.

    Returns 404 until a profile has been created with PUT or PATCH.
    """
    profile = ProfileService(db).get(current_user.id)
    if profile is None:
        raise NotFoundError("Profile not found.")
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
def replace_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> ProfileOut:
    """Create or fully replace the authenticated user's profile."""
    fields = payload.model_dump(exclude_unset=False)
    profile = ProfileService(db).update(current_user.id, fields, partial=False)
    return ProfileOut.model_validate(profile)


@router.patch("", response_model=ProfileOut)
def update_profile(
    payload: ProfilePatch,
    current_user: CurrentUser,
    db: DbSession,
) -> ProfileOut:
    """Partially update the authenticated user's profile."""
    fields = payload.model_dump(exclude_unset=True)
    profile = ProfileService(db).update(current_user.id, fields, partial=True)
    return ProfileOut.model_validate(profile)
