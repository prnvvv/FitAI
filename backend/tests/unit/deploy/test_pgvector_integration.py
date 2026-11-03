"""PgVectorStore against a real PostgreSQL + pgvector (opt-in).

Set ``TEST_PGVECTOR_URL`` to a *disposable* database, for example::

    docker run -d --name fitai-pgvector-test -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=fitai_test -p 54329:5432 pgvector/pgvector:pg16
    TEST_PGVECTOR_URL=postgresql+psycopg2://postgres:test@localhost:54329/fitai_test

The suite creates and drops only its own ``vector_chunks`` table. Skipped otherwise,
so ordinary CI needs no database.
"""

from __future__ import annotations

import hashlib
import math
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.rag.chunker import Chunk
from app.rag.pg_vector_store import PgVectorStore
from app.rag.vector_store import CONTINUITY_COLLECTION, KNOWLEDGE_COLLECTION, USER_COLLECTION

URL = os.environ.get("TEST_PGVECTOR_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_PGVECTOR_URL not set")

DIM = 384


def fake_embed(texts):
    """Deterministic bag-of-words embedding: shared words -> similar vectors."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        for word in t.lower().split():
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


@pytest.fixture(scope="module")
def engine():
    """A disposable database with the *real* migration chain applied (head)."""
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings
    from app.db.schema_check import BACKEND_DIR

    eng = create_engine(URL, future=True)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    original = settings.database_url
    settings.database_url = URL
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original
    yield eng
    eng.dispose()


@pytest.fixture
def store(engine):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE vector_chunks"))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return PgVectorStore(embedding_function=fake_embed, session_factory=sessions, dimension=DIM)


def test_migration_created_the_expected_objects(engine) -> None:
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        indexes = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes"))}
        assert {"ix_vector_chunks_embedding_hnsw", "ix_vector_chunks_scope"} <= indexes
        assert conn.scalar(text("SELECT to_regclass('document_ingestion_jobs')"))
        dim = conn.scalar(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid='vector_chunks'::regclass AND attname='embedding'"
            )
        )
        assert dim == DIM


def test_migration_downgrade_then_upgrade_is_clean(engine) -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings
    from app.db.schema_check import BACKEND_DIR

    original = settings.database_url
    settings.database_url = URL
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        command.downgrade(cfg, "-1")
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT to_regclass('vector_chunks')")) is None
            assert conn.scalar(text("SELECT to_regclass('documents')"))  # prior data model intact
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original


def _chunk(cid, body, owner=None, doc="d1", **meta):
    m = {"doc_id": doc, "source": "s.pdf", "page": 1, "chunk_index": 0, **meta}
    if owner:
        m["owner_id"] = owner
    return Chunk(cid, body, m)


def test_roundtrip_ranking_and_cosine_distance(store) -> None:
    store.add_chunks(
        KNOWLEDGE_COLLECTION,
        [
            _chunk("a", "squat deadlift strength training"),
            _chunk("b", "marathon running endurance cardio"),
            _chunk("c", "protein carbohydrate nutrition meal"),
        ],
    )
    hits = store.query(KNOWLEDGE_COLLECTION, "squat strength training", n_results=3)
    assert [h.id for h in hits][0] == "a"
    assert hits[0].distance < hits[1].distance
    assert 0.0 <= hits[0].distance <= 2.0
    assert hits[0].text.startswith("squat") and hits[0].metadata["source"] == "s.pdf"


def test_upsert_is_idempotent(store) -> None:
    for _ in range(3):
        store.add_chunks(KNOWLEDGE_COLLECTION, [_chunk("a", "squat")])
    assert store.count(KNOWLEDGE_COLLECTION) == 1


def test_owner_isolation_and_required_owner(store) -> None:
    store.add_chunks(USER_COLLECTION, [_chunk("u1:0", "my squat plan", owner="u1")], "u1")
    store.add_chunks(USER_COLLECTION, [_chunk("u2:0", "my squat plan", owner="u2")], "u2")
    assert [h.id for h in store.query(USER_COLLECTION, "squat", 5, owner_id="u1")] == ["u1:0"]
    assert store.count(USER_COLLECTION, owner_id="u2") == 1
    with pytest.raises(PermissionError):
        store.query(USER_COLLECTION, "squat")


def test_delete_document_is_owner_and_doc_scoped(store) -> None:
    store.add_chunks(
        USER_COLLECTION,
        [_chunk("x:0", "a b", owner="u1", doc="d1"), _chunk("x:1", "c d", owner="u1", doc="d2")],
        "u1",
    )
    store.add_chunks(USER_COLLECTION, [_chunk("y:0", "a b", owner="u2", doc="d1")], "u2")
    assert store.delete_document(USER_COLLECTION, "d1", owner_id="u1") == 1
    assert store.count(USER_COLLECTION, owner_id="u1") == 1
    assert store.count(USER_COLLECTION, owner_id="u2") == 1  # other owner untouched


def test_metadata_filters(store) -> None:
    store.add_chunks(
        CONTINUITY_COLLECTION,
        [
            _chunk("m1", "likes squats", owner="u1", kind="memory", page=1),
            _chunk("s1", "likes squats too", owner="u1", kind="summary", page=5),
        ],
        "u1",
    )
    kinds = lambda **kw: sorted(  # noqa: E731
        h.id for h in store.query(CONTINUITY_COLLECTION, "squats", 5, owner_id="u1", **kw)
    )
    assert kinds(where={"kind": "memory"}) == ["m1"]
    assert kinds(where={"page": {"$gte": 3}}) == ["s1"]
    assert kinds(where={"kind": {"$in": ["memory", "summary"]}}) == ["m1", "s1"]


def test_collection_info_reports_dimension_and_model(store) -> None:
    store.add_chunks(KNOWLEDGE_COLLECTION, [_chunk("a", "squat")])
    info = store.collection_info(KNOWLEDGE_COLLECTION)
    assert info["count"] == 1 and info["dimension"] == DIM and info["embedding_model"]
    assert store.embedding_dimension() == DIM


def test_chunk_text_order_and_listing(store) -> None:
    store.add_chunks(
        USER_COLLECTION,
        [
            _chunk("p:1", "second", owner="u1", chunk_index=1),
            _chunk("p:0", "first", owner="u1", chunk_index=0),
        ],
        "u1",
    )
    assert store.stored_chunk_texts(USER_COLLECTION, "d1", "u1") == ["first", "second"]
    assert {r[2] for r in store.all_chunk_owners(USER_COLLECTION)} == {"u1"}
    assert store.document_vector_count(USER_COLLECTION, "d1", "u1") == 2
