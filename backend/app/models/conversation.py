"""Conversations and messages."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import MessageRole
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A persistent chat conversation owned by a single user."""

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
    summary: Mapped[ConversationSummary | None] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single message within a conversation.

    ``message_metadata`` is a reserved-safe attribute name for the ``metadata``
    column, which carries AI-produced extras such as retrieved sources or tool
    output without changing the core schema.
    """

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole, "message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSONType,
        nullable=True,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ConversationSummary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A rolling, owner-scoped summary of one conversation.

    One row per conversation (``conversation_id`` is unique). It powers
    cross-chat recall: the summary is indexed for semantic search and injected as
    "past chats" context on later turns, without replaying the full transcript.
    Deleting the conversation cascades to its summary.
    """

    __tablename__ = "conversation_summaries"
    __table_args__ = (Index("ix_conversation_summaries_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="summary")
