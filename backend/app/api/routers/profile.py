"""Profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.profile import ProfileOut, ProfilePatch, ProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(current_user: CurrentUser, db: DbSession) -> ProfileOut:
    """Return the authenticated user's profile, creating an empty one if absent.

    The profile is initialized lazily so the UI can always load it without
    treating a missing row as an error.
    """
    profile = ProfileService(db).get_or_create(current_user.id)
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
