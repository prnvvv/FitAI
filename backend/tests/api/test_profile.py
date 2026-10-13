"""API tests for profile endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_profile_creates_empty_profile_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["goal"] is None
    assert body["weight_kg"] is None


def test_put_profile_creates_profile(client: TestClient) -> None:
    response = client.put(
        "/api/v1/profile",
        json={
            "date_of_birth": "1995-06-15",
            "height_cm": 180.5,
            "weight_kg": 78.2,
            "goal": "build muscle",
            "activity_level": "moderate",
            "dietary_preferences": ["high protein"],
            "dietary_restrictions": [],
            "supplements": [],
            "preferences": {"units": "metric"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["goal"] == "build muscle"
    assert body["activity_level"] == "moderate"
    assert body["age"] >= 0


def test_patch_profile_updates_only_supplied_fields(client: TestClient) -> None:
    client.put("/api/v1/profile", json={"goal": "build muscle", "weight_kg": 80})
    response = client.patch("/api/v1/profile", json={"weight_kg": 79})
    assert response.status_code == 200
    body = response.json()
    assert body["weight_kg"] == 79.0 or float(body["weight_kg"]) == 79.0
    assert body["goal"] == "build muscle"


def test_patch_rejects_invalid_measurement(client: TestClient) -> None:
    response = client.patch("/api/v1/profile", json={"height_cm": -5})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_rejects_future_date_of_birth(client: TestClient) -> None:
    response = client.patch("/api/v1/profile", json={"date_of_birth": "2999-01-01"})
    assert response.status_code == 422


def test_profiles_are_isolated_between_users(make_client) -> None:
    user_a = make_client()
    user_b = make_client()
    user_a.put("/api/v1/profile", json={"goal": "cut"})
    response = user_b.get("/api/v1/profile")
    assert response.status_code == 200
    assert response.json()["goal"] is None
