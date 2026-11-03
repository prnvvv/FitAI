"""Chroma -> pgvector parity with the REAL local embedding model (opt-in).

Proves, with the production embedding function (Chroma's ONNX all-MiniLM-L6-v2):

* the vector dimension is preserved (384) through the migration script;
* retrieval ranking and cosine distances from ``PgVectorStore`` match ``VectorStore``;
* owner scoping behaves identically.

Needs ``TEST_PGVECTOR_URL`` (disposable pgvector database) and the ONNX model in the
local Chroma cache; skipped otherwise.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("TEST_PGVECTOR_URL")


def _model_cached() -> bool:
    try:
        from app.rag.embeddings import is_embedding_model_cached

        return is_embedding_model_cached()
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not URL or not _model_cached(), reason="needs TEST_PGVECTOR_URL and the cached ONNX model"
)

CORPUS = [
    ("k1", "Progressive overload means gradually increasing weight, reps or sets over time."),
    ("k2", "Protein intake of 1.6 to 2.2 grams per kilogram supports muscle growth."),
    ("k3", "Marathon training builds aerobic endurance through long slow runs."),
    ("k4", "Sleep of seven to nine hours improves recovery and hormone balance."),
    ("k5", "A deadlift works the hamstrings, glutes and lower back."),
    ("k6", "Stretching after exercise may reduce stiffness and improve flexibility."),
]
QUERIES = [
    "how do I build muscle with protein",
    "improve running endurance",
    "which exercise trains hamstrings",
    "how much sleep for recovery",
]


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings
    from app.db.schema_check import BACKEND_DIR
    from app.rag.chunker import Chunk
    from app.rag.pg_vector_store import PgVectorStore
    from app.rag.vector_store import KNOWLEDGE_COLLECTION, USER_COLLECTION, VectorStore

    engine = create_engine(URL, future=True)
    with engine.begin() as conn:
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

    chroma_dir = str(tmp_path_factory.mktemp("chroma"))
    chroma = VectorStore(persist_dir=chroma_dir)
    chunks = [
        Chunk(i, t, {"doc_id": i, "source": "kb.md", "page": -1, "chunk_index": 0})
        for i, t in CORPUS
    ]
    chroma.add_chunks(KNOWLEDGE_COLLECTION, chunks)
    owned = [
        Chunk(f"o{n}", t, {"doc_id": "mine", "owner_id": "u1", "source": "p.pdf", "chunk_index": n})
        for n, (_, t) in enumerate(CORPUS[:3])
    ]
    chroma.add_chunks(USER_COLLECTION, owned, "u1")

    # Run the real migration script (apply mode) against the disposable database.
    spec = importlib.util.spec_from_file_location(
        "migrate_chroma_to_pgvector",
        Path(BACKEND_DIR) / "scripts" / "migrate_chroma_to_pgvector.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import app.db.session as session_module

    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    original_factory = session_module.SessionLocal
    session_module.SessionLocal = sessions
    try:
        assert module.migrate(chroma_dir, apply=True, dimension=384) == 0
        assert module.verify(chroma_dir, 384) == 0
        # Idempotent: a second run changes nothing.
        assert module.migrate(chroma_dir, apply=True, dimension=384) == 0
    finally:
        session_module.SessionLocal = original_factory

    pg = PgVectorStore(session_factory=sessions)
    yield chroma, pg
    engine.dispose()


def test_dimension_is_preserved(stores) -> None:
    from app.rag.vector_store import KNOWLEDGE_COLLECTION

    chroma, pg = stores
    assert chroma.embedding_dimension() == 384
    assert pg.collection_info(KNOWLEDGE_COLLECTION)["dimension"] == 384


@pytest.mark.parametrize("query", QUERIES)
def test_ranking_and_distances_match_chroma(stores, query) -> None:
    from app.rag.vector_store import KNOWLEDGE_COLLECTION

    chroma, pg = stores
    expected = chroma.query(KNOWLEDGE_COLLECTION, query, n_results=4)
    # PgVectorStore embeds the *query* itself with the configured provider (local
    # ONNX here), exactly what runs in production with the remote provider.
    actual = pg.query(KNOWLEDGE_COLLECTION, query, n_results=4)
    assert [h.id for h in actual] == [h.id for h in expected]
    for a, e in zip(actual, expected, strict=True):
        assert a.distance == pytest.approx(e.distance, abs=1e-4)
        assert a.text == e.text and a.metadata["source"] == e.metadata["source"]


def test_owner_scope_and_filter_parity(stores) -> None:
    from app.rag.vector_store import USER_COLLECTION

    chroma, pg = stores
    c = chroma.query(USER_COLLECTION, "protein muscle", 5, owner_id="u1", where={"doc_id": "mine"})
    p = pg.query(USER_COLLECTION, "protein muscle", 5, owner_id="u1", where={"doc_id": "mine"})
    assert [h.id for h in p] == [h.id for h in c]
    assert pg.query(USER_COLLECTION, "protein muscle", 5, owner_id="other") == []
    assert chroma.query(USER_COLLECTION, "protein muscle", 5, owner_id="other") == []
