"""add durable ingestion jobs and the pgvector chunk table

Revision ID: 0005_ingestion_jobs_pgvector
Revises: 0004_conversation_summaries
Create Date: 2026-11-03

Purely additive: creates two new tables and (on PostgreSQL) the ``vector``
extension. No existing table, column or row is altered or removed, and the
Chroma data is not touched. ``vector_chunks`` is PostgreSQL-only; on SQLite
(tests) only the jobs table is created.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0005_ingestion_jobs_pgvector"
down_revision: Union[str, None] = "0004_conversation_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2; must equal EMBEDDING_DIMENSION in settings


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_ingestion_jobs" not in tables:
        op.create_table(
            "document_ingestion_jobs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "document_id",
                sa.Uuid(),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("next_unit", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_chunk_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_units", sa.Integer(), nullable=True),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_by", sa.String(64), nullable=True),
            sa.Column("last_error", sa.String(500), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
        )
        op.create_index(
            "ix_ingestion_jobs_status_lease",
            "document_ingestion_jobs",
            ["status", "locked_until"],
        )

    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS vector_chunks (
            collection      text        NOT NULL,
            id              text        NOT NULL,
            owner_id        text,
            doc_id          text,
            content         text        NOT NULL,
            metadata        jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
            embedding       vector({EMBEDDING_DIMENSION}) NOT NULL,
            embedding_model text        NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (collection, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_scope "
        "ON vector_chunks (collection, owner_id, doc_id)"
    )
    # Cosine distance, matching the Chroma collections' hnsw:space=cosine.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_embedding_hnsw "
        "ON vector_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Drop only the objects this revision created (both tables are new and derived)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS vector_chunks")
        # The extension is intentionally left installed: other objects may use it.
    op.drop_table("document_ingestion_jobs")
