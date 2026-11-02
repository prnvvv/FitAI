"""Startup schema verification."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.db.base import Base
from app.db.schema_check import (
    DatabaseSchemaError,
    alembic_head_revision,
    is_ephemeral_sqlite,
    verify_database_schema,
)


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///", "sqlite:///:memory:"])
def test_in_memory_sqlite_detected(url: str) -> None:
    assert is_ephemeral_sqlite(url)


def test_file_sqlite_and_postgres_not_ephemeral(tmp_path) -> None:
    assert not is_ephemeral_sqlite(f"sqlite:///{tmp_path / 'x.db'}")
    assert not is_ephemeral_sqlite("postgresql+psycopg2://u:p@h:5432/d")


def test_in_memory_database_rejected() -> None:
    with pytest.raises(DatabaseSchemaError, match="in-memory"):
        verify_database_schema(create_engine("sqlite:///"), "head")


def test_unmigrated_database_rejected(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    with pytest.raises(DatabaseSchemaError, match="alembic_version"):
        verify_database_schema(engine, "head")


def test_stale_revision_rejected(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('old')"))
    with pytest.raises(DatabaseSchemaError, match="mismatch"):
        verify_database_schema(engine, "head")


def test_missing_tables_rejected(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('head')"))
    with pytest.raises(DatabaseSchemaError, match="users"):
        verify_database_schema(engine, "head")


def test_valid_schema_passes(tmp_path) -> None:
    import app.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('head')"))
    verify_database_schema(engine, "head")


def test_head_revision_independent_of_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert alembic_head_revision() == "0004_conversation_summaries"
