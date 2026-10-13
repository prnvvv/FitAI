"""Read-only workout-history lookup exposed to the agent.

The user's logged workouts live in PostgreSQL and are read through the
persistence ``WorkoutService`` (via :class:`WorkoutHistoryService`). This module
resolves the requested date range, fetches the workouts, and serialises them so
the language model can answer questions such as "what exercises did I do on the
13th?" without inventing data.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any, Protocol

from app.tools.calculations import ToolInputError
from app.tools.workout_tools import WorkoutLog, utc_today

#: Hard cap on sessions returned so a long window cannot flood the model context.
MAX_SESSIONS = 100
#: Default look-back window (in days) when the model supplies only a vague request.
DEFAULT_WINDOW_DAYS = 90


class WorkoutHistoryService(Protocol):
    """Read-only view of a user's logged workouts."""

    def get_workouts(self, user_id: str, start: date, end: date) -> Sequence[WorkoutLog]: ...


def _parse_date(value: Any, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ToolInputError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def _parse_days(value: Any) -> int:
    if value is None:
        return DEFAULT_WINDOW_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolInputError("days must be an integer") from exc
    if not 1 <= days <= 365:
        raise ToolInputError("days must be between 1 and 365")
    return days


def resolve_range(args: dict[str, Any], today: date) -> tuple[date, date]:
    """Resolve the requested window from ``start``/``end``/``days`` arguments."""
    start = _parse_date(args.get("start"), "start")
    end = _parse_date(args.get("end"), "end")
    if start is None and end is None:
        end = today
        start = end - timedelta(days=_parse_days(args.get("days")) - 1)
    elif start is None:
        start = end
    elif end is None:
        end = start
    assert start is not None and end is not None
    if start > end:
        raise ToolInputError("start must be on or before end")
    return start, end


def format_workout_history(
    workouts: Sequence[WorkoutLog], *, start: date, end: date
) -> dict[str, Any]:
    """Serialise workouts newest-last into a compact, model-readable dict."""
    ordered = sorted(workouts, key=lambda w: w.performed_on)
    truncated = len(ordered) > MAX_SESSIONS
    if truncated:
        ordered = ordered[-MAX_SESSIONS:]
    sessions = [
        {
            "date": w.performed_on.isoformat(),
            "name": w.name,
            "duration_min": w.duration_min,
            "exercises": [
                {
                    "exercise": ex.name,
                    "sets": [{"reps": s.reps, "weight_kg": s.weight_kg} for s in ex.sets],
                }
                for ex in w.exercises
            ],
        }
        for w in ordered
    ]
    return {
        "status": "ok" if sessions else "no_data",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "session_count": len(sessions),
        "truncated": truncated,
        "sessions": sessions,
    }


def build_workout_history(
    service: WorkoutHistoryService,
    user_id: str,
    args: dict[str, Any],
    *,
    today: Callable[[], date] = utc_today,
) -> dict[str, Any]:
    """Resolve the range, fetch the workouts, and return a formatted result."""
    start, end = resolve_range(args, today())
    workouts = service.get_workouts(user_id, start, end)
    return format_workout_history(workouts, start=start, end=end)
