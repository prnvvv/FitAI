"""Conversation and message persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole


class ConversationRepository:
    """Persistence operations for conversations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Return a page of conversations for ``user_id`` and the total count."""
        base = select(Conversation).where(Conversation.user_id == user_id)
        total = self._db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
        )
        statement = base.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
        return list(self._db.scalars(statement)), int(total or 0)

    def get_for_user(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """Return a conversation only when it belongs to ``user_id``."""
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        return self._db.scalar(statement)

    def create(self, user_id: UUID, title: str | None) -> Conversation:
        """Create and persist a conversation."""
        conversation = Conversation(user_id=user_id, title=title)
        self._db.add(conversation)
        self._db.flush()
        return conversation

    def rename(self, conversation: Conversation, title: str | None) -> Conversation:
        """Update a conversation title."""
        conversation.title = title
        self._db.flush()
        return conversation

    def delete(self, conversation: Conversation) -> None:
        """Delete a conversation and (by cascade) its messages."""
        self._db.delete(conversation)
        self._db.flush()

    def touch(self, conversation: Conversation) -> None:
        """Mark a conversation as active so it sorts to the top of the list.

        ``list_for_user`` orders by ``updated_at``; adding a message does not
        otherwise modify the conversation row, so the timestamp has to be bumped
        explicitly for "most recently active first" ordering to hold.
        """
        conversation.updated_at = datetime.now(timezone.utc)
        self._db.flush()


class MessageRepository:
    """Persistence operations for conversation messages."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_conversation(
        self, conversation_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        """Return a chronological page of messages and the total count."""
        base_filter = Message.conversation_id == conversation_id
        total = self._db.scalar(select(func.count()).select_from(Message).where(base_filter))
        statement = (
            select(Message)
            .where(base_filter)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def list_recent_for_conversation(self, conversation_id: UUID, *, limit: int) -> list[Message]:
        """Return the most recent messages in chronological (oldest-first) order."""
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list(self._db.scalars(statement))
        rows.reverse()
        return rows

    def create(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message:
        """Persist a message within a conversation.

        ``created_at`` is assigned here and kept strictly increasing within the
        conversation. The database default (``now()``) has coarse resolution on
        some engines and is identical for rows written close together, which would
        leave the order of equal timestamps to the random UUID tie-breaker and could
        show an assistant reply before the question it answers.
        """
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_metadata=metadata,
            created_at=self._next_timestamp(conversation_id),
        )
        self._db.add(message)
        self._db.flush()
        return message

    def _next_timestamp(self, conversation_id: UUID) -> datetime:
        """Return a UTC timestamp later than every stored message in the conversation."""
        now = datetime.now(timezone.utc)
        latest = self._db.scalar(
            select(func.max(Message.created_at)).where(Message.conversation_id == conversation_id)
        )
        if latest is None:
            return now
        if latest.tzinfo is None:  # SQLite returns naive datetimes
            latest = latest.replace(tzinfo=timezone.utc)
        return max(now, latest + timedelta(microseconds=1))
