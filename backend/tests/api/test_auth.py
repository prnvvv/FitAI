"""API tests for the authentication identity endpoint."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.security import AuthUser


def test_auth_me_returns_identity(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == body["id"]  # valid uuid string
    uuid.UUID(body["id"])
    assert body["email"] == "user@example.com"


def test_auth_me_without_token_returns_401(anon_client: TestClient) -> None:
    response = anon_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_auth_me_with_malformed_token_returns_401(anon_client: TestClient) -> None:
    response = anon_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_user_is_provisioned_once(make_client) -> None:
    user_id = uuid.uuid4()
    auth_user = AuthUser(id=user_id, email="same@example.com")
    first = make_client(auth_user).get("/api/v1/auth/me")
    second = make_client(auth_user).get("/api/v1/auth/me")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == str(user_id)
    assert second.json()["id"] == str(user_id)
