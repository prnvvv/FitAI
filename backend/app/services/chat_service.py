"""Chat orchestration: run one turn through the agent graph and persist messages."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import (
    AgentDeps,
    FitnessReader,
    MemoryReader,
    ProfileReader,
    build_graph,
    run_turn,
)
from app.agent.multi import run_multi_turn
from app.core.config import settings
from app.llm.client import GroqClient
from app.memory.change_detector import DetectedChange, MemoryEntry
from app.memory.confirmation import Decision, MemoryWriter
from app.memory.history import HistoryRecord
from app.models.enums import MemoryChangeType, MemoryKey, MessageRole
from app.models.user import User
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorStore
from app.services.conversation_service import ConversationService
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.progress_service import ProgressService
from app.services.workout_service import WorkoutService
from app.tools.nearby_gyms import nearby_gyms
from app.tools.web_search import web_search


class _ProfileReaderAdapter(ProfileReader):
    """Adapt ProfileService to the agent's ProfileReader protocol."""

    def __init__(self, db: Session, user_id: UUID) -> None:
        self._service = ProfileService(db)
        self._user_id = user_id

    def get_profile(self, user_id: str) -> Mapping[str, object] | None:
        profile = self._service.get(self._user_id)
        if profile is None:
            return None
        prefs = profile.preferences or {}
        data: dict[str, object] = {
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "activity_level": profile.activity_level,
            "goal": profile.goal,
            "dietary_preferences": profile.dietary_preferences or [],
            "dietary_restrictions": profile.dietary_restrictions or [],
            "display_name": prefs.get("display_name") if isinstance(prefs, dict) else None,
            "about_you": prefs.get("about_you") if isinstance(prefs, dict) else None,
            "assistant_should_know": prefs.get("assistant_should_know")
            if isinstance(prefs, dict)
            else None,
            "preferred_tone": prefs.get("preferred_tone") if isinstance(prefs, dict) else None,
            "units": prefs.get("units") if isinstance(prefs, dict) else None,
            "timezone": profile.location_timezone,
            "location": profile.location_label,
        }
        return {k: v for k, v in data.items() if v is not None and v != []}


class _MemoryReaderAdapter(MemoryReader):
    """Adapt MemoryService to the agent's MemoryReader protocol."""

    def __init__(self, db: Session, user_id: UUID) -> None:
        self._service = MemoryService(db)
        self._user_id = user_id

    def get_current_memory(self, user_id: str) -> Mapping[str, MemoryEntry]:
        items = self._service.list_current(UUID(user_id))
        return {
            item.key: MemoryEntry(
                key=item.key,
                value=self._scalar(item.value),
                updated_at=item.updated_at,
            )
            for item in items
        }

    @staticmethod
    def _scalar(value: object) -> float | str | list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, int | float):
            return float(value)
        return str(value)


class _MemoryWriterAdapter(MemoryWriter):
    """Adapt MemoryService to the agent's MemoryWriter protocol."""

    def __init__(self, db: Session, user_id: UUID) -> None:
        self._service = MemoryService(db)
        self._user_id = user_id
        # (key, value) pairs whose current-value change already wrote a history
        # row via the service. Consumed by record_history so a single fact is
        # never historised twice in one turn.
        self._already_historised: set[tuple[str, object]] = set()

    def apply_update(self, user_id: str, change: DetectedChange) -> bool:
        try:
            service = self._service
            uid = UUID(user_id)
            try:
                key = MemoryKey(change.fact.key)
            except ValueError:
                # Not part of the provisional memory taxonomy: cannot persist.
                return False
            for item in service.list_current(uid):
                if item.key == key:
                    service.correct(item.id, uid, change.fact.value)
                    self._already_historised.add((change.fact.key, change.fact.value))
                    return True
            service.create(
                uid,
                key,
                change.fact.value,
                confidence=Decimal(str(change.fact.confidence)),
                source="agent",
                effective_at=change.fact.timestamp,
            )
            self._already_historised.add((change.fact.key, change.fact.value))
            return True
        except Exception:
            return False

    def create_pending(self, user_id: str, decision: Decision) -> str | None:
        """Persist an uncertain proposal so the user can confirm or reject it."""
        try:
            try:
                key = MemoryKey(decision.change.fact.key)
            except ValueError:
                return None
            proposal = self._service.create_proposal(
                UUID(user_id),
                key,
                decision.change.fact.value,
                confidence=Decimal(str(decision.change.fact.confidence)),
                source="agent",
                reason=decision.reason,
            )
            return str(proposal.id)
        except Exception:
            return None

    def record_history(self, user_id: str, record: HistoryRecord) -> bool:
        """Persist a dated historical event as an immutable history row.

        For an AUTO_APPLY turn, apply_update already wrote the history row via
        the memory service, so the immediate follow-up record for the same
        (key, value) is treated as already persisted (no duplicate).
        """
        marker = (record.key, record.value)
        if marker in self._already_historised:
            self._already_historised.discard(marker)
            return True
        try:
            key = MemoryKey(record.key)
        except ValueError:
            return False
        try:
            effective_at = (
                datetime(
                    record.effective_date.year,
                    record.effective_date.month,
                    record.effective_date.day,
                    tzinfo=timezone.utc,
                )
                if record.effective_date is not None
                else None
            )
            self._service.record_history(
                UUID(user_id),
                key,
                change_type=MemoryChangeType.UPDATE,
                previous_value=None,
                new_value=record.value,
                confidence=Decimal(str(record.confidence)),
                source="agent",
                effective_at=effective_at,
            )
            return True
        except Exception:
            return False


class _FitnessReaderAdapter(FitnessReader):
    """Expose the user's real workout plans, completed sessions and progress
    measurements to the agent, using the authoritative services. Everything is
    scoped to the authenticated user; nothing is fabricated. A failure is
    reported as an error dict so chat never breaks and the model can be honest.
    """

    WINDOW_DAYS = 120

    def __init__(self, db: Session, user_id: UUID) -> None:
        self._db = db
        self._user_id = user_id

    def get_fitness_context(self, user_id: str) -> dict[str, Any]:
        try:
            return self._build(UUID(user_id))
        except Exception as exc:  # never break chat; surface an honest error
            return {"error": f"records unavailable ({type(exc).__name__})"}

    def _build(self, uid: UUID) -> dict[str, Any]:
        today = date.today()
        since = today - timedelta(days=self.WINDOW_DAYS)
        workouts = WorkoutService(self._db)
        progress = ProgressService(self._db)

        sessions, _ = workouts.list_sessions(uid, limit=10, offset=0)
        recent_sessions: list[dict[str, Any]] = []
        for session in sessions[:10]:
            sets = list(getattr(session, "sets", []) or [])
            exercises: list[str] = []
            top: dict[str, Any] | None = None
            for entry in sets:
                name = entry.exercise_name
                if name and name not in exercises:
                    exercises.append(name)
                if entry.weight is not None:
                    load = float(entry.weight)
                    if top is None or load > float(top["weight"]):
                        top = {
                            "exercise": name,
                            "weight": round(load, 2),
                            "unit": entry.weight_unit.value if entry.weight_unit else "kg",
                            "reps": int(entry.reps or 0),
                        }
            recent_sessions.append(
                {
                    "date": session.performed_at.date().isoformat(),
                    "name": session.name,
                    "duration_min": session.duration_minutes,
                    "sets": len(sets),
                    "exercises": exercises[:12],
                    "top": top,
                }
            )

        metrics = progress.derived_metrics(uid, from_date=since, to_date=today)
        records = []
        for pr in (metrics.get("personal_records") or [])[:8]:
            weight = pr.get("weight")
            records.append(
                {
                    "exercise": pr.get("exercise_name"),
                    "weight": round(float(weight), 2) if weight is not None else None,
                    "unit": pr.get("weight_unit") or "kg",
                    "on": pr.get("achieved_on"),
                }
            )
        totals = {
            "sessions_completed": metrics.get("sessions_completed"),
            "active_days": metrics.get("active_days"),
            "total_volume_kg": metrics.get("total_volume_kg"),
            "sessions_per_week": metrics.get("sessions_per_week"),
            "current_streak_days": metrics.get("current_streak_days"),
            "longest_streak_days": metrics.get("longest_streak_days"),
            "planned_sessions": metrics.get("planned_sessions"),
            "planned_completed": metrics.get("planned_completed"),
            "planned_completion_rate": metrics.get("planned_completion_rate"),
        }

        recent_weights = [m for m in progress.weight_series(uid) if m.measured_at.date() >= since]
        return {
            "window_days": self.WINDOW_DAYS,
            "totals": totals,
            "weight": self._weight_block(recent_weights),
            "recent_sessions": recent_sessions,
            "personal_records": records,
        }

    @staticmethod
    def _weight_block(measurements: list[Any]) -> dict[str, Any]:
        if not measurements:
            return {"points": 0, "unit": "kg"}

        def to_kg(measurement: Any) -> float:
            value = float(measurement.value)
            if measurement.unit == "lb":
                return value * 0.45359237
            return value

        first, last = measurements[0], measurements[-1]
        return {
            "points": len(measurements),
            "unit": "kg",
            "first": {
                "date": first.measured_at.date().isoformat(),
                "value": round(to_kg(first), 2),
            },
            "latest": {"date": last.measured_at.date().isoformat(), "value": round(to_kg(last), 2)},
            "change": round(to_kg(last) - to_kg(first), 2),
        }


def _title_from_message(message: str) -> str:
    return message.strip().split("\n")[0][:50] or "New chat"


class ChatService:
    """Run one chat turn and persist the conversation."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._conversations = ConversationService(db)
        self._memory = MemoryService(db)

    def chat(self, user: User, message: str, conversation_id: UUID | None = None) -> dict[str, Any]:
        """Run a single turn and return the assistant response.

        Creates a new conversation if `conversation_id` is not provided.
        """
        user_id = user.id
        if conversation_id is None:
            conversation = self._conversations.create(user_id, _title_from_message(message))
        else:
            conversation = self._conversations.get(user_id, conversation_id)

        conversation_id = conversation.id
        self._conversations.add_message(user_id, conversation_id, MessageRole.USER, message)

        try:
            retriever = Retriever(VectorStore(persist_dir=settings.chromadb_persist_dir))
        except Exception:
            retriever = None

        graph_deps = AgentDeps(
            llm=self._build_llm(),
            memory_reader=_MemoryReaderAdapter(self._db, user_id),
            memory_writer=_MemoryWriterAdapter(self._db, user_id),
            profile_reader=_ProfileReaderAdapter(self._db, user_id),
            retriever=retriever,
            fitness_reader=_FitnessReaderAdapter(self._db, user_id),
            tools={"web_search": web_search, "nearby_gyms": nearby_gyms},
            db_session=self._db,
        )

        messages = self._conversations.list_recent_messages(user_id, conversation_id, limit=20)
        context = [{"role": msg.role.value, "content": msg.content} for msg in messages]

        if settings.agent_multi_agent:
            turn = run_multi_turn(graph_deps, str(user_id), message, context)
        else:
            graph = build_graph(graph_deps)
            turn = run_turn(graph, str(user_id), message, context)
        response = turn["response"]

        metadata = {
            "sources": turn.get("sources", []),
            "actions": turn.get("actions", []),
            "tool_events": turn.get("tool_results", []),
        }
        self._conversations.add_message(
            user_id, conversation_id, MessageRole.ASSISTANT, response, metadata=metadata
        )

        return {
            "conversation_id": conversation_id,
            "response": response,
            "title": conversation.title,
            "sources": metadata["sources"],
            "actions": metadata["actions"],
            "tool_events": metadata["tool_events"],
        }

    @staticmethod
    def _build_llm() -> GroqClient:
        """Return a Groq-backed completer configured from project settings."""
        return GroqClient(api_key=settings.groq_api_key, model=settings.groq_model)
