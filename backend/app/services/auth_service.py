"""Authentication-adjacent persistence: provisioning the local user anchor."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import AuthUser
from app.models.user import User
from app.repositories.user_repository import UserRepository


class AuthService:
    """Ensures a local user row exists for a verified Supabase identity."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._users = UserRepository(db)

    def ensure_user(self, auth_user: AuthUser) -> User:
        """Return the local user row, creating it on first authenticated request."""
        user, created = self._users.get_or_create(auth_user.id, auth_user.email)
        self._db.commit()
        if created:
            self._db.refresh(user)
        return user
