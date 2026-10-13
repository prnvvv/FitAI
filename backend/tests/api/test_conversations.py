"""API tests for conversation and message endpoints."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser


def test_conversation_lifecycle(client) -> None:
    created = client.post("/api/v1/conversations", json={"title": "Leg day"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    listed = client.get("/api/v1/conversations")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/conversations/{conversation_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Leg day"

    renamed = client.patch(f"/api/v1/conversations/{conversation_id}", json={"title": "Push day"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Push day"

    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    assert messages.json()["items"] == []

    deleted = client.delete(f"/api/v1/conversations/{conversation_id}")
    assert deleted.status_code == 204

    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404


def test_conversation_ownership_is_enforced(make_client) -> None:
    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))

    conversation_id = owner.post("/api/v1/conversations", json={"title": "Mine"}).json()["id"]

    assert other.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert other.delete(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert owner.get(f"/api/v1/conversations/{conversation_id}").status_code == 200


def test_delete_conversation_does_not_touch_profile(make_client) -> None:
    user = make_client(AuthUser(id=uuid.uuid4()))
    user.put("/api/v1/profile", json={"goal": "cut"})
    conversation_id = user.post("/api/v1/conversations", json={"title": "Temp"}).json()["id"]

    assert user.delete(f"/api/v1/conversations/{conversation_id}").status_code == 204
    assert user.get("/api/v1/profile").status_code == 200
