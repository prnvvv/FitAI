"""Integration: the agent's memory-writer adapter persists history correctly.

These tests exercise the real MemoryService/repository against an in-memory
SQLite database to prove that:
  * a dated historical event is written to memory_history and does NOT silently
    mutate current memory, and
  * an AUTO_APPLY turn writes exactly one history row (the follow-up record made
    by ``apply_decisions`` does not duplicate it).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.memory.change_detector import ChangeKind, DetectedChange
from app.memory.extractor import ExtractedFact, StatementType, Tense
from app.memory.history import build_history_record
from app.models.enums import MemoryKey
from app.repositories.memory_repository import MemoryRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import _MemoryWriterAdapter


def _fact(
    *,
    value: float = 72.0,
    tense: Tense = Tense.PRESENT,
    statement_type: StatementType = StatementType.EXPLICIT,
    confidence: float = 0.9,
    timestamp: datetime | None = None,
) -> ExtractedFact:
    return ExtractedFact(
        field="weight",
        value=value,
        unit="kg",
        confidence=confidence,
        timestamp=timestamp,
        extracted_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        tense=tense,
        statement_type=statement_type,
        source_text="I weighed 72 kg",
    )


def _history_total(db: Session, user_id) -> int:
    _rows, total = MemoryRepository(db).list_history(user_id, limit=50, offset=0)
    return total


def test_historical_event_is_persisted_without_changing_current_memory(db_session: Session) -> None:
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "history@example.com")
    writer = _MemoryWriterAdapter(db_session, user_id)
    repo = MemoryRepository(db_session)

    when = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    fact = _fact(
        value=80.0, tense=Tense.PAST, statement_type=StatementType.HISTORICAL, timestamp=when
    )
    record = build_history_record(fact)
    assert record is not None
    assert record.value == 80.0

    assert writer.record_history(str(user_id), record) is True

    persisted, total = repo.list_history(user_id, limit=50, offset=0)
    assert total == 1
    assert float(persisted[0].new_value) == 80.0
    # The historical note must not create or overwrite a current memory fact.
    assert repo.get_active(user_id, MemoryKey.WEIGHT) is None


def test_auto_apply_writes_exactly_one_history_row(db_session: Session) -> None:
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "auto@example.com")
    writer = _MemoryWriterAdapter(db_session, user_id)
    repo = MemoryRepository(db_session)

    change = DetectedChange(fact=_fact(value=72.0), kind=ChangeKind.NEW)
    assert writer.apply_update(str(user_id), change) is True

    assert _history_total(db_session, user_id) == 1  # CREATE history from the service
    assert repo.get_active(user_id, MemoryKey.WEIGHT) is not None

    # apply_decisions always follows an AUTO_APPLY with record_history; the
    # adapter must recognize this is the same fact already historised.
    record = build_history_record(change.fact)
    assert record is not None
    assert writer.record_history(str(user_id), record) is True
    assert _history_total(db_session, user_id) == 1  # no duplicate row


def test_two_distinct_historical_events_both_persist(db_session: Session) -> None:
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "two@example.com")
    writer = _MemoryWriterAdapter(db_session, user_id)

    older = build_history_record(
        _fact(
            value=84.0,
            tense=Tense.PAST,
            statement_type=StatementType.HISTORICAL,
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
    )
    newer = build_history_record(
        _fact(
            value=80.0,
            tense=Tense.PAST,
            statement_type=StatementType.HISTORICAL,
            timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
    )
    assert older is not None and newer is not None
    assert writer.record_history(str(user_id), older) is True
    assert writer.record_history(str(user_id), newer) is True

    assert _history_total(db_session, user_id) == 2
    assert MemoryRepository(db_session).get_active(user_id, MemoryKey.WEIGHT) is None
