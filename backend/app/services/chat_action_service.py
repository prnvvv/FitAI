"""Propose and resolve user-confirmable chat actions.

The agent proposes an action (log a workout, or personalise an answer with the
user's stored height/weight) without performing it. This service creates the
pending record and, once the user confirms, executes the action and appends the
resulting assistant message to the conversation. Nothing is executed until the
user confirms.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.llm.prompts import PERSONALIZED_MEASUREMENTS, PERSONALIZED_MEASUREMENTS_SYSTEM
from app.models.enums import ActivityEventType, PendingActionStatus, PendingActionType
from app.models.pending_action import PendingChatAction
from app.repositories.pending_action_repository import PendingActionRepository
from app.services.activity_event_service import ActivityEventService
from app.services.workout_service import WorkoutService

log = logging.getLogger(__name__)

Completer = Callable[..., str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatActionService:
    """Coordinates pending chat actions and the persistence they touch."""

    def __init__(self, db: Session, *, completer: Completer | None = None) -> None:
        self._db = db
        self._actions = PendingActionRepository(db)
        self._completer = completer

    # ------------------------------------------------------------------
    # Proposal creation (called through the agent's ActionWriter adapter)
    # ------------------------------------------------------------------
    def propose(
        self,
        user_id: UUID,
        conversation_id: UUID,
        action_type: PendingActionType,
        payload: dict[str, object],
        summary: str,
    ) -> PendingChatAction:
        """Persist a pending action without executing it."""
        action = self._actions.create(user_id, conversation_id, action_type, payload, summary)
        self._commit()
        self._db.refresh(action)
        return action

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def confirm(self, user_id: UUID, action_id: UUID) -> tuple[UUID, str, dict[str, object]]:
        """Execute a pending action and return (conversation_id, content, metadata)."""
        action = self._load_pending(user_id, action_id)
        try:
            content, metadata = self._execute(action, user_id)
        except AppError:
            raise
        except Exception as exc:  # never report success on failure
            log.warning("chat action execution failed: %s", exc, exc_info=True)
            raise AppError("The action could not be completed.") from exc

        action.status = PendingActionStatus.CONFIRMED
        action.resolved_at = _utcnow()
        self._commit()
        return action.conversation_id, content, metadata

    def reject(self, user_id: UUID, action_id: UUID) -> tuple[UUID, str, dict[str, object]]:
        """Reject a pending action without executing it."""
        action = self._load_pending(user_id, action_id)
        action.status = PendingActionStatus.REJECTED
        action.resolved_at = _utcnow()
        self._commit()
        content = self._rejection_message(action.action_type)
        return action.conversation_id, content, {}

    def _load_pending(self, user_id: UUID, action_id: UUID) -> PendingChatAction:
        action = self._actions.get_for_update(action_id, user_id)
        if action is None:
            raise NotFoundError("Pending action not found.")
        if action.status is not PendingActionStatus.PENDING:
            raise ConflictError(
                "This action has already been resolved.",
                details={"status": action.status.value},
            )
        return action

    # ------------------------------------------------------------------
    # Executors
    # ------------------------------------------------------------------
    def _execute(self, action: PendingChatAction, user_id: UUID) -> tuple[str, dict[str, object]]:
        if action.action_type is PendingActionType.LOG_WORKOUT:
            return self._execute_log_workout(action, user_id)
        if action.action_type is PendingActionType.USE_MEASUREMENTS:
            return self._execute_use_measurements(action)
        raise AppError("Unsupported action type.")

    def _execute_log_workout(
        self, action: PendingChatAction, user_id: UUID
    ) -> tuple[str, dict[str, object]]:
        payload = action.payload
        activity = str(payload.get("activity") or "Workout")[:255]
        performed_on = date.fromisoformat(str(payload["performed_on"])[:10])
        performed_at = datetime.combine(performed_on, time(hour=10), tzinfo=timezone.utc)
        duration = self._as_int(payload.get("duration_minutes"))

        sets: list[dict[str, object]] = []
        if duration and duration > 0:
            sets.append({"exercise_name": activity, "duration_seconds": duration * 60})

        session = WorkoutService(self._db).create_session(
            user_id,
            performed_at,
            name=activity,
            duration_minutes=duration,
            notes=self._as_text(payload.get("notes")),
            sets=sets,
        )
        ActivityEventService(self._db).record(
            user_id,
            ActivityEventType.SESSION_COMPLETED,
            entity_type="workout_session",
            entity_id=str(session.id),
            occurred_at=performed_at,
            source="agent",
            payload={"name": activity, "duration_minutes": duration},
        )
        self._commit()

        suffix = f" ({duration} min)" if duration else ""
        content = (
            f"Done — I've added **{activity}**{suffix} to your calendar for "
            f"{performed_on.isoformat()}."
        )
        metadata: dict[str, object] = {
            "tool_events": [{"tool": "log_workout", "status": "applied", "summary": action.summary}]
        }
        return content, metadata

    def _execute_use_measurements(self, action: PendingChatAction) -> tuple[str, dict[str, object]]:
        payload = action.payload
        question = str(payload.get("question") or "")
        parts: list[str] = []
        height = payload.get("height_cm")
        weight = payload.get("weight_kg")
        if isinstance(height, int | float) and not isinstance(height, bool):
            parts.append(f"height: {height:g} cm")
        if isinstance(weight, int | float) and not isinstance(weight, bool):
            parts.append(f"weight: {weight:g} kg")
        measurements = ", ".join(parts) or "(none stored)"

        prompt = PERSONALIZED_MEASUREMENTS.format(measurements=measurements, question=question)
        try:
            answer = self._get_completer()(PERSONALIZED_MEASUREMENTS_SYSTEM, prompt).strip()
        except Exception as exc:
            log.warning("personalised answer generation failed: %s", exc)
            answer = ""
        if not answer:
            answer = (
                "Sorry, I couldn't put together a personalised answer right now. "
                "Please try again."
            )
        metadata: dict[str, object] = {
            "tool_events": [{"tool": "use_measurements", "status": "applied"}]
        }
        return answer, metadata

    def _get_completer(self) -> Completer:
        if self._completer is None:
            from app.llm.client import GroqClient

            self._completer = GroqClient(api_key=settings.groq_api_key, model=settings.groq_model)
        return self._completer

    @staticmethod
    def _rejection_message(action_type: PendingActionType) -> str:
        if action_type is PendingActionType.LOG_WORKOUT:
            return "No problem — I didn't add anything to your calendar."
        return "No problem. Tell me your current height and weight and I'll use those instead."

    @staticmethod
    def _as_int(value: object) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, Decimal):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return None

    @staticmethod
    def _as_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The action could not be saved.") from exc
