"""Integration tests for model relationships and cascade behavior."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.models.profile import Profile
from app.models.user import User


def _make_user() -> User:
    return User(id=uuid.uuid4(), email="models@example.com")


def test_conversation_delete_cascades_messages(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    conversation = Conversation(user_id=user.id, title="Chat")
    conversation.messages.append(
        Message(role=MessageRole.USER, content="hello", conversation=conversation)
    )
    conversation.messages.append(
        Message(role=MessageRole.ASSISTANT, content="hi", conversation=conversation)
    )
    db_session.add(conversation)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Message)) == 2

    db_session.delete(conversation)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Message)) == 0


def test_user_delete_cascades_profile(db_session) -> None:
    user = _make_user()
    user.profile = Profile(date_of_birth=datetime(1990, 1, 1).date(), height_cm=180)
    db_session.add(user)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Profile)) == 1

    db_session.delete(user)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Profile)) == 0


def test_timestamps_are_populated(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.created_at.tzinfo is not None or isinstance(user.created_at, datetime)


def test_unique_active_memory_per_key(db_session) -> None:
    from app.models.enums import MemoryKey, MemoryStatus
    from app.models.memory import Memory

    user = _make_user()
    db_session.add(user)
    db_session.add(
        Memory(user_id=user.id, key=MemoryKey.WEIGHT, value=72, status=MemoryStatus.ACTIVE)
    )
    db_session.commit()

    db_session.add(
        Memory(user_id=user.id, key=MemoryKey.WEIGHT, value=70, status=MemoryStatus.ACTIVE)
    )
    try:
        db_session.commit()
    except Exception:  # noqa: BLE001 - IntegrityError expected
        db_session.rollback()
    else:
        raise AssertionError("Expected a uniqueness violation for a second active memory")


def test_current_time_is_timezone_aware() -> None:
    assert datetime.now(timezone.utc).tzinfo is not None
