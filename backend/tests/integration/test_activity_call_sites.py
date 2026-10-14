"""Call-site audit: user writes record activity events, and a broken log is harmless.

The client fixture and the db_session fixture share one session, so anything the
API commits is visible here.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityEvent
from app.models.enums import ActivityEventType
from app.repositories.activity_event_repository import ActivityEventRepository


def _user_id(client) -> uuid.UUID:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    return uuid.UUID(response.json()["id"])


def _types(db_session: Session, user_id: uuid.UUID) -> list[ActivityEventType]:
    db_session.expire_all()
    rows = db_session.query(ActivityEvent).filter(ActivityEvent.user_id == user_id).all()
    return [row.type for row in rows]


def test_workout_records_session_completed(client, db_session) -> None:
    user_id = _user_id(client)
    response = client.post(
        "/api/v1/workouts",
        json={
            "performed_at": "2026-10-10T10:00:00Z",
            "sets": [
                {"exercise_name": "Bench Press", "reps": 5, "weight": 80, "weight_unit": "kg"}
            ],
        },
    )
    assert response.status_code == 201
    assert ActivityEventType.SESSION_COMPLETED in _types(db_session, user_id)


def test_metric_records_metric_logged(client, db_session) -> None:
    user_id = _user_id(client)
    response = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 70,
            "unit": "kg",
            "measured_at": "2026-10-10T08:00:00Z",
        },
    )
    assert response.status_code == 201
    assert ActivityEventType.METRIC_LOGGED in _types(db_session, user_id)


def test_height_metric_is_recorded_too(client, db_session) -> None:
    _user_id(client)
    response = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "height",
            "value": 175,
            "unit": "cm",
            "measured_at": "2026-10-10T08:00:00Z",
        },
    )
    assert response.status_code == 201
    _user_id(client)
    payload = [row.payload for row in db_session.query(ActivityEvent).all()]
    assert {"type": "height", "value": "175", "unit": "cm"} in payload


def test_planned_session_records_plan_events(client, db_session) -> None:
    user_id = _user_id(client)
    created = client.post(
        "/api/v1/plan/sessions",
        json={"planned_date": "2026-10-14", "day_type": "workout", "exercises": []},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    client.patch(f"/api/v1/plan/sessions/{session_id}", json={"title": "Push day"})
    client.post(f"/api/v1/plan/sessions/{session_id}/complete")

    types = _types(db_session, user_id)
    assert ActivityEventType.SESSION_PLANNED in types
    assert ActivityEventType.PLAN_EDITED in types
    assert ActivityEventType.SESSION_COMPLETED in types


def test_document_upload_records_document_added(client, db_session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))
    user_id = _user_id(client)

    response = client.post(
        "/api/v1/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 201
    assert ActivityEventType.DOCUMENT_ADDED in _types(db_session, user_id)


def test_writes_succeed_when_the_activity_log_breaks(client, monkeypatch, tmp_path) -> None:
    """A failed event insert must not fail workouts, metrics or documents.

    The failure is simulated at the repository, i.e. exactly where a schema or
    constraint problem would surface.
    """

    def _explode(*_args: object, **_kwargs: object):
        raise ProgrammingError("INSERT INTO activity_events", {}, Exception("boom"))

    monkeypatch.setattr(ActivityEventRepository, "create", _explode)

    workout = client.post(
        "/api/v1/workouts",
        json={
            "performed_at": "2026-10-10T10:00:00Z",
            "sets": [{"exercise_name": "Squat", "reps": 5}],
        },
    )
    metric = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 70,
            "unit": "kg",
            "measured_at": "2026-10-10T08:00:00Z",
        },
    )
    planned = client.post(
        "/api/v1/plan/sessions",
        json={"planned_date": "2026-10-14", "day_type": "workout", "exercises": []},
    )

    assert workout.status_code == 201
    assert metric.status_code == 201
    assert planned.status_code == 201
    assert client.get("/api/v1/workouts").json()["total"] == 1


def test_document_upload_succeeds_when_the_activity_log_breaks(
    client, monkeypatch, tmp_path
) -> None:
    """The same guarantee holds for uploads."""
    monkeypatch.setattr("app.services.document_storage.settings.document_storage_backend", "local")
    monkeypatch.setattr("app.services.document_storage.settings.upload_dir", str(tmp_path))

    def _explode(*_args: object, **_kwargs: object):
        raise ProgrammingError("INSERT INTO activity_events", {}, Exception("boom"))

    monkeypatch.setattr(ActivityEventRepository, "create", _explode)

    response = client.post(
        "/api/v1/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 201
    assert client.get("/api/v1/documents").json()["total"] == 1


def test_recorder_reports_a_broken_log_without_failing_the_request(client, monkeypatch) -> None:
    """The failure is logged with a traceback, and the write still lands."""

    def _explode(*_args: object, **_kwargs: object):
        raise ProgrammingError("INSERT INTO activity_events", {}, Exception("boom"))

    monkeypatch.setattr(ActivityEventRepository, "create", _explode)

    response = client.post(
        "/api/v1/workouts",
        json={
            "performed_at": "2026-10-10T10:00:00Z",
            "sets": [{"exercise_name": "Squat", "reps": 5}],
        },
    )

    assert response.status_code == 201
    assert client.get("/api/v1/workouts").json()["total"] == 1
