"""Remote embeddings and the pgvector store's filter translation (no database needed)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.rag.embeddings import EmbeddingError, RemoteEmbedder
from app.rag.pg_vector_store import PgVectorStore, translate_filter, vector_literal
from app.rag.vector_store import CONTINUITY_COLLECTION, USER_COLLECTION, VectorStoreError

DIM = 4


def _embedder(handler, fmt: str = "hf", batch: int = 2) -> RemoteEmbedder:
    return RemoteEmbedder(
        "https://embed.test/x",
        "secret-key",
        dimension=DIM,
        model="m",
        api_format=fmt,
        batch_size=batch,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _vec(i: int) -> list[float]:
    return [float(i), 0.0, 1.0, 0.5]


def test_hf_format_batches_requests_and_validates_dimension() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(200, json=[_vec(i) for i, _ in enumerate(body["inputs"])])

    out = _embedder(handler, batch=2).embed(["a", "b", "c", "d", "e"])
    assert len(out) == 5 and all(len(v) == DIM for v in out)
    assert [len(r["inputs"]) for r in requests] == [2, 2, 1]  # bounded batches


def test_openai_format_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "m"
        return httpx.Response(
            200, json={"data": [{"embedding": _vec(i)} for i, _ in enumerate(body["input"])]}
        )

    assert len(_embedder(handler, "openai").embed(["a", "b"])) == 2


def test_wrong_dimension_is_rejected_before_it_can_reach_the_index() -> None:
    handler = lambda r: httpx.Response(200, json=[[1.0, 2.0]])  # noqa: E731
    with pytest.raises(EmbeddingError, match="4-dimensional"):
        _embedder(handler).embed(["a"])


def test_wrong_vector_count_is_rejected() -> None:
    handler = lambda r: httpx.Response(200, json=[_vec(0)])  # noqa: E731
    with pytest.raises(EmbeddingError, match="unexpected number"):
        _embedder(handler).embed(["a", "b"])


def test_provider_error_is_wrapped_and_never_leaks_the_key_or_body() -> None:
    handler = lambda r: httpx.Response(401, text="bad key secret-key")  # noqa: E731
    with pytest.raises(EmbeddingError) as exc:
        _embedder(handler).embed(["a"])
    assert "secret-key" not in str(exc.value)


def test_missing_configuration_fails_clearly() -> None:
    with pytest.raises(EmbeddingError, match="EMBEDDING_API_URL"):
        RemoteEmbedder(None, None, dimension=DIM)


def test_chroma_embedding_function_protocol() -> None:
    e = _embedder(lambda r: httpx.Response(200, json=[_vec(0)]))
    assert e.name() and e(input=["a"])[0] == _vec(0)


# ---- filter translation ---------------------------------------------------


def test_equality_and_conjunction() -> None:
    sql, params = translate_filter({"$and": [{"owner_id": "u1"}, {"doc_id": "d1"}]})
    assert sql.count("(metadata ->> ") == 2 and " AND " in sql
    assert sorted(params.values()) == ["d1", "u1"]


def test_numeric_comparisons_are_cast_and_bound() -> None:
    sql, params = translate_filter({"page": {"$gte": 3}})
    assert "::double precision >= " in sql and 3.0 in params.values()


def test_in_and_or() -> None:
    sql, params = translate_filter({"$or": [{"kind": {"$in": ["a", "b"]}}, {"kind": "c"}]})
    assert " OR " in sql and " IN (" in sql
    assert sorted(params.values()) == ["a", "b", "c"]


def test_values_are_never_interpolated_into_sql() -> None:
    sql, _ = translate_filter({"owner_id": "x'; DROP TABLE vector_chunks; --"})
    assert "DROP" not in sql


@pytest.mark.parametrize(
    "bad",
    [{"bad key": 1}, {"a'b": 1}, {"$where": 1}, {"page": {"$regex": "x"}}, {"$and": []}],
)
def test_unknown_or_unsafe_filters_raise_instead_of_widening_results(bad) -> None:
    with pytest.raises(ValueError):
        translate_filter(bad)


def test_vector_literal_format() -> None:
    assert vector_literal([1, 2.5]) == "[1.0,2.5]"


# ---- store contract that does not need a database --------------------------


def _store() -> PgVectorStore:
    return PgVectorStore(embedding_function=lambda t: [_vec(0) for _ in t], dimension=DIM)


def test_owner_scoped_collections_require_an_owner() -> None:
    store = _store()
    for fn in (
        lambda: store.query(USER_COLLECTION, "q"),
        lambda: store.delete_document(USER_COLLECTION, "d"),
        lambda: store.count(CONTINUITY_COLLECTION),
        lambda: store.get_chunks(USER_COLLECTION, "d"),
    ):
        with pytest.raises(PermissionError):
            fn()


def test_unknown_collection_is_rejected() -> None:
    with pytest.raises(ValueError):
        _store().count("nope")


def test_add_chunks_rejects_a_foreign_owner_before_any_io() -> None:
    from app.rag.chunker import Chunk

    chunk = Chunk("id", "text", {"owner_id": "someone-else"})
    with pytest.raises(PermissionError):
        _store().add_chunks(USER_COLLECTION, [chunk], owner_id="me")


def test_embedding_dimension_mismatch_is_a_store_error() -> None:
    store = PgVectorStore(embedding_function=lambda t: [[1.0] for _ in t], dimension=DIM)
    with pytest.raises(VectorStoreError, match="dimension mismatch"):
        store.embedding_dimension()
