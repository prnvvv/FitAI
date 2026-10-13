"""Activity log tool for the agent."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.models.enums import ActivityEventType
from app.services.activity_event_service import ActivityEventService

log = logging.getLogger(__name__)


def get_activity_log(
    user_id: str,
    *,
    days: int = 14,
    types: list[str] | None = None,
    db_session: Any | None = None,
) -> dict[str, Any]:
    """Return a user's recent activity events.

    This function is normally called from within the FastAPI request context
    where a DB session is available. If ``db_session`` is not provided, it
    returns an error rather than creating its own session.
    """
    if db_session is None:
        return {"events": [], "error": "Activity log is not available outside a request."}

    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        event_types = None
        if types:
            event_types = [
                ActivityEventType(t) for t in types if t in ActivityEventType._value2member_map_
            ]
        service = ActivityEventService(db_session)
        items, total = service.list(
            UUID(user_id),
            types=event_types or [],
            limit=50,
            offset=0,
        )
        return {
            "events": [
                {
                    "type": item.type.value,
                    "occurred_at": item.occurred_at.isoformat(),
                    "payload": item.payload,
                }
                for item in items
                if item.occurred_at is None or item.occurred_at >= since
            ],
            "total": total,
            "range_days": days,
        }
    except Exception as exc:
        log.warning("activity log query failed: %s", exc)
        return {"events": [], "error": f"Could not read activity log: {type(exc).__name__}"}
