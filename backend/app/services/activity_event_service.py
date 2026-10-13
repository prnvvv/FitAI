"""Activity event log business logic."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.activity_event import ActivityEvent
from app.models.enums import ActivityEventType
from app.repositories.activity_event_repository import ActivityEventRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivityEventService:
    """Records and queries the user activity log."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ActivityEventRepository(db)

    def record(
        self,
        user_id: uuid.UUID,
        event_type: ActivityEventType,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        occurred_at: datetime | None = None,
        source: str = "user",
        payload: dict[str, object] | None = None,
    ) -> ActivityEvent:
        """Append an event in the current transaction."""
        try:
            event = self._events.create(
                user_id,
                event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                occurred_at=occurred_at or _utcnow(),
                source=source,
                payload=payload,
            )
            self._db.flush()
            return event
        except SQLAlchemyError as exc:
            # Roll back only this operation, do not break the parent transaction
            try:
                self._db.rollback()
            except Exception:
                pass
            from app.core.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(
                "activity_event_record_failed",
                user_id=str(user_id),
                event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
                error=exc.__class__.__name__,
            )
            raise AppError("The activity event could not be recorded.") from exc

    def list(
        self,
        user_id: uuid.UUID,
        *,
        types: Sequence[ActivityEventType] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ActivityEvent], int]:
        """Return a page of the user's activity events."""
        return self._events.list_for_user(user_id, types=types, limit=limit, offset=offset)

    def clear(self, user_id: uuid.UUID) -> int:
        """Delete all events for a user."""
        try:
            count = self._events.delete_for_user(user_id)
            self._db.commit()
            return count
        except SQLAlchemyError as exc:
            try:
                self._db.rollback()
            except Exception:
                pass
            from app.core.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(
                "activity_event_clear_failed",
                user_id=str(user_id),
                error=exc.__class__.__name__,
            )
            raise AppError("The activity history could not be cleared.") from exc
