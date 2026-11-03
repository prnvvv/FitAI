"""Durable ingestion: checkpoints, restart recovery, idempotency, duplicate prevention."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ingestion_job import IngestionJob
from app.rag.chunker import chunk_document
from app.rag.loader import load_file
from app.rag.vector_store import VectorStoreError
from app.services.document_service import DocumentService
from app.services.document_storage import DocumentStorage
from app.services.ingestion_jobs import (
    JobDeps,
    claim_next,
    enqueue,
    enqueue_orphans,
    process_job,
)
from tests.pdf_factory import make_pdf

PAGES = [f"Page {i} " + ("squats and deadlifts build strength. " * 6) for i in range(1, 8)]


class MemStorage(DocumentStorage):
    backend_name = "mem"
    is_configured = True

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes, content_type: str) -> None:
        self.files[key] = data

    def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def read(self, key: str) -> bytes:
        return self.files[key]


class FakeStore:
    """Records chunks like a vector store; can be told to fail on the Nth add."""

    def __init__(self, fail_on_call: int | None = None) -> None:
        self.rows: dict[str, dict] = {}
        self.calls = 0
        self.deletes = 0
        self.fail_on_call = fail_on_call

    def add_chunks(self, collection, chunks, owner_id=None) -> int:
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise VectorStoreError("simulated embedding outage")
        for c in chunks:
            self.rows[c.id] = {"text": c.text, "meta": c.metadata}
        return len(chunks)

    def delete_document(self, collection, doc_id, owner_id=None) -> int:
        self.deletes += 1
        gone = [k for k, v in self.rows.items() if v["meta"].get("doc_id") == doc_id]
        for k in gone:
            del self.rows[k]
        return len(gone)


@pytest.fixture
def env(db_session):
    storage = MemStorage()
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, expire_on_commit=False)

    def make(store: FakeStore | None = None, pages_per_batch: int = 2) -> JobDeps:
        return JobDeps(factory, storage, store or FakeStore(), pages_per_batch)

    def upload(data: bytes, name: str = "plan.pdf", ctype: str = "application/pdf") -> Document:
        doc, _ = DocumentService(db_session, storage=storage).create(
            uuid.uuid4(), name, ctype, data, trigger_ingestion=False
        )
        return doc

    return db_session, storage, make, upload


def _claim(deps: JobDeps, now: datetime | None = None) -> uuid.UUID | None:
    session = deps.session_factory()
    try:
        return claim_next(session, now=now)
    finally:
        session.close()


def test_pdf_is_ingested_in_bounded_batches_and_marked_indexed(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    deps = make(pages_per_batch=2)

    seen: list[int] = []
    job_id = _claim(deps)
    assert job_id == job.id
    assert process_job(deps, job_id, on_batch=seen.append) == "succeeded"

    assert seen == [2, 4, 6, 7]  # 7 pages, 2 per batch, checkpoint after each
    db.refresh(doc)
    assert doc.status == DocumentStatus.INDEXED and doc.completed_at is not None
    assert deps.store.rows  # chunks written


def test_sliced_ingestion_equals_whole_document_ingestion(env, tmp_path) -> None:
    """Resumable slices must produce exactly the chunks the one-shot pipeline does."""
    db, _, make, upload = env
    data = make_pdf(PAGES)
    doc = upload(data)
    enqueue(db, doc)
    deps = make(pages_per_batch=3)
    process_job(deps, _claim(deps))

    path = tmp_path / "plan.pdf"
    path.write_bytes(data)
    whole = chunk_document(load_file(path), str(doc.id), {}, 1000, 150, "")
    sliced = {k.split(":")[-1]: v["text"] for k, v in deps.store.rows.items()}
    assert sliced == {c.id.split(":")[-1]: c.text for c in whole}


def test_restart_resumes_from_checkpoint_without_losing_or_duplicating(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    store = FakeStore(fail_on_call=3)  # the third batch write fails mid-document
    deps = make(store, pages_per_batch=2)

    assert process_job(deps, _claim(deps)) == "queued"  # transient: back on the queue
    db.expire_all()
    job = db.get(IngestionJob, job.id)
    assert job.next_unit == 4 and job.status == "queued"  # two batches were checkpointed
    assert db.get(Document, doc.id).status == DocumentStatus.PROCESSING
    written_before = set(store.rows)

    # backoff elapsed -> a fresh worker claims it and resumes at page 5
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert _claim(deps, later) == job.id
    store.fail_on_call = None
    assert process_job(deps, job.id) == "succeeded"

    db.expire_all()
    assert db.get(Document, doc.id).status == DocumentStatus.INDEXED
    assert written_before <= set(store.rows)  # nothing lost
    indices = sorted(int(k.split(":")[-1]) for k in store.rows)
    assert indices == list(range(len(indices)))  # contiguous, no duplicates
    assert store.deletes == 1  # the stale-chunk sweep ran once, at the fresh start only


def test_process_killed_mid_run_is_recovered_after_the_lease_expires(env) -> None:
    """Simulates a Render restart: the worker dies right after a checkpoint."""
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    store = FakeStore()
    deps = make(store, pages_per_batch=2)
    job_id = _claim(deps)

    class Killed(BaseException):
        """BaseException: not caught by the processor, like SIGKILL."""

    def die_after_second_batch(unit: int) -> None:
        if unit >= 4:
            raise Killed

    with pytest.raises(Killed):
        process_job(deps, job_id, on_batch=die_after_second_batch)

    db.expire_all()
    stuck = db.get(IngestionJob, job.id)
    assert stuck.status == "running" and stuck.next_unit == 4  # exactly as a crash leaves it

    assert _claim(deps) is None  # lease still valid: not stolen from a live worker
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _claim(deps, future) == job.id  # restart: lease expired -> reclaimed
    assert process_job(deps, job.id) == "succeeded"
    db.expire_all()
    assert db.get(Document, doc.id).status == DocumentStatus.INDEXED
    indices = sorted(int(k.split(":")[-1]) for k in store.rows)
    assert indices == list(range(len(indices)))


def test_enqueue_is_idempotent_one_job_per_document(env) -> None:
    db, _, _, upload = env
    doc = upload(make_pdf(PAGES))
    a, b = enqueue(db, doc), enqueue(db, doc)
    assert a.id == b.id
    assert len(list(db.scalars(select(IngestionJob)))) == 1


def test_running_job_is_never_reset_by_a_retry(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    enqueue(db, doc)
    _claim(make())  # now running
    assert enqueue(db, doc, reset=True).status == "running"


def test_attempts_are_bounded_then_the_document_is_failed(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    deps = make(FakeStore(fail_on_call=1))
    when = datetime.now(timezone.utc)
    for _ in range(job.max_attempts):
        when += timedelta(hours=1)
        job_id = _claim(deps, when)
        assert job_id == job.id
        deps.store.calls = 0  # fail on the first add of every attempt
        process_job(deps, job_id)
    db.expire_all()
    assert db.get(IngestionJob, job.id).status == "failed"
    assert db.get(Document, doc.id).status == DocumentStatus.FAILED


def test_unreadable_pdf_fails_permanently_with_a_readable_reason(env) -> None:
    db, _, make, upload = env
    doc = upload(b"%PDF-1.4 this is not really a pdf")
    enqueue(db, doc)
    deps = make()
    assert process_job(deps, _claim(deps)) == "failed"
    db.expire_all()
    assert db.get(Document, doc.id).status == DocumentStatus.FAILED
    assert db.get(Document, doc.id).error_message


def test_text_free_pdf_is_failed_not_reported_as_success(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(["", ""]))
    enqueue(db, doc)
    deps = make()
    assert process_job(deps, _claim(deps)) == "failed"
    db.expire_all()
    assert "readable text" in (db.get(Document, doc.id).error_message or "")


def test_storage_outage_is_transient_and_keeps_the_job(env) -> None:
    db, storage, make, upload = env
    doc = upload(make_pdf(PAGES))
    job = enqueue(db, doc)
    del storage.files[doc.storage_key]
    deps = make()
    assert process_job(deps, _claim(deps)) == "queued"
    db.expire_all()
    assert db.get(IngestionJob, job.id).last_error


def test_orphaned_pending_documents_get_a_job(env) -> None:
    db, _, _, upload = env
    doc = upload(make_pdf(PAGES))  # uploaded, but the request died before enqueue
    assert enqueue_orphans(db) == 1
    assert enqueue_orphans(db) == 0  # idempotent
    assert db.scalar(select(IngestionJob).where(IngestionJob.document_id == doc.id))


def test_deleting_the_document_mid_ingestion_cleans_up_vectors(env) -> None:
    db, _, make, upload = env
    doc = upload(make_pdf(PAGES))
    job_pk = enqueue(db, doc).id
    store = FakeStore()
    deps = make(store, pages_per_batch=2)
    job_id = _claim(deps)
    state = {"done": False}

    def delete_after_first_batch(_unit: int) -> None:
        if not state["done"]:
            state["done"] = True
            s = deps.session_factory()
            s.delete(s.get(Document, doc.id))
            s.commit()
            s.close()

    process_job(deps, job_id, on_batch=delete_after_first_batch)
    db.expire_all()
    assert db.scalar(select(IngestionJob).where(IngestionJob.id == job_pk)) is None
    assert not store.rows  # no orphan vectors left behind


def test_temp_files_are_removed(env, tmp_path, monkeypatch) -> None:
    import tempfile

    db, _, make, upload = env
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    doc = upload(make_pdf(PAGES))
    enqueue(db, doc)
    deps = make()
    process_job(deps, _claim(deps))
    assert list(tmp_path.glob("fitai-ingest-*")) == []
