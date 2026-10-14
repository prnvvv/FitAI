"""Persist validated extraction candidates to the authoritative stores.

Each candidate type is routed to the EXISTING service that owns that data:

* completed_workout -> WorkoutService (PostgreSQL ``workout_sessions``)
* planned_workout   -> PlanService (``planned_sessions``)
* progress_record   -> WorkoutService (``measurements``)
* user_preference   -> ProfileService (``user_profiles.preferences``)
* profile_fact      -> ProfileService (``user_profiles.preferences``)

``fitness_goal`` is intentionally NOT persisted here: goals continue through the
existing LangGraph memory-confirmation workflow (``POST /memory/pending`` →
confirm), so we never bypass that policy or create a competing source of truth.

Guarantees:
* A candidate is only reported as ``saved`` after the owning service commits.
* Writes are idempotent: an identical record on the same day yields ``duplicate``
  instead of a second row (safe retries).
* Every candidate is handled independently; one failure never discards the others.
* Provider failures (``ExtractionResult.error``) mean nothing is persisted here;
  the caller still returns its normal assistant response.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.extraction.schemas import ExtractionResult, RecordedOutcome
from app.models.enums import ActivityEventType, MeasurementType
from app.repositories.workout_repository import WorkoutRepository
from app.services.activity_event_service import ActivityEventService
from app.services.plan_service import PlanService
from app.services.profile_service import ProfileService
from app.services.progress_service import ProgressService
from app.services.workout_service import WorkoutService

log = logging.getLogger(__name__)

_MAX_PREF_ITEMS = 50


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


class ExtractionPersister:
    """Persist extraction candidates for one authenticated user."""

    def __init__(self, db: Session, user_id: UUID) -> None:
        self._db = db
        self._user_id = user_id
        self._workouts = WorkoutService(db)
        self._plans = PlanService(db)
        self._progress = ProgressService(db)
        self._profiles = ProfileService(db)
        self._events = ActivityEventService(db)

    def persist(self, result: ExtractionResult, *, now: datetime) -> list[RecordedOutcome]:
        if result.error:
            # Provider failure: nothing was reliably extracted, so nothing is
            # persisted. The caller keeps its normal response.
            return []
        today = now.date()
        outcomes: list[RecordedOutcome] = []
        outcomes += [self._completed(item, today, now) for item in result.completed_workouts]
        outcomes += [self._planned(item, today, now) for item in result.planned_workouts]
        outcomes += [self._progress_record(item, today, now) for item in result.progress_records]
        outcomes += [self._preference(item) for item in result.user_preferences]
        outcomes += [self._profile_fact(item) for item in result.profile_facts]
        return outcomes

    # -- completed workouts ---------------------------------------------------
    def _completed(self, item, today: date, now: datetime) -> RecordedOutcome:
        activity = _norm(item.activity)
        day = item.performed_on or today
        when = _day_datetime(day, now)
        duration = item.duration_minutes
        try:
            existing_id = self._find_completed(day, activity, duration)
            if existing_id is not None:
                return self._outcome(
                    "completed_workout",
                    "duplicate",
                    existing_id,
                    f"{item.activity} {duration or ''}min".strip(),
                )
            sets: list[dict[str, object]] = [{"exercise_name": item.activity}]
            if duration:
                sets[0]["duration_seconds"] = int(duration) * 60
            if item.distance_meters:
                sets[0]["distance_meters"] = Decimal(str(item.distance_meters))
            session = self._workouts.create_session(
                self._user_id,
                when,
                name=item.activity,
                duration_minutes=duration,
                notes=_provenance_note(item.source_text),
                sets=sets,
            )
        except Exception as exc:
            log.warning("completed_workout persist failed: %s", type(exc).__name__)
            return self._outcome(
                "completed_workout", "failed", None, item.activity, detail=type(exc).__name__
            )
        self._log_event(
            ActivityEventType.SESSION_COMPLETED,
            str(session.id),
            when,
            {"activity": item.activity, "duration_minutes": duration},
        )
        return self._outcome(
            "completed_workout",
            "saved",
            str(session.id),
            f"{item.activity}{f', {duration} min' if duration else ''}",
        )

    def _find_completed(self, day: date, activity: str, duration: int | None) -> str | None:
        for session in WorkoutRepository(self._db).list_sessions_with_sets(self._user_id, day, day):
            names = {_norm(s.exercise_name) for s in session.sets}
            name_match = activity in names or _norm(session.name or "") == activity
            if not name_match:
                continue
            if duration is None or session.duration_minutes == duration:
                return str(session.id)
        return None

    # -- planned workouts -----------------------------------------------------
    def _planned(self, item, today: date, now: datetime) -> RecordedOutcome:
        activity = _norm(item.activity)
        day = item.planned_on or (today + timedelta(days=1))
        duration = item.duration_minutes
        try:
            for existing in self._plans.list_sessions(
                self._user_id, from_date=day, to_date=day, limit=100
            )[0]:
                if _norm(existing.title or "") == activity:
                    return self._outcome(
                        "planned_workout", "duplicate", str(existing.id), item.activity
                    )
            exercises: list[dict[str, object]] = [{"exercise_name": item.activity}]
            if duration:
                exercises[0]["duration_seconds"] = int(duration) * 60
            planned = self._plans.create_planned_session(
                self._user_id,
                day,
                title=item.activity,
                day_type="workout",
                notes=_provenance_note(item.source_text),
                exercises=exercises,
            )
        except Exception as exc:
            log.warning("planned_workout persist failed: %s", type(exc).__name__)
            return self._outcome(
                "planned_workout", "failed", None, item.activity, detail=type(exc).__name__
            )
        self._log_event(
            ActivityEventType.SESSION_PLANNED,
            str(planned.id),
            datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            {"activity": item.activity},
        )
        return self._outcome("planned_workout", "saved", str(planned.id), item.activity)

    # -- progress measurements ------------------------------------------------
    def _progress_record(self, item, today: date, now: datetime) -> RecordedOutcome:
        day = item.measured_on or today
        when = _day_datetime(day, now)
        mtype: MeasurementType = item.measurement_type
        try:
            for m in self._progress.measurement_series(
                self._user_id, mtype, from_date=day, to_date=day
            ):
                if m.unit == item.unit and Decimal(str(m.value)) == Decimal(str(item.value)):
                    return self._outcome(
                        "progress_record",
                        "duplicate",
                        str(m.id),
                        f"{mtype.value} {item.value} {item.unit}",
                    )
            record = self._workouts.create_measurement(
                self._user_id,
                mtype,
                Decimal(str(item.value)),
                item.unit,
                when,
                notes=_provenance_note(item.source_text),
            )
        except Exception as exc:
            log.warning("progress_record persist failed: %s", type(exc).__name__)
            return self._outcome(
                "progress_record",
                "failed",
                None,
                f"{mtype.value} {item.value} {item.unit}",
                detail=type(exc).__name__,
            )
        return self._outcome(
            "progress_record", "saved", str(record.id), f"{mtype.value} {item.value} {item.unit}"
        )

    # -- preferences & profile facts (profile.preferences JSON) ----------------
    def _preference(self, item) -> RecordedOutcome:
        return self._append_profile_list("interests", item.preference, "user_preference")

    def _profile_fact(self, item) -> RecordedOutcome:
        return self._append_profile_list("profile_notes", item.text, "profile_fact")

    def _append_profile_list(self, key: str, value: str, kind: str) -> RecordedOutcome:
        text = value.strip()
        try:
            profile = self._profiles.get_or_create(self._user_id)
            prefs = dict(profile.preferences or {})
            items = list(prefs.get(key) or [])
            if text in items:
                return self._outcome(kind, "duplicate", str(profile.id), text)
            items.append(text)
            prefs[key] = items[-_MAX_PREF_ITEMS:]
            saved = self._profiles.update(self._user_id, {"preferences": prefs}, partial=True)
        except Exception as exc:
            log.warning("%s persist failed: %s", kind, type(exc).__name__)
            return self._outcome(kind, "failed", None, text, detail=type(exc).__name__)
        return self._outcome(kind, "saved", str(saved.id), text)

    # -- helpers --------------------------------------------------------------
    def _log_event(self, event_type, entity_id, occurred_at, payload) -> None:
        # Best-effort; the primary write has already committed.
        with _suppress():
            self._events.record(
                self._user_id,
                event_type,
                entity_type=entity_type_name(event_type),
                entity_id=entity_id,
                occurred_at=occurred_at,
                source="chat_extraction",
                payload=payload,
            )

    @staticmethod
    def _outcome(
        kind: str, status: str, record_id: str | None, summary: str, detail: str | None = None
    ) -> RecordedOutcome:
        return RecordedOutcome(
            kind=kind, status=status, record_id=record_id, summary=summary, detail=detail
        )


def persist_extraction(
    db: Session, user_id: UUID, result: ExtractionResult, *, now: datetime | None = None
) -> list[RecordedOutcome]:
    """Convenience wrapper used by the chat flow."""
    return ExtractionPersister(db, user_id).persist(result, now=now or datetime.now(timezone.utc))


@contextlib.contextmanager
def _suppress():
    try:
        yield
    except Exception:  # pragma: no cover - event logging is best-effort
        log.debug("activity event logging failed", exc_info=True)


def _day_datetime(day: date, now: datetime) -> datetime:
    """Return an aware UTC datetime for `day`; clamp so it is never in the future."""
    now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if day >= now_utc.date():
        return now_utc
    midday = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    return min(midday, now_utc)


def _provenance_note(source_text: str) -> str:
    text = (source_text or "").strip()
    if not text:
        return "Logged from chat"
    return f"Logged from chat: {text[:200]}"


def entity_type_name(event_type: ActivityEventType) -> str:
    if event_type is ActivityEventType.SESSION_COMPLETED:
        return "workout_session"
    if event_type is ActivityEventType.SESSION_PLANNED:
        return "planned_session"
    return "record"
