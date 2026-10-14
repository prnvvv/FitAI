"""Detect user-confirmable actions in a chat message.

Two actions are supported:

* ``LOG_WORKOUT`` — the user reports a session ("I did treadmill for 2h today").
  A structured proposal is extracted with the LLM and proposed for confirmation.
* ``USE_MEASUREMENTS`` — the user asks a question that depends on their body
  metrics and we already hold a stored height and/or weight. The stored values
  are proposed for confirmation before a personalised answer is produced.

Detection is cheap and heuristic-first so the extra LLM call only happens when
a message plausibly reports a workout.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field, ValidationError

from app.llm.prompts import WORKOUT_LOG_EXTRACTION
from app.memory.change_detector import MemoryEntry
from app.memory.extractor import TextCompleter
from app.models.enums import PendingActionType

log = logging.getLogger(__name__)

_WORKOUT_LOG = re.compile(
    r"\b(i (?:did|did a|went for|went on|went to|ran|walked|jogged|cycled|swam|lifted|"
    r"completed|finished|did some|hit|crushed)|treadmill|elliptical|rowing|stair ?master|"
    r"for \d+\s*(?:min|mins|minutes|hour|hours|hr|hrs|h))\b",
    re.I,
)

_BODY_STATS = re.compile(r"\b(height|weight|bmi|bmr|tdee|body fat)\b", re.I)

_QUESTION = re.compile(
    r"\?|^\s*(how|what|why|when|which|should|can|could|is|are|do|does|suggest|recommend|"
    r"give me|show me|according)\b",
    re.I,
)


class WorkoutLogProposal(BaseModel):
    """A structured, extracted workout the user reported."""

    activity: str = Field(min_length=1, max_length=120)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    performed_on: date
    notes: str | None = Field(default=None, max_length=500)


class ActionProposal(BaseModel):
    """An action the agent wants the user to confirm before it runs."""

    action_type: PendingActionType
    payload: dict[str, object]
    summary: str


def looks_like_workout_log(message: str) -> bool:
    """Return True when the message plausibly reports a completed activity."""
    return bool(_WORKOUT_LOG.search(message))


def looks_like_body_stats_query(message: str) -> bool:
    """Return True when the message asks something that depends on body metrics."""
    if not _BODY_STATS.search(message):
        return False
    return bool(_QUESTION.search(message)) or "according to" in message.lower()


def _parse_json(raw: str) -> object:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(text)


def extract_workout_log(
    message: str, llm: TextCompleter, today: date | None = None
) -> WorkoutLogProposal | None:
    """Ask the LLM to structure a reported workout. Never raises."""
    today = today or datetime.now(timezone.utc).date()
    try:
        raw = llm(
            WORKOUT_LOG_EXTRACTION.replace("{today}", today.isoformat()),
            message[:2000],
            json_mode=True,
        )
        data = _parse_json(raw)
    except Exception as exc:
        log.warning("workout log extraction failed: %s", exc)
        return None
    if not isinstance(data, dict) or not data.get("is_workout"):
        return None
    try:
        return WorkoutLogProposal.model_validate(
            {
                "activity": data.get("activity") or "Workout",
                "duration_minutes": data.get("duration_minutes"),
                "performed_on": data.get("performed_on") or today.isoformat(),
                "notes": data.get("notes"),
            }
        )
    except (ValidationError, ValueError) as exc:
        log.warning("workout log proposal rejected: %s", exc)
        return None


def _stored_measurements(
    memory: Mapping[str, MemoryEntry], profile: Mapping[str, object] | None
) -> tuple[float | None, float | None]:
    """Return the stored (height_cm, weight_kg) preferring memory over profile."""
    height: float | None = None
    weight: float | None = None
    for key in ("height", "weight"):
        entry = memory.get(key)
        if entry is None or isinstance(entry.value, str | list):
            continue
        if key == "height":
            height = float(entry.value)
        else:
            weight = float(entry.value)
    if profile:
        if height is None and isinstance(profile.get("height_cm"), int | float):
            height = float(profile["height_cm"])  # type: ignore[arg-type]
        if weight is None and isinstance(profile.get("weight_kg"), int | float):
            weight = float(profile["weight_kg"])  # type: ignore[arg-type]
    return height, weight


def _workout_summary(proposal: WorkoutLogProposal) -> str:
    when = proposal.performed_on.isoformat()
    if proposal.duration_minutes:
        return f"Log {proposal.activity} ({proposal.duration_minutes} min) on {when}"
    return f"Log {proposal.activity} on {when}"


def _measurements_summary(height: float | None, weight: float | None) -> str:
    parts = []
    if height is not None:
        parts.append(f"{height:g} cm")
    if weight is not None:
        parts.append(f"{weight:g} kg")
    return "Use your saved height/weight (" + ", ".join(parts) + ") for this answer"


def build_action_proposals(
    message: str,
    memory: Mapping[str, MemoryEntry],
    profile: Mapping[str, object] | None,
    llm: TextCompleter,
    now: datetime | None = None,
) -> list[ActionProposal]:
    """Return the confirmable actions implied by ``message`` (possibly none)."""
    now = now or datetime.now(timezone.utc)
    proposals: list[ActionProposal] = []

    if looks_like_workout_log(message):
        workout = extract_workout_log(message, llm, now.date())
        if workout is not None:
            proposals.append(
                ActionProposal(
                    action_type=PendingActionType.LOG_WORKOUT,
                    payload={
                        "activity": workout.activity,
                        "duration_minutes": workout.duration_minutes,
                        "performed_on": workout.performed_on.isoformat(),
                        "notes": workout.notes,
                    },
                    summary=_workout_summary(workout),
                )
            )

    if looks_like_body_stats_query(message):
        height, weight = _stored_measurements(memory, profile)
        if height is not None or weight is not None:
            proposals.append(
                ActionProposal(
                    action_type=PendingActionType.USE_MEASUREMENTS,
                    payload={
                        "question": message,
                        "height_cm": height,
                        "weight_kg": weight,
                    },
                    summary=_measurements_summary(height, weight),
                )
            )

    return proposals
