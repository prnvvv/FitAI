"""Reconcile the document library (PostgreSQL) with the ChromaDB index.

Read-only by default: ``audit_library`` classifies every document against the
vectors actually stored for it and never mutates anything. ``repair_library``
re-runs ingestion through the normal handler and removes orphan vectors, but
only after a timestamped copy of the Chroma persist directory exists.

No document content is ever copied into a report: only ids, file names, counts
and short, human-readable failure reasons.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.rag.embeddings import embedding_model_name
from app.rag.vector_store import USER_COLLECTION, VectorStore, VectorStoreError
from app.repositories.document_repository import DocumentRepository

log = logging.getLogger(__name__)

Finding = Literal[
    "OK",
    "OK_EMPTY",
    "MISSING",
    "STUCK",
    "FAILED",
    "DUPLICATE",
    "UNREADABLE_INDEX",
]
#: Findings that make the audit exit non-zero.
PROBLEM_FINDINGS = ("MISSING", "STUCK", "FAILED", "UNREADABLE_INDEX")
#: Characters taken from a document's own first chunk for the retrieval proof.
SNIPPET_CHARS = 160


@dataclass
class DocumentFinding:
    """Audit result for one document. Contains no document text."""

    document_id: str
    user_id: str
    filename: str
    kind: str
    status: str
    finding: Finding
    vectors: int
    reason: str | None = None
    note: str | None = None
    duplicate_of: str | None = None
    retrieval_ok: bool | None = None


@dataclass(frozen=True)
class OrphanVector:
    """A stored vector whose document no longer has a database row."""

    doc_id: str
    owner_id: str
    vectors: int


@dataclass
class AuditReport:
    """Everything the CLI prints, and everything ``repair_library`` acts on."""

    collection: str
    persist_dir: str | None
    embedding_model: str | None
    stored_embedding_model: str | None
    total_vectors: int
    expected_dimension: int | None
    stored_dimension: int | None
    rows: list[DocumentFinding] = field(default_factory=list)
    orphans: list[OrphanVector] = field(default_factory=list)
    scoped_user_id: str | None = None

    @property
    def wrong_embedding(self) -> bool:
        """True when the collection was built with a different embedding model."""
        if self.stored_embedding_model and self.stored_embedding_model != self.embedding_model:
            return True
        return bool(
            self.expected_dimension is not None
            and self.stored_dimension is not None
            and self.expected_dimension != self.stored_dimension
        )

    @property
    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in self.rows:
            result[row.finding] = result.get(row.finding, 0) + 1
        return result

    @property
    def problems(self) -> list[DocumentFinding]:
        wrong = "UNREADABLE_INDEX" if self.wrong_embedding else None
        return [row for row in self.rows if row.finding in PROBLEM_FINDINGS or row.finding == wrong]

    @property
    def duplicates(self) -> list[DocumentFinding]:
        return [row for row in self.rows if row.finding == "DUPLICATE"]

    def repairable(self) -> list[DocumentFinding]:
        """Rows whose ingestion should be re-run: missing, stuck and failed."""
        return [row for row in self.rows if row.finding in ("MISSING", "STUCK", "FAILED")]


def _kind(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".") or "none"


def _is_empty_text(document: Document) -> bool:
    metadata = document.ingestion_metadata or {}
    return isinstance(metadata, dict) and bool(metadata.get("note"))


def _duplicates(documents: list[Document]) -> dict[UUID, UUID]:
    """Map each duplicate row to the id of the row that kept its bytes."""
    first_by_hash: dict[tuple[str, str], UUID] = {}
    duplicates: dict[UUID, UUID] = {}
    for document in documents:
        if not document.content_hash:
            continue
        key = (str(document.user_id), document.content_hash)
        original = first_by_hash.setdefault(key, document.id)
        if original != document.id:
            duplicates[document.id] = original
    return duplicates


def audit_library(
    db: Session,
    store: VectorStore,
    *,
    user_id: UUID | str | None = None,
    timeout_minutes: int = 30,
    verify_retrieval: bool = True,
    now: datetime | None = None,
) -> AuditReport:
    """Compare every document row with the vectors stored for it.

    Read-only: no row, file or vector is modified. ``user_id`` scopes the audit
    to one user; without it every document is checked.
    """
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(minutes=timeout_minutes)
    scoped = UUID(str(user_id)) if user_id else None
    documents = DocumentRepository(db).list_all(scoped)
    duplicates = _duplicates(documents)

    info = store.collection_info(USER_COLLECTION)
    try:
        expected_dimension: int | None = store.embedding_dimension()
    except VectorStoreError:
        log.warning("audit_embedding_dimension_failed", exc_info=True)
        expected_dimension = None

    report = AuditReport(
        collection=info["name"],
        persist_dir=store.persist_dir,
        embedding_model=embedding_model_name(),
        stored_embedding_model=info["embedding_model"],
        total_vectors=int(info["count"]),
        expected_dimension=expected_dimension,
        stored_dimension=info["dimension"],
        scoped_user_id=str(scoped) if scoped else None,
    )

    known: set[tuple[str, str]] = set()
    for document in documents:
        owner_id = str(document.user_id)
        known.add((owner_id, str(document.id)))
        vectors = store.document_vector_count(USER_COLLECTION, str(document.id), owner_id)
        reason = document.error_message
        note = None

        if document.status == DocumentStatus.FAILED:
            finding: Finding = "FAILED"
        elif document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
            created = document.created_at
            is_stuck = created is not None and _as_utc(created) < cutoff
            finding = "STUCK" if is_stuck else "OK"
        elif vectors == 0:
            finding = "OK_EMPTY" if _is_empty_text(document) else "MISSING"
            note = "No readable text found" if finding == "OK_EMPTY" else None
        else:
            finding = "OK"

        original = duplicates.get(document.id)
        if original is not None and finding in ("OK", "OK_EMPTY"):
            finding = "DUPLICATE"

        report.rows.append(
            DocumentFinding(
                document_id=str(document.id),
                user_id=owner_id,
                filename=document.filename,
                kind=_kind(document.filename),
                status=document.status.value
                if isinstance(document.status, DocumentStatus)
                else str(document.status),
                finding=finding,
                vectors=vectors,
                reason=reason,
                note=note,
                duplicate_of=str(original) if original else None,
            )
        )

    _attach_retrieval_proof(store, report, documents, verify_retrieval)
    _collect_orphans(store, report, known)
    return report


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _attach_retrieval_proof(
    store: VectorStore,
    report: AuditReport,
    documents: list[Document],
    verify_retrieval: bool,
) -> None:
    """Query each ready document with its own text and record whether it returns."""
    if not verify_retrieval:
        return
    by_id = {str(row.document_id): row for row in report.rows}
    for document in documents:
        row = by_id.get(str(document.id))
        if row is None or row.vectors == 0:
            continue
        texts = store.stored_chunk_texts(USER_COLLECTION, str(document.id), str(document.user_id))
        snippet = next((text.strip() for text in texts if text and text.strip()), "")
        if not snippet:
            continue
        try:
            hits = store.query(
                USER_COLLECTION,
                snippet[:SNIPPET_CHARS],
                n_results=5,
                owner_id=str(document.user_id),
            )
        except VectorStoreError:
            log.warning("audit_retrieval_failed doc_id=%s", document.id, exc_info=True)
            row.retrieval_ok = False
            continue
        row.retrieval_ok = any(hit.metadata.get("doc_id") == str(document.id) for hit in hits)


def _collect_orphans(store: VectorStore, report: AuditReport, known: set[tuple[str, str]]) -> None:
    """Group stored vectors whose (owner_id, doc_id) has no database row."""
    counts: dict[tuple[str, str], int] = {}
    for _chunk_id, doc_id, owner_id in store.all_chunk_owners(USER_COLLECTION):
        if not doc_id:
            log.error("vector_without_doc_id", owner_id=owner_id)
            continue
        if (owner_id, doc_id) in known:
            continue
        counts[(owner_id, doc_id)] = counts.get((owner_id, doc_id), 0) + 1
    report.orphans = [
        OrphanVector(doc_id=doc_id, owner_id=owner_id, vectors=count)
        for (owner_id, doc_id), count in sorted(counts.items())
    ]


def backup_persist_dir(persist_dir: str | Path, *, now: datetime | None = None) -> Path:
    """Copy the Chroma persist directory to a timestamped sibling; return it."""
    source = Path(persist_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"Chroma persist directory not found: {source}")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.name}.backup-{stamp}")
    shutil.copytree(source, target)
    log.info("chroma_backup_created path=%s", target)
    return target


def repair_library(
    db: Session,
    store: VectorStore,
    report: AuditReport,
    *,
    ingestion: object | None = None,
    storage: object | None = None,
    backup: bool = True,
) -> list[str]:
    """Re-index missing/stuck/failed documents and drop orphan vectors.

    Ingestion is re-run through ``DocumentService.retry``, so the same database
    row and stored file are reused; nothing is deleted from the database. Orphan
    vectors are removed only after the persist directory has been backed up.
    """
    from app.services.document_service import DocumentService

    actions: list[str] = []
    backup_path: Path | None = None
    if backup and report.persist_dir:
        backup_path = backup_persist_dir(report.persist_dir)
        actions.append(f"backup: {backup_path}")

    service: object | None = None
    if ingestion is not None:
        service = DocumentService(db, storage=storage, ingestion=ingestion)
    for row in report.repairable():
        if service is None:
            actions.append(f"skipped reindex {row.filename}: no ingestion handler")
            continue
        try:
            document = service.retry(UUID(row.user_id), UUID(row.document_id))
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the audit
            log.warning("audit_reindex_failed doc_id=%s", row.document_id, exc_info=True)
            actions.append(f"reindex failed {row.filename}: {type(exc).__name__}")
            continue
        state = getattr(document.status, "value", str(document.status))
        actions.append(f"reindexed {row.filename}: status={state}")

    for orphan in report.orphans:
        if backup_path is None:
            actions.append(f"skipped orphan removal {orphan.doc_id}: no backup taken")
            continue
        removed = store.delete_document_pair(orphan.doc_id, orphan.owner_id)
        actions.append(f"removed {removed} orphan vectors for {orphan.doc_id}")
    return actions
