"""Profile business logic."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.profile import Profile
from app.repositories.profile_repository import ProfileRepository

WRITABLE_FIELDS = frozenset(
    {
        "date_of_birth",
        "height_cm",
        "weight_kg",
        "goal",
        "activity_level",
        "dietary_preferences",
        "dietary_restrictions",
        "supplements",
        "preferences",
        "location_label",
        "location_lat",
        "location_lon",
        "location_timezone",
    }
)


class ProfileService:
    """Coordinates profile creation and updates."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._profiles = ProfileRepository(db)

    def get(self, user_id: UUID) -> Profile | None:
        """Return the user's profile, or None if it has not been created."""
        return self._profiles.get_for_user(user_id)

    def get_or_create(self, user_id: UUID) -> Profile:
        """Return the profile, creating an empty one when absent."""
        profile = self._profiles.get_for_user(user_id)
        if profile is not None:
            return profile
        profile = self._profiles.create(user_id)
        self._commit()
        return profile

    def update(self, user_id: UUID, fields: dict[str, object], *, partial: bool) -> Profile:
        """Create or update the profile.

        When ``partial`` is False (PUT semantics) every writable field is set,
        using ``None`` for values the client omitted. When True (PATCH
        semantics) only the supplied fields are changed.
        """
        unknown = set(fields) - WRITABLE_FIELDS
        if unknown:
            raise AppError(
                "Unknown profile fields were supplied.",
                details={"fields": sorted(unknown)},
            )

        payload = dict(fields)
        if not partial:
            for name in WRITABLE_FIELDS:
                payload.setdefault(name, None)

        profile = self._profiles.get_for_user(user_id)
        if profile is None:
            profile = self._profiles.create(user_id, **payload)
        else:
            self._profiles.update(profile, payload)
        self._commit()
        self._db.refresh(profile)
        return profile

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The profile could not be saved.") from exc
