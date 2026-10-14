"""add document content hash for duplicate detection

Revision ID: 0dafb73c281c
Revises: 0cf16f5439a2
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0dafb73c281c"
down_revision: Union[str, None] = "0cf16f5439a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add an optional content hash. Existing rows keep NULL and are untouched."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("documents")}
    if "content_hash" not in columns:
        op.add_column(
            "documents",
            sa.Column("content_hash", sa.String(length=64), nullable=True),
        )
    indexes = {index["name"] for index in inspector.get_indexes("documents")}
    if "ix_documents_user_content_hash" not in indexes:
        op.create_index(
            "ix_documents_user_content_hash",
            "documents",
            ["user_id", "content_hash"],
        )


def downgrade() -> None:
    op.drop_index("ix_documents_user_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
