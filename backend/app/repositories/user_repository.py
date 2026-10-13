"""User account persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Persistence operations for local user anchor rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, user_id: UUID) -> User | None:
        """Return the user row for ``user_id`` if present."""
        return self._db.get(User, user_id)

    def get_or_create(self, user_id: UUID, email: str | None) -> tuple[User, bool]:
        """Return the user row, creating it on first authenticated request.

        Returns a tuple of ``(user, created)``.
        """
        user = self.get(user_id)
        if user is not None:
            if email and user.email != email:
                user.email = email
            return user, False
        user = User(id=user_id, email=email)
        self._db.add(user)
        self._db.flush()
        return user, True

    def exists(self, user_id: UUID) -> bool:
        """Return True when a user row exists for ``user_id``."""
        statement = select(User.id).where(User.id == user_id)
        return self._db.scalar(statement) is not None
