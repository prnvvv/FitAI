"""Persistence for per-conversation summaries (cross-chat recall)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationSummary


class ConversationSummaryRepository:
    """Persistence operations for conversation summaries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> ConversationSummary | None:
        """Return the summary for a conversation only when it belongs to the user."""
        statement = select(ConversationSummary).where(
            ConversationSummary.conversation_id == conversation_id,
            ConversationSummary.user_id == user_id,
        )
        return self._db.scalar(statement)

    def upsert(
        self,
        user_id: UUID,
        conversation_id: UUID,
        summary: str,
        *,
        message_count: int,
        last_message_at: datetime | None,
    ) -> ConversationSummary:
        """Create or replace the summary for one conversation."""
        row = self._db.scalar(
            select(ConversationSummary).where(
                ConversationSummary.conversation_id == conversation_id
            )
        )
        if row is None:
            row = ConversationSummary(
                user_id=user_id,
                conversation_id=conversation_id,
                summary=summary,
                message_count=message_count,
                last_message_at=last_message_at,
            )
            self._db.add(row)
        else:
            row.summary = summary
            row.message_count = message_count
            row.last_message_at = last_message_at
        self._db.flush()
        return row

    def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[ConversationSummary], int]:
        """Return a page of the user's summaries, newest first."""
        base = select(ConversationSummary).where(ConversationSummary.user_id == user_id)
        total = self._db.scalar(
            select(func.count())
            .select_from(ConversationSummary)
            .where(ConversationSummary.user_id == user_id)
        )
        statement = base.order_by(ConversationSummary.updated_at.desc()).limit(limit).offset(offset)
        return list(self._db.scalars(statement)), int(total or 0)

    def delete_for_conversation(self, conversation_id: UUID, user_id: UUID) -> None:
        """Delete the summary of one conversation (owner-scoped)."""
        row = self.get_for_conversation(conversation_id, user_id)
        if row is not None:
            self._db.delete(row)
            self._db.flush()
