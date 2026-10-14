"""API tests for progress: height, derived BMI, derived metrics and validation."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser


def _log(client, type_: str, value, unit: str, date_: str = "2026-01-10"):
    return client.post(
        "/api/v1/progress/measurements",
        json={"type": type_, "value": value, "unit": unit, "measured_at": f"{date_}T08:00:00Z"},
    )


def test_height_and_weight_produce_a_bmi_series(client) -> None:
    assert _log(client, "height", 175, "cm", "2026-01-01").status_code == 201
    assert _log(client, "weight", 70, "kg", "2026-01-05").status_code == 201

    heights = client.get("/api/v1/progress/height").json()
    assert [float(h["value"]) for h in heights] == [175.0]

    bmi = client.get("/api/v1/progress/bmi").json()
    assert len(bmi) == 1
    point = bmi[0]
    assert float(point["value"]) == 22.9  # 70 / 1.75^2, rounded to one decimal
    assert point["source"] == "derived"
    assert float(point["weight_kg"]) == 70.0
    assert float(point["height_cm"]) == 175.0


def test_bmi_is_empty_without_a_height_entry(client) -> None:
    assert _log(client, "weight", 80, "kg").status_code == 201
    assert client.get("/api/v1/progress/bmi").json() == []


def test_bmi_pairs_each_weight_with_the_latest_prior_height(client) -> None:
    _log(client, "height", 170, "cm", "2026-01-01")
    _log(client, "weight", 70, "kg", "2026-02-01")
    _log(client, "height", 180, "cm", "2026-03-01")
    _log(client, "weight", 80, "kg", "2026-04-01")

    values = [float(p["value"]) for p in client.get("/api/v1/progress/bmi").json()]
    assert values == [24.2, 24.7]


def test_bmi_converts_pounds_to_kilograms(client) -> None:
    _log(client, "height", 175, "cm", "2026-01-01")
    _log(client, "weight", 154.3, "lb", "2026-02-01")

    point = client.get("/api/v1/progress/bmi").json()[0]
    assert float(point["weight_kg"]) == 69.99
    assert float(point["value"]) == 22.9


def test_measurement_units_are_validated(client) -> None:
    assert _log(client, "weight", 70, "cm").status_code == 422
    assert _log(client, "height", 175, "kg").status_code == 422


def test_measurement_ranges_are_validated(client) -> None:
    too_light = _log(client, "weight", 5, "kg")
    assert too_light.status_code == 422
    assert "between" in str(too_light.json())

    too_tall = _log(client, "height", 400, "cm")
    assert too_tall.status_code == 422

    assert _log(client, "weight", 70, "kg").status_code == 201
    assert _log(client, "height", 175, "cm").status_code == 201


def test_derived_metrics_are_computed_from_sessions(client) -> None:
    client.post(
        "/api/v1/workouts",
        json={
            "name": "Push",
            "performed_at": "2026-01-05T10:00:00Z",
            "sets": [
                {"exercise_name": "Bench Press", "reps": 5, "weight": 80, "weight_unit": "kg"}
            ],
        },
    )
    client.post(
        "/api/v1/workouts",
        json={
            "name": "Pull",
            "performed_at": "2026-01-06T10:00:00Z",
            "sets": [
                {"exercise_name": "Bench Press", "reps": 5, "weight": 85, "weight_unit": "kg"},
                {"exercise_name": "Barbell Row", "reps": 10, "weight": 60, "weight_unit": "kg"},
            ],
        },
    )

    metrics = client.get("/api/v1/progress/derived").json()
    assert metrics["sessions_completed"] == 2
    assert metrics["active_days"] == 2
    assert metrics["total_volume_kg"] == 80 * 5 + 85 * 5 + 60 * 10
    assert {r["exercise_name"] for r in metrics["personal_records"]} == {
        "Bench Press",
        "Barbell Row",
    }
    bench = next(r for r in metrics["personal_records"] if r["exercise_name"] == "Bench Press")
    assert float(bench["weight"]) == 85.0
    assert bench["weight_unit"] == "kg"
    assert metrics["source"] == "derived"
    assert len(metrics["weekly_sessions"]) >= 1


def test_derived_metrics_are_empty_for_a_new_user(client) -> None:
    metrics = client.get("/api/v1/progress/derived").json()
    assert metrics["sessions_completed"] == 0
    assert metrics["total_volume_kg"] == 0
    assert metrics["current_streak_days"] == 0
    assert metrics["planned_completion_rate"] is None


def test_derived_metrics_reject_a_reversed_range(client) -> None:
    response = client.get("/api/v1/progress/derived?from=2026-02-01&to=2026-01-01")
    assert response.status_code == 400


def test_progress_is_scoped_to_the_user(make_client) -> None:
    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))

    owner.post(
        "/api/v1/progress/measurements",
        json={
            "type": "weight",
            "value": 70,
            "unit": "kg",
            "measured_at": "2026-01-10T08:00:00Z",
        },
    )

    assert len(other.get("/api/v1/progress/weight").json()) == 0
    assert other.get("/api/v1/progress/bmi").json() == []
    assert other.get("/api/v1/progress/derived").json()["sessions_completed"] == 0
