"""API tests for the plan endpoints: summaries, sessions and templates."""

from __future__ import annotations

import uuid

from app.core.security import AuthUser

SESSION_PAYLOAD = {
    "planned_date": "2026-10-14",
    "title": "Push",
    "day_type": "workout",
    "exercises": [
        {"exercise_name": "Bench Press", "position": 0, "target_sets": 4, "target_reps": 8}
    ],
}


def test_day_summary_returns_every_day_in_range(client) -> None:
    response = client.get("/api/v1/plan/summary?from=2026-10-01&to=2026-10-07")
    assert response.status_code == 200
    days = response.json()
    assert [d["date"] for d in days] == [f"2026-10-{day:02d}" for day in range(1, 8)]
    assert all(day["planned_count"] == 0 for day in days)


def test_day_summary_counts_planned_and_completed(client) -> None:
    created = client.post("/api/v1/plan/sessions", json=SESSION_PAYLOAD)
    assert created.status_code == 201
    session_id = created.json()["id"]

    days = client.get("/api/v1/plan/summary?from=2026-10-13&to=2026-10-15").json()
    by_date = {d["date"]: d for d in days}
    assert by_date["2026-10-14"]["planned_count"] == 1
    assert by_date["2026-10-14"]["completed_count"] == 0
    assert by_date["2026-10-13"]["planned_count"] == 0

    completed = client.post(f"/api/v1/plan/sessions/{session_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    after = {
        d["date"]: d
        for d in client.get("/api/v1/plan/summary?from=2026-10-14&to=2026-10-14").json()
    }
    assert after["2026-10-14"]["completed_count"] == 1


def test_completing_a_planned_session_links_the_logged_workout(client) -> None:
    session_id = client.post("/api/v1/plan/sessions", json=SESSION_PAYLOAD).json()["id"]
    completed = client.post(f"/api/v1/plan/sessions/{session_id}/complete").json()

    assert completed["completed_session_id"] is not None
    logged = client.get(f"/api/v1/workouts/{completed['completed_session_id']}")
    assert logged.status_code == 200
    assert logged.json()["sets"][0]["exercise_name"] == "Bench Press"


def test_summary_range_is_capped(client) -> None:
    ok = client.get("/api/v1/plan/summary?from=2025-01-01&to=2026-01-01")
    assert ok.status_code == 200

    too_wide = client.get("/api/v1/plan/summary?from=2020-01-01&to=2026-01-01")
    assert too_wide.status_code != 200
    assert "400" in str(too_wide.status_code) or too_wide.json()["error"]["code"]


def test_summary_requires_both_bounds(client) -> None:
    assert client.get("/api/v1/plan/summary?from=2026-10-01").status_code == 422


def test_plan_is_scoped_to_the_user(make_client) -> None:
    owner = make_client(AuthUser(id=uuid.uuid4()))
    other = make_client(AuthUser(id=uuid.uuid4()))

    session_id = owner.post("/api/v1/plan/sessions", json=SESSION_PAYLOAD).json()["id"]

    other_days = other.get("/api/v1/plan/summary?from=2026-10-14&to=2026-10-14").json()
    assert other_days[0]["planned_count"] == 0

    assert (
        other.patch(f"/api/v1/plan/sessions/{session_id}", json={"title": "stolen"}).status_code
        == 404
    )
    assert other.post(f"/api/v1/plan/sessions/{session_id}/complete").status_code == 404
    assert other.delete(f"/api/v1/plan/sessions/{session_id}").status_code == 404

    owner_days = owner.get("/api/v1/plan/summary?from=2026-10-14&to=2026-10-14").json()
    assert owner_days[0]["planned_count"] == 1


def test_templates_are_listed_and_applied(client) -> None:
    templates = client.get("/api/v1/plan/templates")
    assert templates.status_code == 200
    keys = {t["key"] for t in templates.json()}
    assert {
        "push_pull_legs",
        "upper_lower",
        "full_body_3",
        "beginner_strength",
        "walk_mobility",
    } <= keys

    applied = client.post(
        "/api/v1/plan/templates/apply",
        json={"template_key": "upper_lower", "start_date": "2026-10-12"},
    )
    assert applied.status_code == 200
    assert len(applied.json()) == 7

    days = {
        d["date"]: d
        for d in client.get("/api/v1/plan/summary?from=2026-10-12&to=2026-10-18").json()
    }
    assert days["2026-10-12"]["planned_count"] == 1
    assert days["2026-10-14"]["day_type"] == "rest"


def test_unknown_template_returns_404(client) -> None:
    response = client.post(
        "/api/v1/plan/templates/apply", json={"template_key": "nope", "start_date": "2026-10-12"}
    )
    assert response.status_code == 404


def test_planned_session_validation(client) -> None:
    missing_date = client.post("/api/v1/plan/sessions", json={"day_type": "workout"})
    assert missing_date.status_code == 422

    bad_date = client.post(
        "/api/v1/plan/sessions", json={"planned_date": "14/10/2026", "day_type": "workout"}
    )
    assert bad_date.status_code == 422
