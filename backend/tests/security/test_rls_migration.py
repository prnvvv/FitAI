"""Static checks on the RLS migration (no PostgreSQL needed).

Row Level Security is defence in depth: the FastAPI backend connects as the
``postgres`` role, which bypasses RLS, so ownership is enforced in application
code too (see ``test_authorization_sweep.py``). These tests make sure no table
is ever added without RLS, and that the policy shapes stay owner-scoped.
"""

from __future__ import annotations

import re
from pathlib import Path

import app.models  # noqa: F401  (register all models)
from app.db.base import Base

MIGRATION = next(
    (Path(__file__).resolve().parents[2] / "migrations" / "versions").glob("ca4d2c439416_*.py")
)
SOURCE = MIGRATION.read_text(encoding="utf-8")

#: Created with raw SQL in migration 0005 (PostgreSQL only), so not in ORM metadata.
RAW_SQL_TABLES = {"vector_chunks"}


def _enabled_tables() -> set[str]:
    upgrade = SOURCE.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    return set(re.findall(r'_rls_enable\("([a-z_]+)"\)', upgrade))


def test_every_application_table_has_rls_enabled() -> None:
    expected = set(Base.metadata.tables) | RAW_SQL_TABLES
    assert _enabled_tables() == expected, (
        "A table was added or removed without updating the RLS migration/a new migration. "
        f"missing={expected - _enabled_tables()} extra={_enabled_tables() - expected}"
    )


def test_downgrade_disables_the_same_tables() -> None:
    downgrade = SOURCE.split("def downgrade()", 1)[1].split("def _rls_enable", 1)[0]
    disabled = set(re.findall(r'"([a-z_]+)"', downgrade.split("# 1. Disable RLS", 1)[1]))
    assert _enabled_tables() <= disabled


def test_user_owned_tables_use_auth_uid_policies() -> None:
    for table in ("conversations", "documents", "memories", "workout_sessions", "measurements"):
        assert table in SOURCE
    assert SOURCE.count("auth.uid()") >= 6
    # Authenticated policies must carry both USING and WITH CHECK (no write bypass).
    assert "WITH CHECK (auth.uid() =" in SOURCE
    assert "WITH CHECK (EXISTS" in SOURCE


def test_indirect_ownership_tables_join_to_their_parent() -> None:
    assert '_policy_join("messages", "conversations", "id", "conversation_id")' in SOURCE
    assert '_policy_join("workout_sets", "workout_sessions", "id", "session_id")' in SOURCE
    assert (
        '_policy_join("planned_exercises", "planned_sessions", "id", "planned_session_id")'
        in SOURCE
    )


def test_vector_chunks_are_owner_and_collection_scoped() -> None:
    assert "collection = 'user' AND owner_id::uuid = auth.uid()" in SOURCE
    assert "CREATE POLICY anon_deny ON vector_chunks TO anon USING (false)" in SOURCE


def test_anonymous_role_can_only_read_global_exercises() -> None:
    anon_policies = re.findall(r"TO anon\s+\"?\s*\"?USING \(([^)]*)\)", SOURCE)
    permitted = {p.strip() for p in anon_policies}
    assert permitted <= {"false", "user_id IS NULL"}
    assert "CREATE POLICY anon_canonical_read ON exercise_library" in SOURCE
    assert "user_id IS NULL OR auth.uid() = user_id" in SOURCE  # authenticated: global + own
