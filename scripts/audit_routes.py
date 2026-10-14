"""Live contract audit: call every route the frontend uses, as the audit user.

Run with: backend/.venv/Scripts/python.exe scripts/audit_routes.py <session.json>
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(token: str, method: str, path: str, payload: object | None = None) -> tuple[int, str]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, response.read().decode()[:300]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]
    except urllib.error.URLError as exc:
        return 0, str(exc)


def main() -> int:
    session = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    token = session["token"]

    calls: list[tuple[str, str, str, object | None]] = [
        ("GET", "/health", "public", None),
        ("GET", "/api/v1/auth/me", "profile load", None),
        ("GET", "/api/v1/profile", "progress load", None),
        ("GET", "/api/v1/progress/weight", "progress load", None),
        ("GET", "/api/v1/progress/height", "progress load", None),
        ("GET", "/api/v1/progress/bmi", "progress load", None),
        ("GET", "/api/v1/progress/derived", "progress load", None),
        ("GET", "/api/v1/progress/records", "progress records", None),
        ("GET", "/api/v1/progress/measurements?limit=50&offset=0", "history", None),
        ("POST", "/api/v1/progress/measurements", "log weight", {
            "type": "weight", "value": 70, "unit": "kg",
            "measured_at": "2026-10-14T08:00:00Z"}),
        ("POST", "/api/v1/progress/measurements", "log height", {
            "type": "height", "value": 175, "unit": "cm",
            "measured_at": "2026-10-14T08:05:00Z"}),
        ("GET", "/api/v1/progress/bmi", "after height", None),
        ("GET", "/api/v1/plan/summary?from=2026-10-12&to=2026-11-01", "plan month", None),
        ("GET", "/api/v1/plan/summary?from=2026-01-01&to=2026-12-31", "plan year", None),
        ("GET", "/api/v1/plan/sessions?from=2026-10-12&to=2026-11-01&limit=100", "plan week", None),
        ("GET", "/api/v1/plan/templates", "templates", None),
        ("POST", "/api/v1/plan/sessions", "plan a session", {
            "planned_date": "2026-10-14", "title": "Push", "day_type": "workout",
            "notes": None, "exercises": [
                {"exercise_name": "Bench Press", "position": 0,
                 "target_sets": 4, "target_reps": 8, "target_weight": None,
                 "target_weight_unit": None, "duration_seconds": None,
                 "distance_meters": None, "notes": None}]}),
        ("GET", "/api/v1/exercises?limit=100&offset=0", "exercise library", None),
        ("GET", "/api/v1/progress/metrics", "metric definitions", None),
        ("GET", "/api/v1/progress/series?type=weight", "metric series", None),
        ("GET", "/api/v1/progress/series?type=sleep_hours", "empty metric", None),
        ("GET", "/api/v1/progress/series?type=bogus", "unknown metric", None),
        ("GET", "/api/v1/exercises?search=squat&limit=20&offset=0", "combobox search", None),
        ("GET", "/api/v1/exercises/muscle-groups", "muscle groups", None),
        ("GET", "/api/v1/workouts?limit=100&offset=0", "workout list", None),
        ("POST", "/api/v1/workouts", "log session", {
            "performed_at": "2026-10-14T10:00:00Z", "name": "Audit session",
            "sets": [{"exercise_name": "Bench Press", "reps": 5, "weight": 80,
                      "weight_unit": "kg"}]}),
        ("GET", "/api/v1/documents?limit=50&offset=0", "library list", None),
        ("GET", "/api/v1/conversations?limit=50&offset=0", "conversations", None),
        ("POST", "/api/v1/conversations", "create conversation", {"title": "Audit"}),
        ("GET", "/api/v1/memory?limit=50&offset=0", "memory list", None),
        ("GET", "/api/v1/memory/pending?limit=50&offset=0", "pending memory", None),
        ("GET", "/api/v1/activity?limit=100&offset=0", "activity log", None),
    ]

    failures = 0
    for method, path, purpose, payload in calls:
        status, body = call(token, method, path, payload)
        flag = "" if status < 400 else "  <-- PROBLEM"
        if status >= 400:
            failures += 1
        print(f"{status:3} {method:6} {path:60} [{purpose}]{flag}")
        if status >= 400:
            print(f"      {body}")
    print(f"\n{failures} failing call(s) of {len(calls)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
