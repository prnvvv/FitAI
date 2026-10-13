"""Trend analysis over real dated history (weight, measurements, workouts, goals).

No interpolation or extrapolation beyond what the data supports: sparse data yields
`insufficient_data`. Services are injected; the user comes from `config["configurable"]["user_id"]`.
"""
import math
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any, Literal, Protocol

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from .calculations import ToolInputError
from .workout_tools import WorkoutService, call_service, require_user_id, utc_today


class DatedValue(BaseModel):
    on: date
    value: float  # canonical units: kg for weight, cm for measurements


class GoalEntry(BaseModel):
    on: date
    goal: str
    metric: str | None = None          # e.g. "weight"
    target_value: float | None = None  # canonical units
    status: str | None = None


class ProgressService(Protocol):
    """Implemented by the existing profile/history service adapter."""

    def get_weight_history(self, user_id: str, start: date, end: date) -> Sequence[DatedValue]: ...
    def get_measurement_history(self, user_id: str, site: str, start: date, end: date) -> Sequence[DatedValue]: ...
    def get_goal_history(self, user_id: str) -> Sequence[GoalEntry]: ...


def analyze_trend(points: Sequence[DatedValue], flat_threshold_per_week: float,
                  min_points: int = 3, min_span_days: int = 7) -> dict[str, Any]:
    """Least-squares trend on actual points (one per date, last entry wins)."""
    by_date: dict[date, float] = {}
    for p in sorted(points, key=lambda p: p.on):
        if math.isfinite(p.value):
            by_date[p.on] = p.value
    pts = sorted(by_date.items())
    if not pts:
        return {"status": "no_data", "points": 0}
    (d0, v0), (d1, v1) = pts[0], pts[-1]
    span = (d1 - d0).days
    out: dict[str, Any] = {
        "status": "ok", "points": len(pts), "span_days": span,
        "first": {"date": d0.isoformat(), "value": round(v0, 2)},
        "latest": {"date": d1.isoformat(), "value": round(v1, 2)},
        "change": round(v1 - v0, 2),
        "max_gap_days": max((b[0] - a[0]).days for a, b in zip(pts, pts[1:], strict=False)) if len(pts) > 1 else 0}
    if len(pts) < min_points or span < min_span_days:
        out["status"] = "insufficient_data"
        out["needs"] = f"at least {min_points} dated points spanning {min_span_days}+ days"
        return out
    xs = [(d - d0).days for d, _ in pts]
    ys = [v for _, v in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    syy = sum((y - my) ** 2 for y in ys)
    slope_week = (sxy / sxx) * 7
    out["slope_per_week"] = round(slope_week, 3)
    out["r_squared"] = round(sxy ** 2 / (sxx * syy), 2) if syy > 0 else None
    out["direction"] = ("stable" if abs(slope_week) < flat_threshold_per_week
                        else "increasing" if slope_week > 0 else "decreasing")
    return out


def analyze_workout_consistency(workouts: Sequence[Any], start: date, end: date) -> dict[str, Any]:
    """Sessions per Monday-start week over [start, end], gaps, and recent-vs-prior comparison."""
    dated = sorted(w.performed_on for w in workouts if start <= w.performed_on <= end)
    if not dated:
        return {"status": "no_data", "sessions": 0}
    monday = lambda d: d - timedelta(days=d.weekday())  # noqa: E731
    weeks: dict[date, int] = {}
    w = monday(start)
    while w <= end:
        weeks[w] = 0
        w += timedelta(days=7)
    for d in dated:
        weeks[monday(d)] += 1
    days = (end - start).days + 1
    mid = start + timedelta(days=days // 2)
    first_half = sum(1 for d in dated if d < mid)
    gaps = [(b - a).days for a, b in zip(dated, dated[1:], strict=False)]
    return {"status": "ok", "sessions": len(dated), "active_days": len(set(dated)),
            "sessions_per_week": round(len(dated) / (days / 7), 2),
            "weekly_sessions": [{"week_of": k.isoformat(), "sessions": v} for k, v in sorted(weeks.items())],
            "longest_gap_days": max(gaps) if gaps else 0,
            "days_since_last_workout": (end - dated[-1]).days,
            "sessions_first_half": first_half, "sessions_second_half": len(dated) - first_half}


def make_progress_tools(progress: ProgressService, workouts: WorkoutService,
                        today: Callable[[], date] = utc_today) -> list[BaseTool]:
    """Build LangGraph-compatible progress tools bound to the given services."""

    def _window(days: int, lo: int, hi: int) -> tuple[date, date]:
        if not lo <= days <= hi:
            raise ToolInputError(f"days must be between {lo} and {hi}")
        end = today()
        return end - timedelta(days=days), end

    def _clip(points: Sequence[DatedValue], start: date, end: date) -> list[DatedValue]:
        return [p for p in points if start <= p.on <= end]

    def weight_trend(config: RunnableConfig, days: int = 90) -> dict[str, Any]:
        """Weight trend (kg) from the user's recorded weigh-ins over the last `days` days (7-730)."""
        uid = require_user_id(config)
        start, end = _window(days, 7, 730)
        pts = _clip(call_service(progress.get_weight_history, uid, start, end), start, end)
        return {"window_days": days, "unit": "kg", **analyze_trend(pts, flat_threshold_per_week=0.1)}

    def measurement_trend(site: Literal["waist", "chest", "hips", "arm", "thigh", "neck", "other"] | str,
                          config: RunnableConfig, days: int = 90) -> dict[str, Any]:
        """Trend (cm) for one body measurement site (e.g. waist) over the last `days` days (7-730)."""
        uid = require_user_id(config)
        site = " ".join(str(site).lower().split())
        if not site:
            raise ToolInputError("site is required")
        start, end = _window(days, 7, 730)
        pts = _clip(call_service(progress.get_measurement_history, uid, site, start, end), start, end)
        return {"site": site, "window_days": days, "unit": "cm",
                **analyze_trend(pts, flat_threshold_per_week=0.1)}

    def workout_consistency(config: RunnableConfig, days: int = 56) -> dict[str, Any]:
        """Workout frequency and consistency over the last `days` days (7-365)."""
        uid = require_user_id(config)
        start, end = _window(days, 7, 365)
        data = call_service(workouts.get_workouts, uid, start, end)
        return {"window_days": days, **analyze_workout_consistency(data, start, end)}

    def goal_progress(config: RunnableConfig) -> dict[str, Any]:
        """Current goal and its history; for numeric weight goals, progress from recorded weigh-ins."""
        uid = require_user_id(config)
        goals = sorted(call_service(progress.get_goal_history, uid), key=lambda g: g.on)
        if not goals:
            return {"status": "no_data"}
        cur = goals[-1]
        out: dict[str, Any] = {
            "status": "ok", "current_goal": cur.model_dump(mode="json"),
            "history": [g.model_dump(mode="json") for g in goals[-10:]]}
        if cur.metric != "weight" or cur.target_value is None:
            out["progress_pct"] = None
            out["note"] = "goal has no numeric weight target; progress not computed"
            return out
        end = today()
        weights = _clip(call_service(progress.get_weight_history, uid, cur.on, end), cur.on, end)
        if not weights:
            out["progress_pct"] = None
            out["note"] = "no weigh-ins recorded since the goal was set"
            return out
        pts = sorted(weights, key=lambda p: p.on)
        start_w, latest = pts[0].value, pts[-1].value
        trend = analyze_trend(pts, flat_threshold_per_week=0.1, min_points=4, min_span_days=14)
        out.update(start_value=round(start_w, 2), latest_value=round(latest, 2), target_value=cur.target_value,
                   remaining=round(cur.target_value - latest, 2),
                   progress_pct=(None if start_w == cur.target_value else
                                 round((latest - start_w) / (cur.target_value - start_w) * 100, 1)),
                   trend=trend)
        slope = trend.get("slope_per_week")
        remaining = cur.target_value - latest
        if slope and remaining * slope > 0:
            weeks = remaining / slope
            if 0 < weeks <= 104:
                out["eta_weeks_estimate"] = round(weeks, 1)  # linear extrapolation; an estimate only
        return out

    return [StructuredTool.from_function(f, handle_tool_error=True)
            for f in (weight_trend, measurement_trend, workout_consistency, goal_progress)]
