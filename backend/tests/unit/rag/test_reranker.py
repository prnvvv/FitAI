"""Sentence-similarity reranking: ordering, metadata, fallback, limits, configuration."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.core.config import Settings, settings
from app.rag import reranker as reranker_mod
from app.rag.reranker import SentenceSimilarityReranker, get_configured_reranker
from app.rag.retriever import Retriever
from app.rag.vector_store import KNOWLEDGE_COLLECTION, USER_COLLECTION, SearchHit

TOKEN = "hf_SECRET_TOKEN_VALUE"
UID = "user-1"


class FakeStore:
    """Returns the same ranked hits for any collection, recording the requested size."""

    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits, self.requested_k = hits, []

    def query(self, collection, text, n_results=4, where=None, owner_id=None):
        self.requested_k.append(n_results)
        if collection == USER_COLLECTION:
            return [h for h in self.hits if h.metadata.get("owner_id") == owner_id][:n_results]
        return [h for h in self.hits if h.metadata.get("owner_id") is None][:n_results]


class FakeClient:
    def __init__(self, scores=None, error: Exception | None = None) -> None:
        self.scores, self.error, self.calls = scores, error, []

    def sentence_similarity(self, sentence, other_sentences, *, model=None):
        self.calls.append((sentence, list(other_sentences), model))
        if self.error:
            raise self.error
        return self.scores(other_sentences) if callable(self.scores) else self.scores


def _hit(i: int, distance: float, owner: str | None = None, **meta) -> SearchHit:
    m = {"source": f"doc{i}.pdf", "doc_id": f"d{i}", "page": i, "chunk_index": i, **meta}
    if owner:
        m["owner_id"] = owner
    return SearchHit(f"c{i}", f"text {i}", m, distance)


def _store(n: int = 5) -> FakeStore:
    # Vector order is c0 (closest) .. c{n-1}.
    return FakeStore([_hit(i, 0.1 + i * 0.05) for i in range(n)])


def _rr(client, **kw) -> SentenceSimilarityReranker:
    kw.setdefault("cooldown_s", 60.0)
    return SentenceSimilarityReranker(
        TOKEN, "sentence-transformers/all-MiniLM-L6-v2", client=client, **kw
    )


def _retriever(store, rr, k: int = 3) -> Retriever:
    return Retriever(store, k=k, reranker=rr)


def _ids(chunks) -> list[str]:
    return [c.metadata["chunk_index"] for c in chunks]


def test_reranking_reorders_candidates_by_similarity_score() -> None:
    # Candidates 0..4 get scores that put 3 first, then 1, then 4.
    client = FakeClient([0.10, 0.60, 0.05, 0.90, 0.30])
    out = _retriever(_store(), _rr(client)).retrieve("squat form", None, include_user_docs=False)
    assert _ids(out) == [3, 1, 4]
    assert [c.rerank_score for c in out] == [0.90, 0.60, 0.30]
    sentence, sentences, model = client.calls[0]
    assert sentence == "squat form" and model == "sentence-transformers/all-MiniLM-L6-v2"
    assert sentences == [f"text {i}" for i in range(5)]


def test_metadata_citations_and_vector_score_are_preserved() -> None:
    store = FakeStore([_hit(i, 0.1 + i * 0.05, extra=f"x{i}") for i in range(3)])
    base = Retriever(store, k=3, reranker=None).retrieve("q", None, include_user_docs=False)
    client = FakeClient([0.1, 0.2, 0.9])
    out = _retriever(store, _rr(client)).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [2, 1, 0]
    by_id = {c.metadata["chunk_index"]: c for c in base}
    for chunk in out:
        original = by_id[chunk.metadata["chunk_index"]]
        assert chunk.text == original.text and chunk.metadata == original.metadata
        assert chunk.doc_id == original.doc_id and chunk.page == original.page
        assert chunk.citation() == original.citation()
        assert chunk.score == original.score  # the vector score is untouched
        assert chunk.scope == original.scope


def test_user_documents_stay_scoped_to_their_owner_when_reranking() -> None:
    store = FakeStore([_hit(0, 0.1, owner=UID), _hit(1, 0.2, owner="someone-else"), _hit(2, 0.3)])
    client = FakeClient(lambda s: [0.5] * len(s))
    out = _retriever(store, _rr(client), k=5).retrieve("q", UID)
    assert {c.metadata.get("owner_id") for c in out} <= {UID, None}
    assert all("text 1" not in sent for _, sents, _ in client.calls for sent in sents)


def test_ties_keep_the_vector_order() -> None:
    out = _retriever(_store(4), _rr(FakeClient([0.5, 0.5, 0.5, 0.5]))).retrieve(
        "q", None, include_user_docs=False
    )
    assert _ids(out) == [0, 1, 2]


def test_provider_failure_falls_back_to_vector_ranking_without_raising() -> None:
    err = RuntimeError("429 Too Many Requests")
    err.response = SimpleNamespace(status_code=429)  # type: ignore[attr-defined]
    client = FakeClient(error=err)
    out = _retriever(_store(), _rr(client)).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [0, 1, 2] and all(c.rerank_score is None for c in out)


@pytest.mark.parametrize("bad", [[0.1, 0.2], "nope", None, [0.1, "x", 0.3, 0.4, 0.5]])
def test_malformed_provider_reply_falls_back(bad) -> None:
    out = _retriever(_store(), _rr(FakeClient(bad))).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [0, 1, 2]


def test_after_a_failure_the_provider_is_not_called_again_until_the_cooldown_ends() -> None:
    now = [1000.0]
    client = FakeClient(error=TimeoutError("slow"))
    rr = _rr(client, cooldown_s=60.0, clock=lambda: now[0])
    r = _retriever(_store(), rr)
    r.retrieve("q", None, include_user_docs=False)
    r.retrieve("q", None, include_user_docs=False)
    assert len(client.calls) == 1  # second query skipped the dead provider
    now[0] += 61
    client.error, client.scores = None, [0.1, 0.2, 0.3, 0.4, 0.9]
    out = r.retrieve("q", None, include_user_docs=False)
    assert len(client.calls) == 2 and _ids(out)[0] == 4


def test_missing_token_makes_the_reranker_inert_and_retrieval_unchanged() -> None:
    rr = SentenceSimilarityReranker(None, "m")  # no token, no injected client
    assert not rr.available
    out = _retriever(_store(), rr).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [0, 1, 2]


def test_enabled_without_a_token_yields_no_reranker(monkeypatch) -> None:
    reranker_mod.reset_shared_reranker()
    monkeypatch.setattr(settings, "hf_reranking_enabled", True)
    monkeypatch.setattr(settings, "hf_token", None)
    assert get_configured_reranker() is None
    monkeypatch.setattr(settings, "hf_token", "   ")
    assert get_configured_reranker() is None
    reranker_mod.reset_shared_reranker()


def test_disabled_by_default_makes_no_call_and_fetches_exactly_k(monkeypatch) -> None:
    reranker_mod.reset_shared_reranker()
    monkeypatch.setattr(settings, "hf_token", TOKEN)
    assert settings.hf_reranking_enabled is False
    assert get_configured_reranker() is None
    store = _store()
    out = Retriever(store, k=3).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [0, 1, 2]
    assert store.requested_k == [3]  # no wider candidate pool, baseline behaviour


def test_enabled_and_configured_builds_a_shared_reranker(monkeypatch) -> None:
    reranker_mod.reset_shared_reranker()
    monkeypatch.setattr(settings, "hf_reranking_enabled", True)
    monkeypatch.setattr(settings, "hf_token", TOKEN)
    monkeypatch.setattr(settings, "hf_reranking_candidates", 7)
    rr = get_configured_reranker()
    assert rr is not None and rr.max_candidates == 7 and get_configured_reranker() is rr
    reranker_mod.reset_shared_reranker()


def test_empty_candidate_list_makes_no_call() -> None:
    client = FakeClient([])
    out = _retriever(FakeStore([]), _rr(client)).retrieve("q", None, include_user_docs=False)
    assert out == [] and client.calls == []


def test_single_candidate_needs_no_api_call() -> None:
    client = FakeClient([0.9])
    out = _retriever(_store(1), _rr(client)).retrieve("q", None, include_user_docs=False)
    assert _ids(out) == [0] and client.calls == []


def test_blank_query_makes_no_call() -> None:
    client = FakeClient([0.1] * 5)
    _retriever(_store(), _rr(client)).retrieve("   ", None, include_user_docs=False)
    assert client.calls == []


def test_candidate_pool_is_bounded_and_k_is_respected() -> None:
    store = _store(10)
    client = FakeClient(lambda s: [float(i) for i in range(len(s))])
    out = _retriever(store, _rr(client, max_candidates=4), k=2).retrieve(
        "q", None, include_user_docs=False
    )
    assert store.requested_k == [4]  # fetched max(k, max_candidates), not the whole index
    assert len(client.calls[0][1]) == 4  # one batched request with at most 4 sentences
    assert len(out) == 2
    # The API scores 0..3 ascending, so the last candidate of the pool wins.
    assert _ids(out) == [3, 2]


def test_max_candidates_is_clamped() -> None:
    assert _rr(FakeClient([]), max_candidates=1000).max_candidates == 50
    assert _rr(FakeClient([]), max_candidates=0).max_candidates == 2


def test_long_chunks_are_truncated_before_sending() -> None:
    long = SearchHit("c0", "x" * 5000, {"source": "a", "doc_id": "d0", "chunk_index": 0}, 0.1)
    short = _hit(1, 0.2)
    client = FakeClient([0.2, 0.8])
    _retriever(FakeStore([long, short]), _rr(client)).retrieve("q", None, include_user_docs=False)
    assert max(len(s) for s in client.calls[0][1]) <= reranker_mod.MAX_CANDIDATE_CHARS


def test_failures_never_log_the_token_query_or_chunk_text(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    err = RuntimeError(f"401 Unauthorized Bearer {TOKEN} for 'private user question'")
    err.response = SimpleNamespace(status_code=401)  # type: ignore[attr-defined]
    _retriever(_store(), _rr(FakeClient(error=err))).retrieve(
        "private user question", None, include_user_docs=False
    )
    logged = caplog.text
    assert "hf_rerank_failed" in logged and "status=401" in logged
    assert TOKEN not in logged and "private user question" not in logged and "text 0" not in logged


def test_hf_token_is_read_from_hf_token_or_the_existing_huggingface_api_key(monkeypatch) -> None:
    for name in ("HF_TOKEN", "HUGGINGFACE_API_KEY"):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
        monkeypatch.setenv(name, "hf_from_env")
        assert Settings(_env_file=None).hf_token == "hf_from_env"


def test_reranking_config_defaults_preserve_existing_behaviour() -> None:
    s = Settings(_env_file=None)
    assert s.hf_reranking_enabled is False
    assert s.hf_reranking_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert 2 <= s.hf_reranking_candidates <= 50


def test_provider_and_client_method_match_the_huggingface_hub_api() -> None:
    hub = pytest.importorskip("huggingface_hub")
    import inspect

    params = list(inspect.signature(hub.InferenceClient.sentence_similarity).parameters)
    assert params[:3] == ["self", "sentence", "other_sentences"] and "model" in params
    assert reranker_mod.PROVIDER == "hf-inference"
    assert KNOWLEDGE_COLLECTION  # imported for the fake store's collection routing
