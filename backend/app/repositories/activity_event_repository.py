"""Activity event persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.models.enums import ActivityEventType


class ActivityEventRepository:
    """Persistence operations for the activity event log."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
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
        """Append a new activity event (the caller is responsible for flushing)."""
        from datetime import datetime, timezone

        occurred = occurred_at or datetime.now(timezone.utc)
        event = ActivityEvent(
            user_id=user_id,
            type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_at=occurred,
            source=source,
            payload=payload,
        )
        self._db.add(event)
        return event

    def exists_within(
        self,
        user_id: uuid.UUID,
        event_type: ActivityEventType,
        entity_type: str | None,
        entity_id: str,
        *,
        within_seconds: int,
    ) -> bool:
        """True when the same entity was already logged for this type recently.

        Used to coalesce rapid repeated edits into a single activity event.
        """
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        statement = (
            select(ActivityEvent.id)
            .where(
                ActivityEvent.user_id == user_id,
                ActivityEvent.type == event_type,
                ActivityEvent.entity_id == entity_id,
                ActivityEvent.occurred_at >= cutoff,
            )
            .limit(1)
        )
        if entity_type is not None:
            statement = statement.where(ActivityEvent.entity_type == entity_type)
        return self._db.scalar(statement) is not None

    def exists(
        self,
        user_id: uuid.UUID,
        event_type: ActivityEventType,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> bool:
        """True when such an event was EVER recorded (durable checkpoint).

        Unlike :meth:`exists_within` this has no time window, which makes it
        suitable for marking historical messages as already processed by the
        extraction backfill.
        """
        statement = select(ActivityEvent.id).where(
            ActivityEvent.user_id == user_id,
            ActivityEvent.type == event_type,
        )
        if entity_type is not None:
            statement = statement.where(ActivityEvent.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(ActivityEvent.entity_id == entity_id)
        return self._db.scalar(statement.limit(1)) is not None

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        types: Sequence[ActivityEventType] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ActivityEvent], int]:
        """Return a page of events for the user, newest first."""
        filters = [ActivityEvent.user_id == user_id]
        if types:
            filters.append(ActivityEvent.type.in_(types))
        total = self._db.scalar(select(func.count()).select_from(ActivityEvent).where(*filters))
        statement = (
            select(ActivityEvent)
            .where(*filters)
            .order_by(ActivityEvent.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Delete all activity events for a user (privacy reset)."""
        from sqlalchemy import delete

        result = self._db.execute(delete(ActivityEvent).where(ActivityEvent.user_id == user_id))
        return int(getattr(result, "rowcount", 0))
