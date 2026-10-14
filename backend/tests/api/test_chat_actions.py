"""API tests for confirmable chat actions."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser
from app.models.enums import PendingActionType
from app.services.chat_action_service import ChatActionService


def _make_conversation(user, title: str = "Action chat") -> uuid.UUID:
    response = user.post("/api/v1/conversations", json={"title": title})
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _propose_workout(db_session, user_id, conversation_id) -> uuid.UUID:
    action = ChatActionService(db_session).propose(
        user_id,
        conversation_id,
        PendingActionType.LOG_WORKOUT,
        {
            "activity": "Treadmill",
            "duration_minutes": 120,
            "performed_on": "2026-10-01",
            "notes": None,
        },
        "Log Treadmill (120 min) on 2026-10-01",
    )
    return action.id


def test_confirm_workout_action_logs_workout_and_event(make_client, db_session) -> None:
    user_id = uuid.uuid4()
    user = make_client(AuthUser(id=user_id))
    conversation_id = _make_conversation(user)
    action_id = _propose_workout(db_session, user_id, conversation_id)

    response = user.post(f"/api/v1/chat/actions/{action_id}/confirm")
    assert response.status_code == 200
    content = response.json()["message"]["content"]
    assert "Treadmill" in content

    workouts = user.get("/api/v1/workouts")
    assert workouts.status_code == 200
    assert workouts.json()["total"] == 1
    assert workouts.json()["items"][0]["name"] == "Treadmill"

    activity = user.get("/api/v1/activity")
    assert activity.json()["total"] == 1
    assert activity.json()["items"][0]["type"] == "session_completed"


def test_reject_workout_action_does_not_log(make_client, db_session) -> None:
    user_id = uuid.uuid4()
    user = make_client(AuthUser(id=user_id))
    conversation_id = _make_conversation(user)
    action_id = _propose_workout(db_session, user_id, conversation_id)

    response = user.post(f"/api/v1/chat/actions/{action_id}/reject")
    assert response.status_code == 200
    assert "didn't add" in response.json()["message"]["content"]
    assert user.get("/api/v1/workouts").json()["total"] == 0


def test_confirm_measurements_action_generates_answer(make_client, db_session, monkeypatch) -> None:
    user_id = uuid.uuid4()
    user = make_client(AuthUser(id=user_id))
    conversation_id = _make_conversation(user)

    monkeypatch.setattr(
        ChatActionService,
        "_get_completer",
        lambda self: (lambda system, prompt, **_kwargs: "Aim for 150 g of protein."),
    )
    action = ChatActionService(db_session).propose(
        user_id,
        conversation_id,
        PendingActionType.USE_MEASUREMENTS,
        {"question": "How much protein?", "height_cm": 180.0, "weight_kg": 75.0},
        "Use your saved height/weight",
    )

    response = user.post(f"/api/v1/chat/actions/{action.id}/confirm")
    assert response.status_code == 200
    assert "150 g" in response.json()["message"]["content"]


def test_action_cannot_be_confirmed_twice(make_client, db_session) -> None:
    user_id = uuid.uuid4()
    user = make_client(AuthUser(id=user_id))
    conversation_id = _make_conversation(user)
    action_id = _propose_workout(db_session, user_id, conversation_id)

    assert user.post(f"/api/v1/chat/actions/{action_id}/confirm").status_code == 200
    assert user.post(f"/api/v1/chat/actions/{action_id}/confirm").status_code == 409


def test_action_is_isolated_between_users(make_client, db_session) -> None:
    owner_id = uuid.uuid4()
    owner = make_client(AuthUser(id=owner_id))
    conversation_id = _make_conversation(owner)
    action_id = _propose_workout(db_session, owner_id, conversation_id)

    other = make_client(AuthUser(id=uuid.uuid4()))
    assert other.post(f"/api/v1/chat/actions/{action_id}/confirm").status_code == 404


def test_unknown_action_returns_not_found(client) -> None:
    assert client.post(f"/api/v1/chat/actions/{uuid.uuid4()}/confirm").status_code == 404
