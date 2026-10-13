"""Chat orchestration: run one turn through the agent graph and persist messages."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import AgentDeps, MemoryReader, ProfileReader, build_graph, run_turn
from app.core.config import settings
from app.llm.client import GroqClient
from app.memory.change_detector import DetectedChange, MemoryEntry
from app.memory.confirmation import Decision, MemoryWriter
from app.memory.history import HistoryRecord
from app.models.enums import MemoryKey, MessageRole
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
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
                    return True
            service.create(
                uid,
                key,
                change.fact.value,
                confidence=Decimal(str(change.fact.confidence)),
                source="agent",
                effective_at=change.fact.timestamp,
            )
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
        # Historical records are stored by correcting current memory; full history
        # persistence is handled separately by the memory service.
        return True


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

        graph = build_graph(
            AgentDeps(
                llm=self._build_llm(),
                memory_reader=_MemoryReaderAdapter(self._db, user_id),
                memory_writer=_MemoryWriterAdapter(self._db, user_id),
                profile_reader=_ProfileReaderAdapter(self._db, user_id),
                retriever=None,
                tools={"web_search": web_search, "nearby_gyms": nearby_gyms},
                db_session=self._db,
            )
        )

        messages = self._conversations.list_recent_messages(user_id, conversation_id, limit=20)
        context = [{"role": msg.role.value, "content": msg.content} for msg in messages]

        turn = run_turn(graph, str(user_id), message, context)
        response = turn["response"]

        self._conversations.add_message(user_id, conversation_id, MessageRole.ASSISTANT, response)

        return {
            "conversation_id": conversation_id,
            "response": response,
            "title": conversation.title,
            "sources": turn.get("sources", []),
            "actions": turn.get("actions", []),
            "tool_events": turn.get("tool_results", []),
        }

    @staticmethod
    def _build_llm() -> GroqClient:
        """Return a Groq-backed completer configured from project settings."""
        return GroqClient(api_key=settings.groq_api_key, model=settings.groq_model)
