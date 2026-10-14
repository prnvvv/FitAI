"""Activity event recording must never break the caller's primary action."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.models.enums import ActivityEventType
from app.repositories.activity_event_repository import ActivityEventRepository
from app.services.activity_event_service import ActivityEventService


def test_record_inside_savepoint_leaves_parent_transaction_healthy(db_session: Session) -> None:
    """A failing event insert rolls back only the savepoint."""
    user_id = uuid.uuid4()
    db_session.add(
        ActivityEvent(
            user_id=user_id,
            type=ActivityEventType.PROFILE_UPDATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    # Parent transaction is open and must still be usable afterwards.

    service = ActivityEventService(db_session)
    repository = service._events  # noqa: SLF001 - forcing a failure on purpose

    def _explode(*_args: object, **_kwargs: object) -> ActivityEvent:
        raise ProgrammingError("INSERT INTO activity_events", {}, Exception("boom"))

    original_create = repository.create
    repository.create = _explode  # type: ignore[method-assign]
    try:
        assert service.record(user_id, ActivityEventType.SESSION_COMPLETED) is None
    finally:
        repository.create = original_create  # type: ignore[method-assign]

    # The parent row is still there and the session can still commit.
    db_session.commit()
    assert db_session.query(ActivityEvent).count() == 1


def test_record_returns_the_event_on_success(db_session: Session) -> None:
    user_id = uuid.uuid4()
    event = ActivityEventService(db_session).record(
        user_id,
        ActivityEventType.METRIC_LOGGED,
        entity_type="measurement",
        entity_id="abc",
        payload={"type": "weight"},
    )
    assert event is not None
    assert event.type == ActivityEventType.METRIC_LOGGED
    assert event.payload == {"type": "weight"}

    stored, total = ActivityEventService(db_session).list(user_id)
    db_session.commit()
    assert total == 1
    assert stored[0].entity_type == "measurement"


@pytest.mark.parametrize("event_type", list(ActivityEventType))
def test_every_event_type_is_storable(db_session: Session, event_type: ActivityEventType) -> None:
    """The enum values used in code are exactly what the column accepts."""
    user_id = uuid.uuid4()
    event = ActivityEventService(db_session).record(user_id, event_type)
    db_session.commit()
    assert event is not None
    assert db_session.query(ActivityEvent).one().type == event_type


def test_events_are_scoped_to_their_user(db_session: Session) -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ActivityEventService(db_session).record(user_a, ActivityEventType.METRIC_LOGGED)
    db_session.commit()

    assert ActivityEventService(db_session).list(user_b)[1] == 0
    assert ActivityEventService(db_session).list(user_a)[1] == 1


def test_repeated_edits_to_one_entity_are_coalesced(db_session: Session) -> None:
    user_id = uuid.uuid4()
    service = ActivityEventService(db_session)

    first = service.record(
        user_id, ActivityEventType.PLAN_EDITED, entity_type="planned_session", entity_id="abc"
    )
    second = service.record(
        user_id, ActivityEventType.PLAN_EDITED, entity_type="planned_session", entity_id="abc"
    )
    other_entity = service.record(
        user_id, ActivityEventType.PLAN_EDITED, entity_type="planned_session", entity_id="xyz"
    )
    db_session.commit()

    assert first is not None
    assert second is None  # coalesced into the first
    assert other_entity is not None
    assert ActivityEventService(db_session).list(user_id)[1] == 2


def test_coalescing_can_be_bypassed(db_session: Session) -> None:
    user_id = uuid.uuid4()
    service = ActivityEventService(db_session)
    for _ in range(2):
        service.record(
            user_id,
            ActivityEventType.METRIC_LOGGED,
            entity_type="measurement",
            entity_id="m1",
            coalesce=False,
        )
    db_session.commit()
    assert service.list(user_id)[1] == 2


def test_stale_events_are_not_coalesced(db_session: Session) -> None:
    user_id = uuid.uuid4()
    service = ActivityEventService(db_session)
    old = datetime.now(timezone.utc) - timedelta(seconds=3600)
    service.record(
        user_id,
        ActivityEventType.PLAN_EDITED,
        entity_type="planned_session",
        entity_id="abc",
        occurred_at=old,
    )
    db_session.commit()

    later = service.record(
        user_id, ActivityEventType.PLAN_EDITED, entity_type="planned_session", entity_id="abc"
    )
    db_session.commit()

    assert later is not None
    assert service.list(user_id)[1] == 2


def test_repository_clear_deletes_only_the_owner_events(db_session: Session) -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ActivityEventService(db_session).record(user_a, ActivityEventType.METRIC_LOGGED)
    db_session.commit()
    ActivityEventService(db_session).record(user_b, ActivityEventType.METRIC_LOGGED)
    db_session.commit()

    ActivityEventService(db_session).clear(user_a)

    assert ActivityEventService(db_session).list(user_a)[1] == 0
    assert ActivityEventService(db_session).list(user_b)[1] == 1


def test_repository_create_does_not_flush_by_itself(db_session: Session) -> None:
    """The recorder owns the flush boundary so it can wrap it in a savepoint."""
    user_id = uuid.uuid4()
    repository = ActivityEventRepository(db_session)
    event = repository.create(user_id, ActivityEventType.DOCUMENT_ADDED, entity_id="x")

    assert event.id is None
    db_session.commit()
    assert event.id is not None
