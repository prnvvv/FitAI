"""SQLite foreign-key enforcement and read-only orphan detection."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.schema_check import find_foreign_key_violations
from app.db.session import build_engine, enable_sqlite_foreign_keys
from app.models import Conversation, Message, User


def _fk_pragma(conn) -> int:
    return conn.execute(text("PRAGMA foreign_keys")).scalar_one()


@pytest.fixture
def file_engine(tmp_path):
    engine = build_engine(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _user(session: Session) -> User:
    user = User(id=uuid.uuid4(), email="a@example.com")
    session.add(user)
    session.commit()
    return user


def test_pragma_is_on_for_every_new_connection(file_engine) -> None:
    with file_engine.connect() as first, file_engine.connect() as second:
        assert _fk_pragma(first) == 1
        assert _fk_pragma(second) == 1


def test_pragma_is_on_after_pool_recycles_connections(file_engine) -> None:
    with file_engine.connect() as conn:
        assert _fk_pragma(conn) == 1
    file_engine.dispose()  # forces brand-new DBAPI connections
    with file_engine.connect() as conn:
        assert _fk_pragma(conn) == 1


def test_plain_engine_has_enforcement_off_until_helper_applied(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'plain.db').as_posix()}")
    with engine.connect() as conn:
        assert _fk_pragma(conn) == 0
    enable_sqlite_foreign_keys(engine)
    engine.dispose()
    with engine.connect() as conn:
        assert _fk_pragma(conn) == 1
    engine.dispose()


def test_invalid_reference_is_rejected(file_engine) -> None:
    with Session(file_engine) as session:
        session.add(Conversation(id=uuid.uuid4(), user_id=uuid.uuid4(), title="x"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_conversation_removes_its_messages_only(file_engine) -> None:
    with Session(file_engine) as session:
        user = _user(session)
        keep = Conversation(id=uuid.uuid4(), user_id=user.id, title="keep")
        drop = Conversation(id=uuid.uuid4(), user_id=user.id, title="drop")
        session.add_all([keep, drop])
        session.flush()
        session.add_all(
            [
                Message(conversation_id=keep.id, role="user", content="k"),
                Message(conversation_id=drop.id, role="user", content="d1"),
                Message(conversation_id=drop.id, role="assistant", content="d2"),
            ]
        )
        session.commit()
        session.delete(drop)
        session.commit()

        remaining = session.query(Message).all()
        assert [m.content for m in remaining] == ["k"]
        assert session.get(Conversation, keep.id) is not None
    assert find_foreign_key_violations(file_engine) == []


def test_orphans_in_legacy_database_are_reported_not_deleted(tmp_path) -> None:
    """A DB written while enforcement was off keeps its rows; they are only reported."""
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    legacy = create_engine(url)  # no FK enforcement, like the old engine
    Base.metadata.create_all(legacy)
    with legacy.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (:id, :cid, 'user', 'orphan', CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid.uuid4()), "cid": str(uuid.uuid4())},
        )
    legacy.dispose()

    engine = build_engine(url)  # the application's engine, enforcement on
    try:
        violations = find_foreign_key_violations(engine)
        assert [(v["table"], v["parent_table"]) for v in violations] == [
            ("messages", "conversations")
        ]
        with engine.connect() as conn:  # the row is still readable and untouched
            assert conn.execute(text("SELECT count(*) FROM messages")).scalar_one() == 1
    finally:
        engine.dispose()


def test_violation_check_is_a_noop_on_non_sqlite() -> None:
    class _Dialect:
        name = "postgresql"

    class _Engine:
        dialect = _Dialect()

    assert find_foreign_key_violations(_Engine()) == []  # type: ignore[arg-type]


def test_db_session_fixture_enforces_foreign_keys(db_session: Session) -> None:
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
