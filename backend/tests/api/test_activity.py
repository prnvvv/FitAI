"""API tests for the activity log."""
from __future__ import annotations

import uuid

from app.core.security import AuthUser
from app.services.activity_event_service import ActivityEventService


def test_activity_log_is_empty_initially(client) -> None:
    response = client.get("/api/v1/activity")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_activity_events_are_recorded_on_workout(make_client, db_session) -> None:
    user = AuthUser(id=uuid.uuid4())
    client = make_client(user)

    response = client.post(
        "/api/v1/workouts",
        json={
            "performed_at": "2026-10-01T10:00:00Z",
            "name": "Test session",
            "sets": [{"exercise_name": "Squat", "reps": 5, "weight": 100, "weight_unit": "kg"}],
        },
    )
    assert response.status_code == 201

    log = client.get("/api/v1/activity")
    assert log.status_code == 200
    items = log.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "session_completed"


def test_activity_log_is_isolated(make_client, db_session) -> None:
    from app.models.enums import ActivityEventType

    owner = AuthUser(id=uuid.uuid4())
    other = AuthUser(id=uuid.uuid4())
    ActivityEventService(db_session).record(
        owner.id,
        ActivityEventType.SESSION_COMPLETED,
        entity_type="workout_session",
        entity_id=str(uuid.uuid4()),
    )
    other_client = make_client(other)
    response = other_client.get("/api/v1/activity")
    assert response.status_code == 200
    assert response.json()["total"] == 0
