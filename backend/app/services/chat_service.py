"""Chat orchestration: run one turn through the agent graph and persist messages."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import (
    AgentDeps,
    ContinuityReader,
    FitnessReader,
    MemoryReader,
    ProfileReader,
    build_graph,
    run_turn,
)
from app.agent.multi import run_multi_turn
from app.core.config import settings
from app.extraction.extractor import GroqActivityExtractor, RecordExtractor
from app.extraction.persistence import persist_extraction
from app.extraction.schemas import RecordedOutcome
from app.guardrails import GuardDecision, IntentClassifier, guarded_run
from app.llm.client import GroqClient
from app.memory.change_detector import DetectedChange, MemoryEntry
from app.memory.confirmation import Decision, MemoryWriter
from app.memory.continuity import ContinuityContext
from app.memory.extractor import TextCompleter
from app.memory.history import HistoryRecord
from app.memory.summarizer import build_summary
from app.models.enums import MemoryChangeType, MemoryKey, MessageRole
from app.models.user import User
from app.rag.continuity_store import KIND_MEMORY, KIND_SUMMARY, ContinuityHit, ContinuityStore
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorStore
from app.repositories.conversation_summary_repository import ConversationSummaryRepository
from app.safety import run_safety_rules
from app.services.conversation_service import ConversationService
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.progress_service import ProgressService
from app.services.workout_service import WorkoutService
from app.tools.nearby_gyms import nearby_gyms
from app.tools.web_search import web_search

log = logging.getLogger(__name__)


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
            "interests": prefs.get("interests") if isinstance(prefs, dict) else None,
            "profile_notes": prefs.get("profile_notes") if isinstance(prefs, dict) else None,
            "timezone": profile.location_timezone,
            "location": profile.location_label,
        }
        return {k: v for k, v in data.items() if v is not None and v != []}


class _MemoryReaderAdapter(MemoryReader):
    """Adapt MemoryService to the agent's MemoryReader protocol.

    When the user has disabled memory (server-enforced toggle), this returns no
    facts, so stored memory is neither pinned nor used in answers.
    """

    def __init__(self, db: Session, user_id: UUID, *, use_memory: bool = True) -> None:
        self._service = MemoryService(db)
        self._user_id = user_id
        self._use_memory = use_memory

    def get_current_memory(self, user_id: str) -> Mapping[str, MemoryEntry]:
        if not self._use_memory:
            return {}
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


class _ContinuityReaderAdapter(ContinuityReader):
    """Owner-scoped cross-chat recall with server-side toggle enforcement.

    Recalls semantically relevant saved facts (``kind="memory"``) and past-chat
    summaries (``kind="summary"``), each respecting the user's toggles. Every
    store query is scoped to ``owner_id``. Any store failure degrades to "no
    recall" rather than breaking the turn.
    """

    def __init__(
        self,
        store: ContinuityStore,
        *,
        use_memory: bool = True,
        use_past_chats: bool = True,
        k: int = 4,
    ) -> None:
        self._store = store
        self._use_memory = use_memory
        self._use_past_chats = use_past_chats
        self._k = k

    def recall(self, user_id: str, query: str) -> ContinuityContext:
        if not user_id or not query.strip():
            return ContinuityContext()
        memories: list[str] = []
        past_chats: list[str] = []
        try:
            if self._use_memory:
                memories = [
                    hit.text
                    for hit in self._store.search(user_id, query, k=self._k, kind=KIND_MEMORY)
                ]
            if self._use_past_chats:
                past_chats = [
                    self._label(hit)
                    for hit in self._store.search(user_id, query, k=self._k, kind=KIND_SUMMARY)
                ]
        except Exception:
            log.warning("continuity recall failed", exc_info=True)
            return ContinuityContext()
        return ContinuityContext(memories=memories, past_chats=past_chats)

    @staticmethod
    def _label(hit: ContinuityHit) -> str:
        title = str(hit.metadata.get("title") or "Earlier chat")
        return f"{title}: {hit.text}"


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
        self._summaries = ConversationSummaryRepository(db)
        # Overridable extraction provider. Built lazily from settings so a missing
        # extraction key leaves the default (None) and chat proceeds unchanged.
        self._extractor: RecordExtractor | None = None

    def chat(self, user: User, message: str, conversation_id: UUID | None = None) -> dict[str, Any]:
        """Run a single turn and return the assistant response.

        Creates a new conversation if `conversation_id` is not provided.
        """
        user_id = user.id

        # Guardrails gate: deterministic rules + optional LLM intent classifier.
        # This single choke point runs BEFORE any LLM, tool call, memory
        # extraction, or persistence. A refusal never reaches the model or tools;
        # blocked messages are stored with blocked=true and replaced by a neutral
        # placeholder in future context.
        guard = self._run_guard(message, user_id)

        if guard.blocked and settings.guardrails_mode == "enforce":
            response = guard.response or "I can't help with that request."
            if conversation_id is None:
                conversation = self._conversations.create(user_id, _title_from_message(message))
            else:
                conversation = self._conversations.get(user_id, conversation_id)
            conversation_id = conversation.id
            self._conversations.add_message(
                user_id,
                conversation_id,
                MessageRole.USER,
                "[Blocked by safety filter]",
                metadata={
                    "blocked": True,
                    "original_message": message,
                    "category": guard.category,
                },
            )
            self._conversations.add_message(
                user_id, conversation_id, MessageRole.ASSISTANT, response
            )
            return {
                "conversation_id": conversation_id,
                "response": response,
                "title": conversation.title,
                "sources": [],
                "actions": [],
                "tool_events": [],
            }
        if guard.blocked:
            # monitor mode: log-only, allow through to the model
            log.warning("guardrails_monitor_mode_allow category=%s", guard.category)

        is_new_conversation = conversation_id is None
        if conversation_id is None:
            conversation = self._conversations.create(user_id, _title_from_message(message))
        else:
            conversation = self._conversations.get(user_id, conversation_id)

        conversation_id = conversation.id
        self._conversations.add_message(user_id, conversation_id, MessageRole.USER, message)

        # Cross-chat continuity: when a new chat starts, roll the previous
        # conversation into a summary (best-effort) so it can be recalled later.
        if is_new_conversation:
            self._flush_previous_conversation(user_id, conversation_id)

        # Dedicated structured extraction -> authoritative persistence. This runs
        # BEFORE the assistant reply so a truthful confirmation can be appended,
        # and only AFTER the database confirms each write. It must never break
        # the chat response, so every failure is contained here.
        extraction_events, confirmations = self._extract_and_persist(user_id, message)

        # User toggles are enforced server-side: they gate pinned memory and both
        # recall layers regardless of what the client sends.
        use_memory, use_past_chats = self._toggles(user_id)

        try:
            store = VectorStore(persist_dir=settings.chromadb_persist_dir)
        except Exception:
            store = None
        retriever = Retriever(store) if store is not None else None
        continuity_store = (
            ContinuityStore(store) if store is not None and settings.continuity_enabled else None
        )
        if continuity_store is not None:
            self._index_memories(user_id, continuity_store)
        continuity = (
            _ContinuityReaderAdapter(
                continuity_store,
                use_memory=use_memory,
                use_past_chats=use_past_chats,
                k=settings.continuity_recall_k,
            )
            if continuity_store is not None
            else None
        )

        graph_deps = AgentDeps(
            llm=self._build_llm(),
            memory_reader=_MemoryReaderAdapter(self._db, user_id, use_memory=use_memory),
            memory_writer=_MemoryWriterAdapter(self._db, user_id),
            profile_reader=_ProfileReaderAdapter(self._db, user_id),
            retriever=retriever,
            continuity=continuity,
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
            turn = run_turn(graph, str(user_id), message, context, wants_tool=guard.wants_tool)
        response = turn["response"]

        # Only append a confirmation AFTER the database writes succeeded. This is
        # deterministic (not model-generated) so it can never claim a false save.
        if confirmations:
            response = (response.rstrip() + "\n\n" + "\n".join(confirmations)).strip()

        metadata = {
            "sources": turn.get("sources", []),
            "actions": turn.get("actions", []),
            "tool_events": extraction_events + list(turn.get("tool_results", [])),
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

    def _run_guard(self, message: str, user_id: UUID) -> GuardDecision:
        """Gate one message via the single guardrails choke point.

        Deterministic rules always run. The LLM classifier refines the decision
        when enabled and configured; its failure degrades to the deterministic
        allow path, so a classifier outage never breaks chat. ``run_turn`` only
        receives a decision for messages that pass this gate.
        """
        if not settings.guardrails_enabled or settings.guardrails_mode == "disabled":
            return GuardDecision(
                blocked=False, source="deterministic", reason="guardrails disabled"
            )
        return guarded_run(message, str(user_id), self._build_classifier())

    def _build_classifier(self) -> IntentClassifier | None:
        """Return the LLM intent classifier, or None when disabled/unconfigured.

        Built from project settings so a missing key (or the disabled flag) leaves
        None and the gate falls back to deterministic-only behaviour. The
        module-level ``GroqClient`` symbol is referenced so tests can patch it.
        """
        if not settings.guard_classifier_enabled:
            return None
        try:
            completer = GroqClient(
                api_key=settings.groq_api_key,
                model=settings.guard_model or settings.groq_model,
                timeout=settings.guard_timeout_s,
                max_tokens=settings.guard_max_tokens,
            )
        except Exception:
            log.warning("guard classifier could not be initialised", exc_info=True)
            return None
        return IntentClassifier(completer, model=settings.guard_model or settings.groq_model)

    def _toggles(self, user_id: UUID) -> tuple[bool, bool]:
        """Return (use_memory, reference_past_chats) from the user's profile.

        Defaults come from settings so the toggles are enforced server-side even
        when a client never sends them.
        """
        profile = ProfileService(self._db).get(user_id)
        prefs = (
            profile.preferences
            if profile is not None and isinstance(profile.preferences, dict)
            else {}
        )
        use_memory = bool(prefs.get("use_memory", settings.memory_recall_default))
        use_past = bool(prefs.get("reference_past_chats", settings.past_chat_recall_default))
        return use_memory, use_past

    def _build_summary_llm(self) -> TextCompleter | None:
        """Return the conversation-summary completer, or None when unavailable."""
        if not settings.continuity_enabled:
            return None
        try:
            return GroqClient(
                api_key=settings.groq_api_key,
                model=settings.summary_model or settings.groq_model,
            )
        except Exception:
            log.warning("summary model could not be initialised", exc_info=True)
            return None

    def _index_memories(self, user_id: UUID, store: ContinuityStore) -> None:
        """Make the user's memory vectors reflect current memory (best-effort)."""
        if not settings.continuity_enabled:
            return
        try:
            items = self._memory.list_current(user_id)
            mapping = {item.key.value: self._memory_text(item) for item in items}
            store.sync_memories(str(user_id), mapping)
        except Exception:
            log.warning("memory vector sync failed", exc_info=True)

    @staticmethod
    def _memory_text(item: Any) -> str:
        value = item.value
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        return f"{item.key.value}: {value}"

    def _flush_previous_conversation(self, user_id: UUID, new_conversation_id: UUID) -> None:
        """Summarise the user's most recent earlier conversation (best-effort)."""
        if not settings.continuity_enabled:
            return
        try:
            recent, _ = self._conversations.list_conversations(user_id, limit=2, offset=0)
        except Exception:
            log.warning("previous-conversation lookup failed", exc_info=True)
            return
        target = next((c for c in recent if c.id != new_conversation_id), None)
        if target is None:
            return
        self._summarize_conversation(user_id, target.id, target.title)

    def _summarize_conversation(
        self, user_id: UUID, conversation_id: UUID, title: str | None
    ) -> None:
        """Summarise one conversation, persist the row, and index it. Contained."""
        llm = self._build_summary_llm()
        if llm is None:
            return
        try:
            rows = self._conversations.list_recent_messages(user_id, conversation_id, limit=40)
        except Exception:
            log.warning("summary message lookup failed", exc_info=True)
            return
        if not rows:
            return
        try:
            existing = self._summaries.get_for_conversation(conversation_id, user_id)
            if existing is not None and existing.message_count == len(rows):
                return
        except Exception:
            log.warning("summary read failed", exc_info=True)
            return
        context = [{"role": row.role.value, "content": row.content} for row in rows]
        summary = build_summary(context, llm)
        if not summary:
            return
        try:
            self._summaries.upsert(
                user_id,
                conversation_id,
                summary,
                message_count=len(rows),
                last_message_at=rows[-1].created_at,
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            log.warning("summary persist failed", exc_info=True)
            return
        store = self._continuity_store()
        if store is not None:
            try:
                store.index_summary(str(user_id), str(conversation_id), summary, title)
            except Exception:
                log.warning("summary index failed", exc_info=True)

    def _continuity_store(self) -> ContinuityStore | None:
        """Return a continuity store, or None when disabled/unavailable."""
        if not settings.continuity_enabled:
            return None
        try:
            return ContinuityStore(VectorStore(persist_dir=settings.chromadb_persist_dir))
        except Exception:
            log.warning("continuity store unavailable", exc_info=True)
            return None

    def _build_extractor(self) -> RecordExtractor | None:
        """Return the dedicated extractor, or None when disabled/unconfigured."""
        if not settings.extraction_enabled:
            return None
        try:
            return GroqActivityExtractor(
                api_key=settings.extraction_api_key or "",
                model=settings.extraction_model,
            )
        except Exception:
            log.warning("activity extractor could not be initialised", exc_info=True)
            return None

    def _extract_and_persist(self, user_id: UUID, message: str) -> tuple[list[dict], list[str]]:
        """Extract structured records and persist them to the right services.

        Returns (tool_events, confirmations). Containment is total: any failure
        (extractor missing, provider error, or a per-record write error) results
        in no events / no false confirmation, and the assistant response is
        unaffected. Individual write failures are reported honestly, never as
        success.
        """
        extractor = self._extractor or self._build_extractor()
        if extractor is None:
            return [], []
        # Never feed unsafe/injection content to the extraction model.
        if run_safety_rules(message).blocked:
            return [], []
        try:
            result = extractor.extract(message)
        except Exception:
            log.warning("activity extraction raised", exc_info=True)
            return [], []

        outcomes = persist_extraction(self._db, user_id, result)
        events: list[dict[str, Any]] = []
        confirmations: list[str] = []
        for outcome in outcomes:
            if outcome.status in {"saved", "duplicate", "failed"}:
                events.append(
                    {
                        "tool": f"extract_{outcome.kind}",
                        "status": outcome.status,
                        "summary": outcome.summary,
                        "record_id": outcome.record_id,
                    }
                )
            line = _confirmation_line(outcome)
            if line:
                confirmations.append(line)
        return events, confirmations


def _confirmation_line(outcome: RecordedOutcome) -> str | None:
    """Deterministic, truthful user-facing line for a persistence outcome."""
    kind = outcome.kind.replace("_", " ")
    if outcome.kind == "completed_workout":
        if outcome.status == "saved":
            return f"Workout recorded: {outcome.summary}."
        if outcome.status == "duplicate":
            return f"That workout ({outcome.summary}) is already recorded."
        return f"I couldn't save the workout ({outcome.summary}); please try again in a moment."
    if outcome.status == "saved":
        return f"Saved {kind}: {outcome.summary}."
    if outcome.status == "duplicate":
        return f"That {kind} ({outcome.summary}) is already saved."
    if outcome.status == "failed":
        return f"I couldn't save the {kind} ({outcome.summary}); please try again."
    return None
