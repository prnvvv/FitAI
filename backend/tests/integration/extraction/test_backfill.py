"""Integration tests for historical backfill."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.extraction.backfill import BackfillService
from app.extraction.schemas import ExtractionResult, UserPreference
from app.models.enums import MessageRole
from app.repositories.conversation_repository import ConversationRepository, MessageRepository
from app.repositories.user_repository import UserRepository
from app.services.profile_service import ProfileService

NOW = datetime(2026, 5, 20, 9, 0, 0, tzinfo=timezone.utc)


class _PrefExtractor:
    """Returns a stable 'cycling' preference regardless of the message."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, message: str, now=None) -> ExtractionResult:
        self.calls += 1
        return ExtractionResult(
            user_preferences=[
                UserPreference(preference="cycling", confidence=0.9, source_text=message)
            ]
        )


class _BrokenExtractor:
    def extract(self, message: str, now=None) -> ExtractionResult:
        raise RuntimeError("provider down")


def _seed_conversation(db: Session, user_id, text: str) -> None:
    conversations = ConversationRepository(db)
    messages = MessageRepository(db)
    conv = conversations.create(user_id, "history")
    messages.create(conv.id, MessageRole.USER, text)
    messages.create(conv.id, MessageRole.ASSISTANT, "Nice!")  # assistant ignored
    db.commit()


def test_backfill_persists_preference_from_history(db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "a@example.com")
    _seed_conversation(db_session, uid, "I like to do cycling every day.")

    service = BackfillService(db_session, _PrefExtractor())
    report = service.backfill_user(uid)

    assert report.messages_with_facts == 1
    assert report.saved >= 1
    profile = ProfileService(db_session).get(uid)
    assert profile is not None
    assert "cycling" in (profile.preferences or {}).get("interests", [])


def test_backfill_is_idempotent_no_duplicates(db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "a@example.com")
    _seed_conversation(db_session, uid, "I like to do cycling every day.")

    service = BackfillService(db_session, _PrefExtractor())
    service.backfill_user(uid)  # first pass saves
    report2 = service.backfill_user(uid)  # second pass must dedup

    assert report2.saved == 0
    assert report2.duplicates >= 1
    interests = (ProfileService(db_session).get(uid).preferences or {}).get("interests", [])
    assert interests.count("cycling") == 1


def test_backfill_respects_user_isolation(db_session: Session) -> None:
    uid_a = uuid4()
    uid_b = uuid4()
    UserRepository(db_session).get_or_create(uid_a, "a@example.com")
    UserRepository(db_session).get_or_create(uid_b, "b@example.com")
    _seed_conversation(db_session, uid_a, "I like to do cycling every day.")

    BackfillService(db_session, _PrefExtractor()).backfill_user(uid_a)
    # User B has no history; nothing should be extracted or leaked to B.
    report_b = BackfillService(db_session, _PrefExtractor()).backfill_user(uid_b)
    assert report_b.messages_with_facts == 0
    profile_b = ProfileService(db_session).get(uid_b)
    assert profile_b is None or not (profile_b.preferences or {}).get("interests")


def test_backfill_is_bounded(db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "many@example.com")
    conversations = ConversationRepository(db_session)
    messages = MessageRepository(db_session)
    for _ in range(3):
        conv = conversations.create(uid, "session")
        for _ in range(10):
            messages.create(conv.id, MessageRole.USER, "I like cycling.")
    db_session.commit()

    extractor = _PrefExtractor()
    report = BackfillService(db_session, extractor).backfill_user(uid, max_messages=5)
    assert report.messages_scanned == 5  # bounded, not all 30
    assert extractor.calls == 5  # one USER message scanned => one extraction call
    # Resuming continues from where the bound stopped.
    report2 = BackfillService(db_session, _PrefExtractor()).backfill_user(uid, max_messages=5)
    assert report2.messages_scanned == 5


def test_backfill_contains_extraction_failure(db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "fail@example.com")
    _seed_conversation(db_session, uid, "I like cycling.")

    report = BackfillService(db_session, _BrokenExtractor()).backfill_user(uid)
    assert report.failed >= 1
    assert report.messages_with_facts == 0
    profile = ProfileService(db_session).get(uid)
    assert profile is None or not (profile.preferences or {}).get("interests")


def test_backfill_no_extractor_is_a_noop(db_session: Session) -> None:
    uid = uuid4()
    UserRepository(db_session).get_or_create(uid, "noop@example.com")
    _seed_conversation(db_session, uid, "I like cycling.")
    report = BackfillService(db_session, None).backfill_user(uid)
    assert report.messages_scanned == 0
    assert report.saved == 0
