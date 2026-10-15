"""Conversation and message business logic."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)


class ConversationService:
    """Coordinates conversation lifecycle and message persistence."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._conversations = ConversationRepository(db)
        self._messages = MessageRepository(db)

    def list_conversations(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Return a page of the user's conversations."""
        return self._conversations.list_for_user(user_id, limit=limit, offset=offset)

    def create(self, user_id: UUID, title: str | None) -> Conversation:
        """Create a conversation for the user."""
        conversation = self._conversations.create(user_id, title)
        self._commit()
        self._db.refresh(conversation)
        return conversation

    def get(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        """Return the user's conversation or raise NotFoundError."""
        conversation = self._conversations.get_for_user(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    def rename(self, user_id: UUID, conversation_id: UUID, title: str | None) -> Conversation:
        """Rename the user's conversation."""
        conversation = self.get(user_id, conversation_id)
        self._conversations.rename(conversation, title)
        self._commit()
        self._db.refresh(conversation)
        return conversation

    def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        """Delete the user's conversation and its messages.

        This never affects the user's profile, memory, measurements, or
        workouts, which are independent of conversation history.
        """
        conversation = self.get(user_id, conversation_id)
        self._conversations.delete(conversation)
        self._commit()

    def list_messages(
        self, user_id: UUID, conversation_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        """Return a page of messages after verifying conversation ownership."""
        self.get(user_id, conversation_id)
        return self._messages.list_for_conversation(conversation_id, limit=limit, offset=offset)

    def list_recent_messages(
        self, user_id: UUID, conversation_id: UUID, *, limit: int
    ) -> list[Message]:
        """Return the most recent messages in chronological order.

        Shared interface for the chat pipeline; ownership is verified before
        the messages are read.
        """
        self.get(user_id, conversation_id)
        return self._messages.list_recent_for_conversation(conversation_id, limit=limit)

    def add_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message:
        """Persist a message.

        Shared interface used by Person 2's chat pipeline; ownership is verified
        before the message is written.
        """
        conversation = self.get(user_id, conversation_id)
        message = self._messages.create(conversation_id, role, content, metadata)
        # A new message means the conversation was just active; bump updated_at so
        # the chat-history list keeps its "most recently active first" ordering.
        self._conversations.touch(conversation)
        self._commit()
        self._db.refresh(message)
        return message

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The conversation could not be saved.") from exc
