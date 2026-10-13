"""CLI entrypoint to ingest curated knowledge-base documents into ChromaDB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The app package lives under backend/; make it importable when this script is
# run as a module from the repository root.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.rag.pipeline import IngestionPipeline  # noqa: E402
from app.rag.vector_store import VectorStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest curated fitness knowledge into ChromaDB."
    )
    parser.add_argument(
        "--dir", default="knowledge_base", help="Directory of curated documents"
    )
    args = parser.parse_args(argv)

    store = VectorStore()
    pipeline = IngestionPipeline(store)
    results = pipeline.ingest_curated_directory(args.dir)

    failed = 0
    for r in results:
        print(
            f"{r.source}: status={r.status} chunks={r.chunks_indexed} "
            f"attempts={r.attempts} error={r.error}"
        )
        if r.status == "failed":
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
