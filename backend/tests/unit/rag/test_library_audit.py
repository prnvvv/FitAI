"""Library/ChromaDB reconciliation: real Chroma directory, fake embeddings.

The Chroma client here is a real ``PersistentClient`` in a temporary directory,
so filtering, deletion and persistence are exercised for real. The embedding
function is a deterministic stub to keep the test offline and fast.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.rag.chunker import Chunk
from app.rag.library_audit import (
    audit_library,
    backup_persist_dir,
    repair_library,
)
from app.rag.pipeline import IngestionPipeline
from app.rag.vector_store import USER_COLLECTION, VectorStore


class _FakeEmbeddingFunction:
    """Deterministic 8-dimensional embedding: same text, same vector."""

    name = "fake-embedding"

    def __call__(self, input):  # noqa: A002 - matches the Chroma protocol
        vectors = []
        for text in input:
            digest = hashlib.sha256(str(text).encode("utf-8")).digest()
            vectors.append([byte / 255.0 for byte in digest[:8]])
        return vectors


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(
        persist_dir=str(tmp_path / "chroma"), embedding_function=_FakeEmbeddingFunction()
    )


def _add(store: VectorStore, doc_id: str, owner_id: str, text: str = "squat 3x10 at 80 kg") -> None:
    chunks = [
        Chunk(
            id=f"{owner_id[:8]}:{doc_id}:{index}",
            text=text,
            metadata={
                "doc_id": doc_id,
                "owner_id": owner_id,
                "source": "note.txt",
                "chunk_index": index,
            },
        )
        for index in range(2)
    ]
    store.add_chunks(USER_COLLECTION, chunks, owner_id)


def _document(
    session,
    owner_id,
    *,
    filename: str = "note.txt",
    status: DocumentStatus = DocumentStatus.INDEXED,
    content_hash: str | None = None,
    created_at: datetime | None = None,
    storage_key: str | None = None,
    note: str | None = None,
) -> Document:
    document = Document(
        id=uuid4(),
        user_id=owner_id,
        filename=filename,
        content_type="text/plain",
        size_bytes=10,
        status=status,
        content_hash=content_hash,
        storage_key=storage_key,
        storage_backend="local" if storage_key else None,
        ingestion_metadata={"note": note} if note else None,
    )
    if created_at is not None:
        document.created_at = created_at
        document.updated_at = created_at
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #


def test_indexed_document_with_vectors_is_ok(db_session, store) -> None:
    user = uuid4()
    document = _document(db_session, user)
    _add(store, str(document.id), str(user))

    report = audit_library(db_session, store)

    row = report.rows[0]
    assert row.finding == "OK"
    assert row.vectors == 2
    assert row.retrieval_ok is True
    assert report.problems == []


def test_indexed_document_without_vectors_is_missing(db_session, store) -> None:
    document = _document(db_session, uuid4())

    report = audit_library(db_session, store)

    assert report.rows[0].finding == "MISSING"
    assert [row.document_id for row in report.problems] == [str(document.id)]


def test_failed_document_is_reported_with_its_reason(db_session, store) -> None:
    document = _document(db_session, uuid4(), status=DocumentStatus.FAILED)
    document.error_message = "Couldn't read this image."
    db_session.commit()

    report = audit_library(db_session, store)

    assert report.rows[0].finding == "FAILED"
    assert report.rows[0].reason == "Couldn't read this image."


def test_queued_document_past_the_timeout_is_stuck(db_session, store) -> None:
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    _document(db_session, uuid4(), status=DocumentStatus.PROCESSING, created_at=old)

    report = audit_library(db_session, store, timeout_minutes=30)

    assert report.rows[0].finding == "STUCK"


def test_recent_queued_document_is_not_stuck(db_session, store) -> None:
    _document(db_session, uuid4(), status=DocumentStatus.PENDING)

    report = audit_library(db_session, store, timeout_minutes=30)

    assert report.rows[0].finding == "OK"


def test_document_ready_with_an_empty_text_note_is_not_missing(db_session, store) -> None:
    _document(db_session, uuid4(), filename="wall.jpg", note="No readable text found")

    report = audit_library(db_session, store)

    assert report.rows[0].finding == "OK_EMPTY"
    assert report.rows[0].note == "No readable text found"
    assert report.problems == []


def test_same_bytes_twice_are_reported_as_duplicates(db_session, store) -> None:
    user = uuid4()
    first = _document(db_session, user, filename="a.txt", content_hash="deadbeef")
    second = _document(db_session, user, filename="b.txt", content_hash="deadbeef")
    _add(store, str(first.id), str(user))
    _add(store, str(second.id), str(user))

    report = audit_library(db_session, store)

    duplicates = {row.document_id: row.duplicate_of for row in report.duplicates}
    assert duplicates == {str(second.id): str(first.id)}


def test_orphan_vectors_are_detected(db_session, store) -> None:
    _add(store, "deleted-doc", str(uuid4()))

    report = audit_library(db_session, store)

    assert [(o.doc_id, o.vectors) for o in report.orphans] == [("deleted-doc", 2)]


def test_wrong_embedding_model_is_detected(db_session, store) -> None:
    store._col(USER_COLLECTION).modify(metadata={"embedding_model": "some-other-model"})

    report = audit_library(db_session, store)

    assert report.wrong_embedding is True


# --------------------------------------------------------------------------- #
# Ownership isolation
# --------------------------------------------------------------------------- #


def test_users_cannot_reach_each_others_vectors(db_session, store) -> None:
    alice, bob = uuid4(), uuid4()
    alice_doc = _document(db_session, alice, filename="alice.txt")
    bob_doc = _document(db_session, bob, filename="bob.txt")
    _add(store, str(alice_doc.id), str(alice), "alice private note")
    _add(store, str(bob_doc.id), str(bob), "bob private note")

    alice_report = audit_library(db_session, store, user_id=alice)
    bob_report = audit_library(db_session, store, user_id=bob)

    assert [row.filename for row in alice_report.rows] == ["alice.txt"]
    assert [row.filename for row in bob_report.rows] == ["bob.txt"]

    bob_hits = store.query(USER_COLLECTION, "alice private note", n_results=5, owner_id=str(bob))
    assert all(hit.metadata.get("owner_id") == str(bob) for hit in bob_hits)


def test_deleting_a_document_removes_its_vectors(db_session, store) -> None:
    user = uuid4()
    document = _document(db_session, user)
    _add(store, str(document.id), str(user))

    removed = store.delete_document(USER_COLLECTION, str(document.id), str(user))
    report = audit_library(db_session, store)

    assert removed == 2
    assert store.document_vector_count(USER_COLLECTION, str(document.id), str(user)) == 0
    assert report.rows[0].finding == "MISSING"
    assert report.orphans == []


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #


def test_repair_backs_up_then_reindexes_the_missing_document(db_session, store, tmp_path) -> None:
    user = uuid4()
    source = tmp_path / "note.txt"
    source.write_text("Squat 3x10 at 80 kg", encoding="utf-8")
    _document(db_session, user, storage_key=str(source))

    class _Storage:
        backend_name = "local"

        def read(self, key: str) -> bytes:
            return Path(key).read_bytes()

    pipeline = IngestionPipeline(store)
    before = audit_library(db_session, store)
    assert before.rows[0].finding == "MISSING"

    actions = repair_library(db_session, store, before, ingestion=pipeline, storage=_Storage())

    after = audit_library(db_session, store)
    assert any(action.startswith("backup:") for action in actions)
    assert after.rows[0].finding == "OK"
    assert after.rows[0].vectors >= 1
    assert after.rows[0].retrieval_ok is True
    assert list(tmp_path.glob("chroma.backup-*"))


def test_backup_copies_everything(tmp_path: Path) -> None:
    source = tmp_path / "chroma"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"payload")

    target = backup_persist_dir(source, now=datetime(2026, 10, 14, tzinfo=timezone.utc))

    assert (target / "chroma.sqlite3").read_bytes() == b"payload"
    assert target.name == "chroma.backup-20261014T000000Z"


def test_orphans_are_only_removed_after_a_backup(db_session, store) -> None:
    _add(store, "ghost-doc", str(uuid4()))
    report = audit_library(db_session, store)

    actions = repair_library(db_session, store, report, ingestion=None)

    assert any("backup:" in action for action in actions)
    assert any("orphan vectors" in action for action in actions)
    assert audit_library(db_session, store).orphans == []
