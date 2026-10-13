"""Profile persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import Profile


class ProfileRepository:
    """Persistence operations for user profiles."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_user(self, user_id: UUID) -> Profile | None:
        """Return the profile belonging to ``user_id``."""
        statement = select(Profile).where(Profile.user_id == user_id)
        return self._db.scalar(statement)

    def create(self, user_id: UUID, **fields: object) -> Profile:
        """Create and persist a profile for ``user_id``."""
        profile = Profile(user_id=user_id, **fields)
        self._db.add(profile)
        self._db.flush()
        return profile

    def update(self, profile: Profile, fields: dict[str, object]) -> Profile:
        """Apply ``fields`` to ``profile`` and flush."""
        for name, value in fields.items():
            setattr(profile, name, value)
        self._db.flush()
        return profile
