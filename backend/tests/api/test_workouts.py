"""API tests for workout and measurement endpoints."""

from __future__ import annotations

import uuid


def test_workout_lifecycle(client) -> None:
    payload = {
        "name": "Push day",
        "performed_at": "2026-01-10T18:00:00Z",
        "duration_minutes": 60,
        "notes": "felt strong",
        "sets": [
            {"exercise_name": "Bench Press", "reps": 5, "weight": 80, "weight_unit": "kg"},
            {"exercise_name": "Overhead Press", "reps": 8, "weight": 40, "weight_unit": "kg"},
        ],
    }
    created = client.post("/api/v1/workouts", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert len(body["sets"]) == 2
    session_id = body["id"]

    listed = client.get("/api/v1/workouts")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/workouts/{session_id}")
    assert fetched.status_code == 200

    assert client.delete(f"/api/v1/workouts/{session_id}").status_code == 204
    assert client.get(f"/api/v1/workouts/{session_id}").status_code == 404


def test_set_with_weight_requires_unit(client) -> None:
    payload = {
        "performed_at": "2026-01-10T18:00:00Z",
        "sets": [{"exercise_name": "Squat", "reps": 5, "weight": 100}],
    }
    response = client.post("/api/v1/workouts", json=payload)
    assert response.status_code == 422


def test_measurement_recording_and_weight_series(client) -> None:
    first = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 80,
            "unit": "kg",
            "measured_at": "2026-01-01T08:00:00Z",
        },
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 79,
            "unit": "kg",
            "measured_at": "2026-02-01T08:00:00Z",
        },
    )
    assert second.status_code == 201

    series = client.get("/api/v1/progress/weight")
    assert series.status_code == 200
    values = [float(item["value"]) for item in series.json()]
    assert values == [80.0, 79.0]

    listed = client.get("/api/v1/progress/measurements", params={"type": "weight"})
    assert listed.json()["total"] == 2


def test_measurement_rejects_invalid_unit(client) -> None:
    response = client.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 80,
            "unit": "cm",
            "measured_at": "2026-01-01T08:00:00Z",
        },
    )
    assert response.status_code == 422


def test_measurements_are_isolated_between_users(make_client) -> None:
    from app.core.security import AuthUser

    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))
    owner.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 82,
            "unit": "kg",
            "measured_at": "2026-01-01T08:00:00Z",
        },
    )
    assert other.get("/api/v1/progress/measurements").json()["total"] == 0
