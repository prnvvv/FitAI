"""add conversation summaries for cross-chat recall

Revision ID: 0004_conversation_summaries
Revises: 0dafb73c281c
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0004_conversation_summaries"
down_revision: Union[str, None] = "0dafb73c281c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the per-conversation summary table used for past-chat recall."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "conversation_summaries" in inspector.get_table_names():
        return
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversation_summaries_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_summaries_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_summaries"),
    )
    op.create_index("ix_conversation_summaries_user_id", "conversation_summaries", ["user_id"])
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
        unique=True,
    )
    op.create_index(
        "ix_conversation_summaries_user_updated",
        "conversation_summaries",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_summaries_user_updated", table_name="conversation_summaries")
    op.drop_index("ix_conversation_summaries_conversation_id", table_name="conversation_summaries")
    op.drop_index("ix_conversation_summaries_user_id", table_name="conversation_summaries")
    op.drop_table("conversation_summaries")
