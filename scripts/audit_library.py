"""Audit the document library against the ChromaDB index.

Read-only by default:

    python -m scripts.audit_library
    python -m scripts.audit_library --user <user-id>

With ``--fix`` the script backs up the Chroma persist directory, re-runs
ingestion for missing/stuck/failed documents through the normal handler and
removes orphan vectors. It never deletes database rows or stored files, never
touches another user's data, and never removes duplicates (they are reported).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.rag.library_audit import (  # noqa: E402
    AuditReport,
    audit_library,
    repair_library,
)
from app.rag.pipeline import IngestionPipeline  # noqa: E402
from app.rag.vector_store import VectorStore  # noqa: E402

log = logging.getLogger("audit_library")


def _print_report(report: AuditReport) -> None:
    print(f"collection        : {report.collection}")
    print(f"persist dir       : {report.persist_dir}")
    print(f"embedding model   : {report.embedding_model}")
    print(f"stored model      : {report.stored_embedding_model}")
    print(
        f"dimensions        : stored={report.stored_dimension} expected={report.expected_dimension}"
    )
    print(f"total vectors     : {report.total_vectors}")
    if report.scoped_user_id:
        print(f"scoped to user    : {report.scoped_user_id}")
    if report.wrong_embedding:
        print("WRONG EMBEDDING   : collection was built with a different embedding model")
    print("")

    header = f"{'DOCUMENT':<34} {'KIND':<6} {'STATUS':<11} {'FINDING':<10} {'VECS':>4} {'RETRIEVE':>8}"
    print(header)
    print("-" * len(header))
    for row in report.rows:
        retrieval = {True: "pass", False: "FAIL", None: "-"}[row.retrieval_ok]
        print(
            f"{row.filename[:34]:<34} {row.kind:<6} {row.status:<11} {row.finding:<10} "
            f"{row.vectors:>4} {retrieval:>8}"
        )
        if row.reason:
            print(f"{'':<34} reason: {row.reason}")
        if row.note:
            print(f"{'':<34} note: {row.note}")
        if row.duplicate_of:
            print(f"{'':<34} duplicate of {row.duplicate_of}")

    print("")
    counts = report.counts
    print("counts            : " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"))
    if report.orphans:
        print("orphan vectors    :")
        for orphan in report.orphans:
            print(f"  doc_id={orphan.doc_id} owner_id={orphan.owner_id} vectors={orphan.vectors}")
    else:
        print("orphan vectors    : none")
    if report.duplicates:
        print("duplicates        : reported only, never removed")
    else:
        print("duplicates        : none")

    retrieval_failures = [row for row in report.rows if row.retrieval_ok is False]
    if retrieval_failures:
        print("retrieval failures :")
        for row in retrieval_failures:
            print(f"  {row.filename} ({row.document_id})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default=None, help="Only audit this user id")
    parser.add_argument("--fix", action="store_true", help="Repair what the audit found")
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=30,
        help="Queued/processing documents older than this are STUCK",
    )
    parser.add_argument(
        "--skip-retrieval", action="store_true", help="Skip the per-document retrieval proof"
    )
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    db = SessionLocal()
    store = VectorStore(persist_dir=settings.chromadb_persist_dir)
    try:
        report = audit_library(
            db,
            store,
            user_id=args.user,
            timeout_minutes=args.timeout_minutes,
            verify_retrieval=not args.skip_retrieval,
        )
        _print_report(report)

        if args.fix:
            pipeline = IngestionPipeline(store)
            print("")
            print("repairs:")
            for action in repair_library(db, store, report, ingestion=pipeline):
                print(f"  {action}")
            print("")
            print("re-auditing:")
            after = audit_library(
                db,
                store,
                user_id=args.user,
                timeout_minutes=args.timeout_minutes,
                verify_retrieval=not args.skip_retrieval,
            )
            _print_report(after)
            report = after

        if report.problems or report.orphans:
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())