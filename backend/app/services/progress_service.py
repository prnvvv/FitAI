"""Progress-history retrieval.

This service returns raw, ownership-scoped history. It intentionally performs
only trivial aggregation; trend analysis, PR *detection*, and fitness
intelligence belong to Person 2.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import MeasurementType
from app.models.measurement import Measurement
from app.repositories.measurement_repository import MeasurementRepository
from app.repositories.workout_repository import WorkoutRepository


class ProgressService:
    """Provides historical records for progress views and analysis."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._measurements = MeasurementRepository(db)
        self._workouts = WorkoutRepository(db)

    def measurement_series(
        self, user_id: UUID, measurement_type: MeasurementType
    ) -> list[Measurement]:
        """Return all measurements of a type in chronological order."""
        return self._measurements.series(user_id, measurement_type)

    def weight_series(self, user_id: UUID) -> list[Measurement]:
        """Return the user's weight measurements in chronological order."""
        return self._measurements.series(user_id, MeasurementType.WEIGHT)

    def height_series(self, user_id: UUID) -> list[Measurement]:
        """Return the user's height measurements in chronological order."""
        return self._measurements.series(user_id, MeasurementType.HEIGHT)

    def bmi_series(self, user_id: UUID) -> list[dict[str, object]]:
        """Return a derived BMI time-series paired with the nearest preceding height.

        Weight entries are paired with the most recent height entry on or before
        the same date. If no height exists for a weight entry, that entry is
        skipped (the caller can show a prompt instead).
        """
        import datetime as dt

        weights = self._measurements.series(user_id, MeasurementType.WEIGHT)
        heights = self._measurements.series(user_id, MeasurementType.HEIGHT)

        # Build a sorted list of (date, height_cm) keeping the latest height per day.
        height_by_date: dict[dt.date, tuple[dt.datetime, Decimal]] = {}
        for h in heights:
            key = h.measured_at.date()
            if key not in height_by_date or h.measured_at > height_by_date[key][0]:
                height_by_date[key] = (h.measured_at, h.value)
        sorted_heights: list[tuple[dt.date, Decimal]] = sorted(
            ((d, v[1]) for d, v in height_by_date.items()), key=lambda x: x[0]
        )

        result: list[dict[str, object]] = []
        current_height_cm: Decimal | None = None
        height_idx = 0
        for w in weights:
            d = w.measured_at.date()
            # Advance height pointer to the latest height on or before this date.
            while height_idx < len(sorted_heights) and sorted_heights[height_idx][0] <= d:
                current_height_cm = sorted_heights[height_idx][1]
                height_idx += 1

            if current_height_cm is None or current_height_cm <= 0:
                continue

            weight_kg = self._to_kg(w.value, w.unit)
            if weight_kg is None:
                continue
            height_m = current_height_cm / Decimal("100")
            bmi = weight_kg / (height_m * height_m)
            bmi = bmi.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            result.append(
                {
                    "measured_at": w.measured_at,
                    "value": bmi,
                    "unit": "bmi",
                    "source": "derived",
                    "weight_kg": weight_kg,
                    "height_cm": current_height_cm,
                }
            )
        return result

    @staticmethod
    def _to_kg(value: Decimal, unit: str) -> Decimal | None:
        if unit == "kg":
            return Decimal(value)
        if unit == "lb":
            return Decimal(value) * Decimal("0.45359237")
        return None

    def derived_metrics(
        self, user_id: UUID, *, from_date: date | None = None, to_date: date | None = None
    ) -> dict[str, object]:
        """Return metrics computed from the user's logged and planned sessions.

        Everything here is derived from stored rows; nothing is persisted.
        """
        today = to_date or date.today()
        start = from_date or (today - timedelta(days=365))

        sessions = self._workouts.list_sessions_with_sets(user_id, start, today)

        sessions_by_day: dict[date, int] = {}
        weekly: dict[date, int] = {}
        total_volume = 0.0
        prs: dict[str, dict[str, object]] = {}

        for session in sessions:
            day = session.performed_at.date()
            sessions_by_day[day] = sessions_by_day.get(day, 0) + 1
            week_start = day - timedelta(days=day.weekday())
            weekly[week_start] = weekly.get(week_start, 0) + 1
            for workout_set in session.sets:
                if workout_set.weight is None:
                    continue
                weight = float(workout_set.weight)
                reps = int(workout_set.reps or 0)
                # Bodyweight moves add no external load; volume counts reps only.
                total_volume += weight * reps
                name = workout_set.exercise_name
                current = prs.get(name)
                if current is None or weight > float(current["weight"]):
                    prs[name] = {
                        "exercise_name": name,
                        "weight": round(weight, 2),
                        "weight_unit": (
                            workout_set.weight_unit.value if workout_set.weight_unit else None
                        ),
                        "achieved_on": day.isoformat(),
                    }

        current_streak, longest_streak = self._streaks(sorted(sessions_by_day), today)

        planned_total, planned_completed = self._plan_consistency(user_id, start, today)

        return {
            "window": {"from": start.isoformat(), "to": today.isoformat()},
            "sessions_completed": len(sessions),
            "active_days": len(sessions_by_day),
            "sessions_per_week": round(len(sessions) / max((today - start).days / 7, 1), 2),
            "weekly_sessions": [
                {"week_of": week.isoformat(), "sessions": count}
                for week, count in sorted(weekly.items())
            ],
            "total_volume_kg": round(total_volume, 2),
            "personal_records": sorted(prs.values(), key=lambda item: str(item["exercise_name"])),
            "current_streak_days": current_streak,
            "longest_streak_days": longest_streak,
            "planned_sessions": planned_total,
            "planned_completed": planned_completed,
            "planned_completion_rate": (
                round(planned_completed / planned_total, 3) if planned_total else None
            ),
            "source": "derived",
        }

    @staticmethod
    def _streaks(days: list[date], today: date) -> tuple[int, int]:
        """Return (current, longest) run of consecutive days with a session."""
        if not days:
            return 0, 0
        unique = sorted(set(days))
        longest = 1
        run = 1
        for previous, current in zip(unique, unique[1:], strict=False):
            run = run + 1 if (current - previous).days == 1 else 1
            longest = max(longest, run)
        current_streak = 0
        if unique[-1] == today or (today - unique[-1]).days == 1:
            cursor = unique[-1]
            lookback = set(unique)
            while cursor in lookback:
                current_streak += 1
                cursor -= timedelta(days=1)
        return current_streak, longest

    def _plan_consistency(self, user_id: UUID, start: date, end: date) -> tuple[int, int]:
        from app.repositories.planned_session_repository import PlannedSessionRepository

        planned, _ = PlannedSessionRepository(self._db).list_for_user(
            user_id, from_date=start, to_date=end, limit=1000, offset=0
        )
        completed = sum(1 for session in planned if session.status == "completed")
        return len(planned), completed

    def exercise_max_loads(self, user_id: UUID) -> list[dict[str, object]]:
        """Return the heaviest recorded load per exercise.

        This is descriptive aggregation of stored data, not PR detection logic.
        """
        best: dict[str, dict[str, object]] = {}
        for workout_set in self._workouts.list_sets_with_load(user_id):
            weight = workout_set.weight
            if weight is None:
                continue
            current = best.get(workout_set.exercise_name)
            if current is None or Decimal(weight) > Decimal(str(current["weight"])):
                best[workout_set.exercise_name] = {
                    "exercise_name": workout_set.exercise_name,
                    "weight": weight,
                    "weight_unit": (
                        workout_set.weight_unit.value if workout_set.weight_unit else None
                    ),
                }
        return sorted(best.values(), key=lambda item: str(item["exercise_name"]))
