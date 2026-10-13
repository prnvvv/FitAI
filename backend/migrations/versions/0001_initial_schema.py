"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("goal", sa.String(length=200), nullable=True),
        sa.Column("activity_level", sa.String(length=20), nullable=True),
        sa.Column("dietary_preferences", JSONB, nullable=True),
        sa.Column("dietary_restrictions", JSONB, nullable=True),
        sa.Column("supplements", JSONB, nullable=True),
        sa.Column("preferences", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check(
                "activity_level",
                ("sedentary", "light", "moderate", "active", "very_active"),
            ),
            name="ck_user_profiles_activity_level",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_profiles"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check("role", ("user", "assistant", "system", "tool")),
            name="ck_messages_message_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check(
                "key",
                (
                    "weight",
                    "height",
                    "goal",
                    "dietary_preferences",
                    "dietary_restrictions",
                    "activity_level",
                    "supplements",
                    "experience_level",
                    "workout_frequency",
                ),
            ),
            name="ck_memories_memory_key",
        ),
        sa.CheckConstraint(
            _enum_check("status", ("active", "superseded", "deleted")),
            name="ck_memories_memory_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memories_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memories"),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index(
        "uq_memories_user_key_active",
        "memories",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "memory_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("change_type", sa.String(length=20), nullable=False),
        sa.Column("previous_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check(
                "key",
                (
                    "weight",
                    "height",
                    "goal",
                    "dietary_preferences",
                    "dietary_restrictions",
                    "activity_level",
                    "supplements",
                    "experience_level",
                    "workout_frequency",
                ),
            ),
            name="ck_memory_history_memory_key",
        ),
        sa.CheckConstraint(
            _enum_check("change_type", ("create", "update", "correction", "supersede", "delete")),
            name="ck_memory_history_memory_change_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memory_history_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_history_memory_id_memories",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_history"),
    )
    op.create_index("ix_memory_history_user_created", "memory_history", ["user_id", "created_at"])

    op.create_table(
        "pending_memory_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("proposed_value", JSONB, nullable=False),
        sa.Column("previous_value", JSONB, nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check(
                "key",
                (
                    "weight",
                    "height",
                    "goal",
                    "dietary_preferences",
                    "dietary_restrictions",
                    "activity_level",
                    "supplements",
                    "experience_level",
                    "workout_frequency",
                ),
            ),
            name="ck_pending_memory_updates_memory_key",
        ),
        sa.CheckConstraint(
            _enum_check("status", ("pending", "approved", "rejected", "expired")),
            name="ck_pending_memory_updates_pending_update_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_pending_memory_updates_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pending_memory_updates"),
    )
    op.create_index("ix_pending_updates_user_status", "pending_memory_updates", ["user_id", "status"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_backend", sa.String(length=50), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check("status", ("pending", "processing", "indexed", "failed")),
            name="ck_documents_document_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_documents_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])

    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_workout_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workout_sessions"),
    )
    op.create_index(
        "ix_workout_sessions_user_performed",
        "workout_sessions",
        ["user_id", "performed_at"],
    )

    op.create_table(
        "workout_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_name", sa.String(length=200), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("weight_unit", sa.String(length=10), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check("weight_unit", ("kg", "lb")),
            name="ck_workout_sets_weight_unit",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["workout_sessions.id"],
            name="fk_workout_sets_session_id_workout_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workout_sets"),
    )
    op.create_index("ix_workout_sets_session", "workout_sets", ["session_id"])

    op.create_table(
        "measurements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("value", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            _enum_check(
                "type",
                (
                    "weight",
                    "body_fat_percent",
                    "chest",
                    "waist",
                    "hips",
                    "arm",
                    "thigh",
                    "neck",
                ),
            ),
            name="ck_measurements_measurement_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_measurements_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_measurements"),
    )
    op.create_index(
        "ix_measurements_user_type_measured",
        "measurements",
        ["user_id", "type", "measured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_measurements_user_type_measured", table_name="measurements")
    op.drop_table("measurements")

    op.drop_index("ix_workout_sets_session", table_name="workout_sets")
    op.drop_table("workout_sets")

    op.drop_index("ix_workout_sessions_user_performed", table_name="workout_sessions")
    op.drop_table("workout_sessions")

    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_pending_updates_user_status", table_name="pending_memory_updates")
    op.drop_table("pending_memory_updates")

    op.drop_index("ix_memory_history_user_created", table_name="memory_history")
    op.drop_table("memory_history")

    op.drop_index("uq_memories_user_key_active", table_name="memories")
    op.drop_index("ix_memories_user_id", table_name="memories")
    op.drop_table("memories")

    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")

    op.drop_table("users")
