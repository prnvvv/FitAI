"""Workout logging, summaries and personal-record analysis via an injected service.

Tools take the user from `config["configurable"]["user_id"]` (set by the authenticated caller),
never from model-supplied arguments.
"""
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field, field_validator

from .calculations import ToolInputError


class SetEntry(BaseModel):
    reps: int = Field(ge=1, le=200)
    weight_kg: float = Field(default=0, ge=0, le=1000)  # 0 = bodyweight


class ExerciseEntry(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sets: list[SetEntry] = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("exercise name is blank")
        return v


class WorkoutLog(BaseModel):
    performed_on: date
    name: str | None = Field(default=None, max_length=80)
    duration_min: int | None = Field(default=None, ge=1, le=600)
    exercises: list[ExerciseEntry] = Field(min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=500)


class WorkoutService(Protocol):
    """Implemented by the existing workout service/repository adapter."""

    def log_workout(self, user_id: str, workout: WorkoutLog) -> str | None:
        """Persist and return the workout id once committed; None/raise otherwise."""

    def get_workouts(self, user_id: str, start: date, end: date) -> Sequence[WorkoutLog]:
        """Workouts with start <= performed_on <= end."""


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def require_user_id(config: RunnableConfig) -> str:
    uid = ((config or {}).get("configurable") or {}).get("user_id")
    if not isinstance(uid, str) or not uid.strip():
        raise ToolInputError("no authenticated user in this request")
    return uid


def call_service(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a service call; convert any failure into a safe ToolException."""
    try:
        return fn(*args)
    except ToolException:
        raise
    except Exception as exc:
        raise ToolException(f"data service unavailable ({type(exc).__name__}); nothing was changed") from exc


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def estimate_1rm(weight_kg: float, reps: int) -> float | None:
    """Epley estimate; only meaningful up to 12 reps."""
    if weight_kg <= 0 or reps > 12:
        return None
    return weight_kg if reps == 1 else weight_kg * (1 + reps / 30)


def summarize_workouts(workouts: Sequence[WorkoutLog]) -> dict[str, Any]:
    """Totals and per-exercise breakdown from actual logged workouts."""
    if not workouts:
        return {"status": "no_data", "sessions": 0}
    per: dict[str, dict[str, Any]] = {}
    total_sets = 0
    volume = 0.0
    durations = [w.duration_min for w in workouts if w.duration_min]
    for w in workouts:
        for ex in w.exercises:
            e = per.setdefault(_norm(ex.name), {"exercise": _norm(ex.name), "sessions": 0, "sets": 0,
                                                "volume_kg": 0.0, "max_weight_kg": 0.0})
            e["sessions"] += 1
            for s in ex.sets:
                e["sets"] += 1
                e["volume_kg"] += s.reps * s.weight_kg
                e["max_weight_kg"] = max(e["max_weight_kg"], s.weight_kg)
                total_sets += 1
                volume += s.reps * s.weight_kg
    exercises = sorted(per.values(), key=lambda e: e["volume_kg"], reverse=True)
    for e in exercises:
        e["volume_kg"] = round(e["volume_kg"], 1)
    dates = sorted({w.performed_on for w in workouts})
    return {"status": "ok", "sessions": len(workouts), "active_days": len(dates),
            "first_date": dates[0].isoformat(), "last_date": dates[-1].isoformat(),
            "total_sets": total_sets, "total_volume_kg": round(volume, 1),
            "total_duration_min": sum(durations), "sessions_with_duration": len(durations),
            "exercises": exercises}


def analyze_personal_records(workouts: Sequence[WorkoutLog], exercise: str | None = None) -> dict[str, Any]:
    """Max weight, best estimated 1RM, bodyweight rep max and max-weight progression per exercise."""
    wanted = _norm(exercise) if exercise else None
    state: dict[str, dict[str, Any]] = {}
    for w in sorted(workouts, key=lambda w: w.performed_on):
        day = w.performed_on.isoformat()
        for ex in w.exercises:
            key = _norm(ex.name)
            if wanted and key != wanted:
                continue
            r = state.setdefault(key, {"exercise": key, "max_weight_kg": None, "max_weight_reps": None,
                                       "max_weight_date": None, "best_est_1rm_kg": None,
                                       "best_est_1rm_date": None, "max_bodyweight_reps": None,
                                       "max_bodyweight_reps_date": None, "pr_events": []})
            for s in ex.sets:
                if s.weight_kg > 0:
                    if r["max_weight_kg"] is None or s.weight_kg > r["max_weight_kg"]:
                        r.update(max_weight_kg=s.weight_kg, max_weight_reps=s.reps, max_weight_date=day)
                        event = {"date": day, "weight_kg": s.weight_kg, "reps": s.reps,
                                 "baseline": not r["pr_events"]}
                        if r["pr_events"] and r["pr_events"][-1]["date"] == day:
                            event["baseline"] = r["pr_events"][-1]["baseline"]
                            r["pr_events"][-1] = event
                        else:
                            r["pr_events"].append(event)
                    e1 = estimate_1rm(s.weight_kg, s.reps)
                    if e1 is not None and (r["best_est_1rm_kg"] is None or e1 > r["best_est_1rm_kg"]):
                        r.update(best_est_1rm_kg=round(e1, 1), best_est_1rm_date=day)
                elif r["max_bodyweight_reps"] is None or s.reps > r["max_bodyweight_reps"]:
                    r.update(max_bodyweight_reps=s.reps, max_bodyweight_reps_date=day)
    if not state:
        return {"status": "no_data", "records": []}
    records = sorted(state.values(), key=lambda r: r["exercise"])
    for r in records:
        r["pr_events"] = r["pr_events"][-5:]
    return {"status": "ok", "records": records,
            "note": "Estimated 1RM uses the Epley formula and is only computed for sets of 12 reps or fewer."}


def make_workout_tools(service: WorkoutService, today: Callable[[], date] = utc_today) -> list[BaseTool]:
    """Build LangGraph-compatible tools bound to `service`."""

    def log_workout(performed_on: date, exercises: list[ExerciseEntry], config: RunnableConfig,
                    name: str | None = None, duration_min: int | None = None,
                    notes: str | None = None) -> dict[str, Any]:
        """Log a completed workout. `performed_on` must be an explicit ISO date the user gave
        (not in the future). Reports success only when the service confirms the save."""
        uid = require_user_id(config)
        now = today()
        if performed_on > now:
            raise ToolInputError("performed_on cannot be in the future")
        if performed_on < now - timedelta(days=3650):
            raise ToolInputError("performed_on is implausibly old")
        try:
            log = WorkoutLog(performed_on=performed_on, name=name, duration_min=duration_min,
                             exercises=exercises, notes=notes)
        except ValueError as exc:
            raise ToolInputError(f"invalid workout: {exc}") from exc
        workout_id = call_service(service.log_workout, uid, log)
        if not workout_id:
            raise ToolException("the service did not confirm the save; the workout was NOT logged")
        return {"status": "logged", "workout_id": str(workout_id), "date": performed_on.isoformat()}

    def workout_summary(config: RunnableConfig, days: int = 30) -> dict[str, Any]:
        """Summarise the user's logged workouts for the last `days` days (1-366)."""
        uid = require_user_id(config)
        if not 1 <= days <= 366:
            raise ToolInputError("days must be between 1 and 366")
        end = today()
        data = call_service(service.get_workouts, uid, end - timedelta(days=days), end)
        return {"window_days": days, **summarize_workouts(data)}

    def personal_records(config: RunnableConfig, exercise: str | None = None,
                         days: int = 365) -> dict[str, Any]:
        """Personal records (heaviest set, best estimated 1RM, progression) from logged workouts in the
        last `days` days (1-3650), optionally for one exercise."""
        uid = require_user_id(config)
        if not 1 <= days <= 3650:
            raise ToolInputError("days must be between 1 and 3650")
        end = today()
        data = call_service(service.get_workouts, uid, end - timedelta(days=days), end)
        return {"window_days": days, **analyze_personal_records(data, exercise)}

    return [StructuredTool.from_function(f, handle_tool_error=True)
            for f in (log_workout, workout_summary, personal_records)]
