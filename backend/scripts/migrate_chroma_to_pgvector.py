"""Copy existing ChromaDB vectors into the pgvector ``vector_chunks`` table.

SAFE BY DEFAULT
    * Dry run unless ``--apply`` is passed: reads Chroma, validates, reports, writes nothing.
    * Chroma is opened read-only in practice (only ``get``); nothing in it is modified or deleted.
    * Existing embeddings are copied as-is (no re-embedding), so dimensions and
      distances are preserved exactly.
    * Upserts are idempotent: re-running after a partial failure is safe.
    * Nothing is ever deleted from either side.

Usage (see docs/chroma-to-pgvector-migration.md for the full procedure)::

    DATABASE_URL=postgresql+psycopg2://...  python scripts/migrate_chroma_to_pgvector.py \
        --chroma-dir ./chroma_data                      # dry run
    ... --apply                                          # perform the copy
    ... --verify                                         # compare counts/dimension/sample queries

Take a backup of both stores first; this script does not do it for you.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.vector_store import (  # noqa: E402
    CONTINUITY_COLLECTION,
    KNOWLEDGE_COLLECTION,
    USER_COLLECTION,
)

COLLECTIONS = (KNOWLEDGE_COLLECTION, USER_COLLECTION, CONTINUITY_COLLECTION)
PAGE = 200


def _open_chroma(path: str):  # noqa: ANN202
    import chromadb
    from chromadb.config import Settings

    if not Path(path).exists():
        raise SystemExit(f"Chroma directory not found: {path}")
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))


def _existing_names(client) -> set[str]:  # noqa: ANN001
    return {c if isinstance(c, str) else c.name for c in client.list_collections()}


def _pages(col, total: int):  # noqa: ANN001, ANN202
    for offset in range(0, total, PAGE):
        yield col.get(limit=PAGE, offset=offset, include=["documents", "metadatas", "embeddings"])


def migrate(chroma_dir: str, apply: bool, dimension: int) -> int:
    from app.rag.pg_vector_store import PgVectorStore

    client = _open_chroma(chroma_dir)
    names = _existing_names(client)
    store = PgVectorStore(embedding_function=lambda t: [], dimension=dimension) if apply else None
    problems = 0
    for name in COLLECTIONS:
        if name not in names:
            print(f"[skip] {name}: not present in Chroma")
            continue
        col = client.get_collection(name)
        total = col.count()
        copied = bad = 0
        for page in _pages(col, total):
            ids = list(page["ids"])
            texts = [t or "" for t in page["documents"]]
            metas = [dict(m or {}) for m in page["metadatas"]]
            embs = [list(map(float, e)) for e in page["embeddings"]]
            good = [i for i, e in enumerate(embs) if len(e) == dimension]
            bad += len(ids) - len(good)
            if apply and good and store is not None:
                store.add_embedded(
                    name,
                    [ids[i] for i in good],
                    [texts[i] for i in good],
                    [metas[i] for i in good],
                    [embs[i] for i in good],
                )
            copied += len(good)
        verb = "copied" if apply else "would copy"
        print(f"[{name}] chroma={total} {verb}={copied} wrong_dimension={bad}")
        problems += bad
    if problems:
        print(f"ERROR: {problems} vector(s) do not have dimension {dimension}; not migrated.")
    print("DRY RUN: nothing was written. Re-run with --apply." if not apply else "Done.")
    return 1 if problems else 0


def verify(chroma_dir: str, dimension: int) -> int:
    from app.rag.pg_vector_store import PgVectorStore

    client = _open_chroma(chroma_dir)
    names = _existing_names(client)
    store = PgVectorStore(embedding_function=lambda t: [], dimension=dimension)
    failures = 0
    for name in COLLECTIONS:
        if name not in names:
            continue
        chroma_count = client.get_collection(name).count()
        info = store.collection_info(name)
        ok = chroma_count == info["count"] and (
            info["count"] == 0 or info["dimension"] == dimension
        )
        failures += 0 if ok else 1
        print(
            f"[{name}] chroma={chroma_count} pgvector={info['count']} "
            f"dimension={info['dimension']} -> {'OK' if ok else 'MISMATCH'}"
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--chroma-dir", required=True)
    parser.add_argument("--dimension", type=int, default=384)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="write to pgvector")
    group.add_argument("--verify", action="store_true", help="compare counts and dimension")
    args = parser.parse_args()
    if args.verify:
        return verify(args.chroma_dir, args.dimension)
    return migrate(args.chroma_dir, args.apply, args.dimension)


if __name__ == "__main__":
    raise SystemExit(main())
