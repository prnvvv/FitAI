"""pgvector-backed vector store with the same contract as the Chroma ``VectorStore``.

All vectors live in one table, ``vector_chunks``, keyed by ``(collection, id)``.
The collections, owner scoping, metadata filters and cosine-distance semantics
mirror ``app.rag.vector_store.VectorStore`` so the retriever, ingestion pipeline
and continuity store work unchanged on either backend.

Safety properties:

* Owner-scoped collections always filter on ``owner_id`` (a missing owner raises
  ``PermissionError`` exactly like the Chroma store).
* Every identifier that reaches SQL is a bound parameter; metadata keys are
  validated against a strict pattern before being used as JSON paths.
* Writes are idempotent upserts and are embedded/inserted in bounded batches.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .chunker import Chunk
from .embeddings import EMBEDDING_NAME, embed_texts
from .vector_store import (
    _OWNER_SCOPED,
    CONTINUITY_COLLECTION,
    KNOWLEDGE_COLLECTION,
    USER_COLLECTION,
    FilterDict,
    SearchHit,
    VectorStoreError,
)

log = logging.getLogger(__name__)

_BATCH = 50
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_COLLECTIONS = (KNOWLEDGE_COLLECTION, USER_COLLECTION, CONTINUITY_COLLECTION)
_COMPARE = {"$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}


def vector_literal(vector: Sequence[float]) -> str:
    """Render a vector in pgvector's text input format."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class _Params:
    """Collects bound parameters with unique names."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def add(self, value: Any) -> str:
        name = f"p{len(self.values)}"
        self.values[name] = value
        return f":{name}"


def _scalar_sql(value: Any, params: _Params) -> tuple[str, str]:
    """Return ``(json-extract expression suffix, bound param)`` typed for ``value``."""
    if isinstance(value, bool):
        return "::boolean", f"CAST({params.add(value)} AS boolean)"
    if isinstance(value, int | float):
        return "::double precision", f"CAST({params.add(float(value))} AS double precision)"
    return "", params.add(str(value))


def _field(key: str, cast: str) -> str:
    if not _KEY_RE.match(key):
        raise ValueError(f"invalid metadata key {key!r}")
    return f"(metadata ->> '{key}'){cast}"


def translate_filter(where: FilterDict | None, params: _Params | None = None) -> tuple[str, dict]:
    """Translate a Chroma ``where`` filter into a SQL predicate and bound params.

    Supports equality, ``$eq $ne $gt $gte $lt $lte $in $nin`` and ``$and``/``$or``.
    Unknown operators raise ``ValueError`` rather than being silently ignored: a
    dropped filter would widen results (a privacy risk for owner scoping).
    """
    params = params or _Params()
    if not where:
        return "TRUE", params.values
    return _node(where, params), params.values


def _node(node: FilterDict, params: _Params) -> str:
    parts: list[str] = []
    for key, value in node.items():
        if key in ("$and", "$or"):
            if not isinstance(value, list) or not value:
                raise ValueError(f"{key} needs a non-empty list")
            joiner = " AND " if key == "$and" else " OR "
            parts.append("(" + joiner.join(_node(child, params) for child in value) + ")")
            continue
        if key.startswith("$"):
            raise ValueError(f"unsupported operator {key}")
        if isinstance(value, dict):
            for op, operand in value.items():
                parts.append(_operator(key, op, operand, params))
        else:
            parts.append(_operator(key, "$eq", value, params))
    return "(" + " AND ".join(parts) + ")" if parts else "TRUE"


def _operator(key: str, op: str, operand: Any, params: _Params) -> str:
    if op in ("$eq", "$ne"):
        cast, bound = _scalar_sql(operand, params)
        sql_op = "=" if op == "$eq" else "IS DISTINCT FROM"
        return f"{_field(key, cast)} {sql_op} {bound}"
    if op in _COMPARE:
        if isinstance(operand, bool) or not isinstance(operand, int | float):
            raise ValueError(f"{op} requires a number")
        cast, bound = _scalar_sql(operand, params)
        return f"{_field(key, cast)} {_COMPARE[op]} {bound}"
    if op in ("$in", "$nin"):
        if not isinstance(operand, list) or not operand:
            raise ValueError(f"{op} needs a non-empty list")
        pieces = []
        cast = ""
        for item in operand:
            cast, bound = _scalar_sql(item, params)
            pieces.append(bound)
        negate = "NOT " if op == "$nin" else ""
        return f"{negate}({_field(key, cast)} IN ({', '.join(pieces)}))"
    raise ValueError(f"unsupported operator {op}")


_UPSERT_SQL = """
            INSERT INTO vector_chunks
                (collection, id, owner_id, doc_id, content, metadata, embedding, embedding_model)
            VALUES (:collection, :id, :owner_id, :doc_id, :content,
                    CAST(:metadata AS jsonb), CAST(:embedding AS vector), :model)
            ON CONFLICT (collection, id) DO UPDATE SET
                owner_id = EXCLUDED.owner_id, doc_id = EXCLUDED.doc_id,
                content = EXCLUDED.content, metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model,
                updated_at = now()
            """

SessionFactory = Callable[[], AbstractContextManager[Session]]


def _default_session_factory() -> SessionFactory:
    from app.db.session import SessionLocal

    return SessionLocal


class PgVectorStore:
    """Drop-in replacement for ``VectorStore`` backed by PostgreSQL + pgvector."""

    def __init__(
        self,
        persist_dir: str | None = None,  # noqa: ARG002 - accepted for call-site parity
        client: Any = None,  # noqa: ARG002
        embedding_function: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
        session_factory: SessionFactory | None = None,
        dimension: int | None = None,
    ) -> None:
        from app.core.config import settings

        self._embed = embedding_function or embed_texts
        self._sessions = session_factory or _default_session_factory()
        self._dimension = dimension or settings.embedding_dimension
        self.persist_dir = "pgvector"

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _check_collection(name: str) -> str:
        if name not in _COLLECTIONS:
            raise ValueError(f"unknown collection {name!r}")
        return name

    @staticmethod
    def _scope(
        collection: str, owner_id: str | None, where: FilterDict | None
    ) -> FilterDict | None:
        if collection in _OWNER_SCOPED:
            if not owner_id or not owner_id.strip():
                raise PermissionError(f"owner_id is required for {collection}")
            parts = [p for p in ({"owner_id": owner_id}, where) if p]
            return parts[0] if len(parts) == 1 else {"$and": parts}
        return where or None

    def _where_sql(
        self, collection: str, owner_id: str | None, where: FilterDict | None, params: _Params
    ) -> str:
        self._check_collection(collection)
        scoped = self._scope(collection, owner_id, where)
        predicate = _node(scoped, params) if scoped else "TRUE"
        return f"collection = {params.add(collection)} AND {predicate}"

    def _run(self, action: str, fn: Callable[[Session], Any]) -> Any:
        try:
            with self._sessions() as db:
                result = fn(db)
                db.commit()
                return result
        except (SQLAlchemyError, ValueError) as exc:
            raise VectorStoreError(f"{action} failed: {type(exc).__name__}: {exc}") from exc

    def _embed_checked(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [list(v) for v in self._embed(list(texts))]
        if len(vectors) != len(texts) or any(len(v) != self._dimension for v in vectors):
            raise VectorStoreError(
                f"embedding dimension mismatch: expected {self._dimension} per vector"
            )
        return vectors

    # -- writes -------------------------------------------------------------
    def add_chunks(
        self, collection: str, chunks: Sequence[Chunk], owner_id: str | None = None
    ) -> int:
        """Idempotently upsert chunks in bounded embed+insert batches."""
        self._check_collection(collection)
        self._scope(collection, owner_id, None)
        if collection in _OWNER_SCOPED and any(
            c.metadata.get("owner_id") != owner_id for c in chunks
        ):
            raise PermissionError("chunk owner_id does not match owner_id")

        sql = text(_UPSERT_SQL)
        for i in range(0, len(chunks), _BATCH):
            batch = chunks[i : i + _BATCH]
            vectors = self._embed_checked([c.text for c in batch])
            rows = [
                {
                    "collection": collection,
                    "id": c.id,
                    "owner_id": str(c.metadata["owner_id"]) if "owner_id" in c.metadata else None,
                    "doc_id": str(c.metadata.get("doc_id", "")) or None,
                    "content": c.text,
                    "metadata": json.dumps(c.metadata),
                    "embedding": vector_literal(vec),
                    "model": EMBEDDING_NAME,
                }
                for c, vec in zip(batch, vectors, strict=True)
            ]
            self._run("indexing", lambda db, rows=rows: db.execute(sql, rows))
        return len(chunks)

    def add_embedded(
        self,
        collection: str,
        ids: Sequence[str],
        texts: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
        model_name: str = EMBEDDING_NAME,
    ) -> int:
        """Upsert rows that already carry embeddings (used to migrate from Chroma).

        Nothing is re-embedded, so the stored vectors are bit-for-bit what the
        source index held. Every vector must be exactly ``dimension`` long.
        """
        self._check_collection(collection)
        if not (len(ids) == len(texts) == len(metadatas) == len(embeddings)):
            raise ValueError("ids, texts, metadatas and embeddings must have equal length")
        if any(len(v) != self._dimension for v in embeddings):
            raise VectorStoreError(
                f"embedding dimension mismatch: expected {self._dimension} per vector"
            )
        sql = text(_UPSERT_SQL)
        for i in range(0, len(ids), _BATCH):
            rows = [
                {
                    "collection": collection,
                    "id": ids[j],
                    "owner_id": str(metadatas[j]["owner_id"])
                    if "owner_id" in metadatas[j]
                    else None,
                    "doc_id": str(metadatas[j].get("doc_id", "")) or None,
                    "content": texts[j],
                    "metadata": json.dumps(metadatas[j]),
                    "embedding": vector_literal(embeddings[j]),
                    "model": model_name,
                }
                for j in range(i, min(i + _BATCH, len(ids)))
            ]
            self._run("migration upsert", lambda db, rows=rows: db.execute(sql, rows))
        return len(ids)

    def delete_document(self, collection: str, doc_id: str, owner_id: str | None = None) -> int:
        params = _Params()
        where = self._where_sql(collection, owner_id, {"doc_id": doc_id}, params)
        sql = text(f"DELETE FROM vector_chunks WHERE {where}")
        return int(self._run("delete", lambda db: db.execute(sql, params.values).rowcount or 0))

    def delete_document_pair(self, doc_id: str, owner_id: str) -> int:
        return self.delete_document(USER_COLLECTION, doc_id, owner_id=owner_id)

    # -- reads --------------------------------------------------------------
    def query(
        self,
        collection: str,
        text: str,  # noqa: A002 - mirrors VectorStore.query
        n_results: int = 4,
        where: FilterDict | None = None,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        if n_results < 1:
            raise ValueError("n_results must be >= 1")
        params = _Params()
        scope_sql = self._where_sql(collection, owner_id, where, params)
        if not text.strip():
            return []
        try:
            (vector,) = self._embed_checked([text])
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"query failed: {type(exc).__name__}: {exc}") from exc
        q = params.add(vector_literal(vector))
        limit = params.add(int(n_results))
        sql = _text(
            f"""
            SELECT id, content, metadata, embedding <=> CAST({q} AS vector) AS distance
            FROM vector_chunks WHERE {scope_sql}
            ORDER BY embedding <=> CAST({q} AS vector) LIMIT {limit}
            """
        )
        rows = self._run("query", lambda db: db.execute(sql, params.values).all())
        return [SearchHit(r[0], r[1], _meta(r[2]), float(r[3])) for r in rows]

    def count(self, collection: str, owner_id: str | None = None) -> int:
        params = _Params()
        where = self._where_sql(collection, owner_id, None, params)
        sql = _text(f"SELECT count(*) FROM vector_chunks WHERE {where}")
        return int(self._run("count", lambda db: db.execute(sql, params.values).scalar() or 0))

    def document_vector_count(
        self, collection: str, doc_id: str, owner_id: str | None = None
    ) -> int:
        return len(self.get_chunks(collection, doc_id, owner_id, limit=None))

    def get_chunks(
        self,
        collection: str,
        doc_id: str,
        owner_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[SearchHit]:
        params = _Params()
        where = self._where_sql(collection, owner_id, {"doc_id": doc_id}, params)
        tail = f" LIMIT {params.add(int(limit))}" if limit is not None else ""
        sql = _text(f"SELECT id, metadata FROM vector_chunks WHERE {where} ORDER BY id{tail}")
        rows = self._run("chunk lookup", lambda db: db.execute(sql, params.values).all())
        return [SearchHit(r[0], "", _meta(r[1]), 0.0) for r in rows]

    def stored_chunk_texts(
        self, collection: str, doc_id: str, owner_id: str | None = None
    ) -> list[str]:
        params = _Params()
        where = self._where_sql(collection, owner_id, {"doc_id": doc_id}, params)
        sql = _text(
            f"SELECT content FROM vector_chunks WHERE {where} "
            "ORDER BY (metadata ->> 'chunk_index')::double precision NULLS LAST, id"
        )
        rows = self._run("chunk lookup", lambda db: db.execute(sql, params.values).all())
        return [str(r[0] or "") for r in rows]

    def list_vectors(
        self, collection: str, owner_id: str | None = None, where: FilterDict | None = None
    ) -> list[SearchHit]:
        params = _Params()
        scope_sql = self._where_sql(collection, owner_id, where, params)
        sql = _text(f"SELECT id, metadata FROM vector_chunks WHERE {scope_sql} ORDER BY id")
        rows = self._run("vector listing", lambda db: db.execute(sql, params.values).all())
        return [SearchHit(str(r[0]), "", _meta(r[1]), 0.0) for r in rows]

    def all_chunk_owners(self, collection: str) -> list[tuple[str, str, str]]:
        if collection != USER_COLLECTION:
            raise PermissionError("only the user collection is auditable")
        sql = _text(
            "SELECT id, coalesce(doc_id, ''), coalesce(owner_id, '') "
            "FROM vector_chunks WHERE collection = :c ORDER BY id"
        )
        rows = self._run("audit read", lambda db: db.execute(sql, {"c": collection}).all())
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]

    def embedding_dimension(self) -> int:
        return len(self._embed_checked(["dimension probe"])[0])

    def collection_info(self, collection: str) -> dict[str, Any]:
        self._check_collection(collection)
        sql = _text(
            "SELECT count(*), max(embedding_model), max(vector_dims(embedding)) "
            "FROM vector_chunks WHERE collection = :c"
        )
        row = self._run("collection info", lambda db: db.execute(sql, {"c": collection}).one())
        return {
            "name": collection,
            "count": int(row[0]),
            "embedding_model": row[1],
            "dimension": int(row[2]) if row[2] is not None else None,
        }


def _text(sql: str) -> Any:
    """``sqlalchemy.text`` under a name that ``query``'s ``text`` argument cannot shadow."""
    return text(sql)


def _meta(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return dict(json.loads(value))
    return dict(value or {})
