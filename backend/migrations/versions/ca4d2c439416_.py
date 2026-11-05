"""Enable RLS and security policies for all application tables.

Revision ID: ca4d2c439416
Revises: 0006_vector_dimension_1024
Create Date: 2026-11-05 16:54:34.658540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca4d2c439416'
down_revision: Union[str, None] = '0006_vector_dimension_1024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _policy_auth_deny(table: str) -> None:
    """Create authenticated own-row policy + anon deny policy for a table with user_id."""
    sql = (
        "CREATE POLICY authenticated ON " + table +
        " TO authenticated "
        "USING (auth.uid() = " + table + ".user_id) "
        "WITH CHECK (auth.uid() = " + table + ".user_id);"
    )
    op.execute(sa.text(sql))
    op.execute(
        sa.text(
            "CREATE POLICY anon_deny ON " + table +
            " TO anon "
            "USING (false);"
        )
    )


def _policy_join(table: str, join_table: str, join_pk: str, fk_col: str) -> None:
    """Create policy for table owned through a parent key join.

    Example: messages owned through conversations (messages.conversation_id -> conversations.id).
    The USING clause filters rows where the parent row belongs to the authenticated user.
    """
    # USING condition: EXISTS (SELECT ... FROM join_table WHERE join_pk = fk AND join_table.user_id = auth.uid())
    using_sql = (
        "USING (EXISTS ("
        "SELECT 1 FROM " + join_table +
        " WHERE " + join_table + "." + join_pk + " = " + table + "." + fk_col +
        " AND " + join_table + ".user_id = auth.uid()))"
    )
    # WITH CHECK condition: same as USING for read/write consistency
    with_check_sql = (
        "WITH CHECK (EXISTS ("
        "SELECT 1 FROM " + join_table +
        " WHERE " + join_table + "." + join_pk + " = " + table + "." + fk_col +
        " AND " + join_table + ".user_id = auth.uid())"
    )
    sql = (
        "CREATE POLICY authenticated ON " + table +
        " TO authenticated "
        + using_sql +
        " " + with_check_sql +
        ");"
    )
    op.execute(sa.text(sql))
    op.execute(
        sa.text(
            "CREATE POLICY anon_deny ON " + table +
            " TO anon "
            "USING (false);"
        )
    )


def upgrade() -> None:
    # ── only run on PostgreSQL; SQLite/test environments do not support RLS
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # ── enable RLS on all 19 application tables ─────────────────────
    _rls_enable("users")
    _rls_enable("user_profiles")
    _rls_enable("conversations")
    _rls_enable("messages")
    _rls_enable("conversation_summaries")
    _rls_enable("memories")
    _rls_enable("memory_history")
    _rls_enable("documents")
    _rls_enable("document_ingestion_jobs")
    _rls_enable("exercise_library")
    _rls_enable("measurements")
    _rls_enable("workout_sessions")
    _rls_enable("workout_sets")
    _rls_enable("planned_sessions")
    _rls_enable("planned_exercises")
    _rls_enable("activity_events")
    _rls_enable("pending_memory_updates")
    _rls_enable("vector_chunks")

    # ── 1. Direct user_id tables: authenticated own-row policy ────────
    for t in (
        "user_profiles", "conversations", "conversation_summaries",
        "memories", "memory_history", "documents",
        "document_ingestion_jobs", "measurements",
        "workout_sessions", "planned_sessions", "activity_events",
        "pending_memory_updates",
    ):
        _policy_auth_deny(t)

    # ── 2. exercise_library: global (user_id IS NULL) + custom ────────
    op.execute(
        sa.text(
            "CREATE POLICY authenticated ON exercise_library "
            "TO authenticated "
            "USING (user_id IS NULL OR auth.uid() = user_id);"
        )
    )
    op.execute(
        sa.text("CREATE POLICY anon_canonical_read ON exercise_library "
                "TO anon "
                "USING (user_id IS NULL);")
    )

    # ── 3. messages: ownership through conversations ───────────────────
    _policy_join("messages", "conversations", "id", "conversation_id")

    # ── 4. workout_sets: ownership through workout_sessions ────────────
    _policy_join("workout_sets", "workout_sessions", "id", "session_id")

    # ── 5. planned_exercises: ownership through planned_sessions ───────
    _policy_join("planned_exercises", "planned_sessions", "id", "planned_session_id")

    # ── 6. vector_chunks: collection-scoped owner_id ───────────────────
    op.execute(
        sa.text(
            "CREATE POLICY authenticated ON vector_chunks "
            "TO authenticated "
            "USING (collection = 'user' AND owner_id::uuid = auth.uid()) "
            "WITH CHECK (collection = 'user' AND owner_id::uuid = auth.uid());"
        )
    )
    op.execute(
        sa.text("CREATE POLICY anon_deny ON vector_chunks TO anon USING (false);")
    )

    # ── 7. users table: no restrictive policies (auth manages it) ─────
    # RLS enabled but no extra policies; service_role can provision rows.


def downgrade() -> None:
    # ── only run on PostgreSQL; SQLite/test environments do not support RLS
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # ── drop policies (reverse order) ────────────────────────────────

    # 6. vector_chunks
    op.execute(sa.text("DROP POLICY IF EXISTS anon_deny ON vector_chunks;"))
    op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON vector_chunks;"))

    # 5. planned_exercises
    op.execute(sa.text("DROP POLICY IF EXISTS anon_deny ON planned_exercises;"))
    op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON planned_exercises;"))

    # 4. workout_sets
    op.execute(sa.text("DROP POLICY IF EXISTS anon_deny ON workout_sets;"))
    op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON workout_sets;"))

    # 3. messages
    op.execute(sa.text("DROP POLICY IF EXISTS anon_deny ON messages;"))
    op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON messages;"))

    # 3. exercise_library
    op.execute(sa.text("DROP POLICY IF EXISTS anon_canonical_read ON exercise_library;"))
    op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON exercise_library;"))

    # 2. direct user_id tables (reverse order)
    for t in reversed(
        ("pending_memory_updates", "activity_events", "planned_sessions",
         "workout_sessions", "measurements", "documents",
         "document_ingestion_jobs", "memories", "memory_history",
         "conversation_summaries", "conversations", "user_profiles")
    ):
        op.execute(sa.text("DROP POLICY IF EXISTS authenticated ON " + t + ";"))
        op.execute(sa.text("DROP POLICY IF EXISTS anon_deny ON " + t + ";"))

    # 1. Disable RLS on all tables
    for t in (
        "users", "user_profiles", "conversations", "messages",
        "conversation_summaries", "memories", "memory_history",
        "documents", "document_ingestion_jobs", "exercise_library",
        "measurements", "workout_sessions", "workout_sets",
        "planned_sessions", "planned_exercises", "activity_events",
        "pending_memory_updates", "vector_chunks",
    ):
        op.execute(sa.text("ALTER TABLE " + t + " DISABLE ROW LEVEL SECURITY;"))


def _rls_enable(table: str) -> None:
    op.execute(sa.text("ALTER TABLE " + table + " ENABLE ROW LEVEL SECURITY;"))
