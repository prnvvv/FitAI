"""Regression: the chat list reflects recent activity, not creation time.

``list_conversations`` promises "newest first" and orders by ``updated_at``.
Adding a message did not previously touch the conversation row, so a chat you
had just used never moved back to the top. These tests pin the ordering so the
behaviour cannot silently regress.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.enums import MessageRole
from app.repositories.user_repository import UserRepository
from app.services.conversation_service import ConversationService

# Far enough in the past that the real wall clock is always "more recent".
EARLY = datetime(2000, 1, 1, tzinfo=timezone.utc)
LATER = datetime(2000, 1, 2, tzinfo=timezone.utc)


def test_new_message_resorts_conversation_to_top(db_session: Session) -> None:
    """A message in an older chat resurfaces it above a newer, idle chat."""
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "a@example.com")
    service = ConversationService(db_session)

    first = service.create(uid, "First")
    second = service.create(uid, "Second")

    # Pin deterministic timestamps so the assertion does not depend on the
    # database's clock resolution (SQLite stores second-precision defaults).
    first.updated_at = EARLY
    second.updated_at = LATER
    db_session.commit()

    items, total = service.list_conversations(uid, limit=10, offset=0)
    assert total == 2
    assert [c.id for c in items] == [second.id, first.id]

    # Activity in the older conversation must move it back to the top.
    service.add_message(uid, first.id, MessageRole.USER, "back for more")

    items, _ = service.list_conversations(uid, limit=10, offset=0)
    assert [c.id for c in items] == [first.id, second.id]
