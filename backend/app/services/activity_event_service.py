"""Activity event log business logic."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.models.enums import ActivityEventType
from app.repositories.activity_event_repository import ActivityEventRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pg_error_info(exc: Exception) -> dict[str, object]:
    """Extract a safe, non-PII diagnostic from a driver error."""
    info: dict[str, object] = {"error_type": type(exc).__name__}
    orig = getattr(exc, "orig", None)
    if orig is not None:
        info["driver_type"] = type(orig).__name__
        info["sqlstate"] = getattr(orig, "pgcode", None)
        # Only the SQL error class/message; never parameter values or payload.
        info["driver_message"] = str(orig).split("\n")[0]
    return info


class ActivityEventService:
    """Records and queries the user activity log."""

    #: Rapid repeated edits to the same entity inside this window are coalesced
    #: into one event, so a slider drag cannot flood the log.
    COALESCE_WINDOW_SECONDS = 60

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
        coalesce: bool = True,
    ) -> ActivityEvent | None:
        """Append an event in a SAVEPOINT so a failure cannot break the caller's transaction.

        This is best-effort logging. If the event cannot be recorded, the failure is
        logged with diagnostic details and ``None`` is returned; the parent transaction
        remains active and the user's primary action can still commit.

        Returns ``None`` without writing when the same entity was already logged for
        the same event type inside :attr:`COALESCE_WINDOW_SECONDS`.
        """
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        try:
            with self._db.begin_nested():
                if (
                    coalesce
                    and entity_id is not None
                    and self._events.exists_within(
                        user_id,
                        event_type,
                        entity_type,
                        entity_id,
                        within_seconds=self.COALESCE_WINDOW_SECONDS,
                    )
                ):
                    return None
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
            logger.warning(
                "activity_event_record_failed",
                exc_info=True,
                user_id=str(user_id),
                event_type=event_type.value,
                **_pg_error_info(exc),
            )
            return None

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
            with suppress(Exception):
                self._db.rollback()
            from app.core.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(
                "activity_event_clear_failed",
                user_id=str(user_id),
                error=exc.__class__.__name__,
            )
            raise RuntimeError("The activity history could not be cleared.") from exc
