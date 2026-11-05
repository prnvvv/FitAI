"""resize vector_chunks.embedding to 1024 dimensions (Qwen3-Embedding-0.6B)

Revision ID: 0006_vector_dimension_1024
Revises: 0005_ingestion_jobs_pgvector
Create Date: 2026-11-05

0005 created ``vector_chunks.embedding`` as ``vector(384)`` for all-MiniLM-L6-v2.
Qwen3-Embedding-0.6B produces 1024-dimension vectors, and vectors of different
models are not comparable, so the column is resized.

Safety: this never deletes or rewrites data. A pgvector column cannot be resized
while it holds vectors of the old size, so the migration REFUSES to run
(raising, with nothing changed) if ``vector_chunks`` contains any row. In that case
re-embedding is a deliberate operator decision: empty the derived index yourself
(documents/originals are untouched and can be re-ingested), then re-run. PostgreSQL
only; a no-op elsewhere (SQLite tests have no vector table).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0006_vector_dimension_1024"
down_revision: Union[str, None] = "0005_ingestion_jobs_pgvector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _resize(dimension: int) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    rows = bind.execute(sa.text("SELECT count(*) FROM vector_chunks")).scalar_one()
    if rows:
        raise RuntimeError(
            f"vector_chunks holds {rows} vector(s); refusing to resize the embedding column "
            f"to {dimension} dimensions. The vectors are derived data: empty the table "
            "deliberately (originals are kept in Storage and can be re-ingested), then re-run "
            "the migration."
        )
    op.execute("DROP INDEX IF EXISTS ix_vector_chunks_embedding_hnsw")
    op.execute(f"ALTER TABLE vector_chunks ALTER COLUMN embedding TYPE vector({dimension})")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_embedding_hnsw "
        "ON vector_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def upgrade() -> None:
    _resize(1024)


def downgrade() -> None:
    _resize(384)
