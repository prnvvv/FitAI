"""Tests for the web search provider chain."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.tools.web.models import SearchResult, WebSearchResponse
from app.tools.web.providers.registry import SearchClient


def test_search_client_uses_first_available_provider() -> None:
    first = MagicMock()
    first.name = "first"
    first.is_available.return_value = True
    first.search.return_value = WebSearchResponse(
        query="protein",
        provider="first",
        results=[
            SearchResult(
                title="T",
                url="https://example.com",
                snippet="S",
                source_domain="example.com",
                provider="first",
                rank=1,
            )
        ],
    )

    second = MagicMock()
    second.name = "second"
    second.is_available.return_value = True

    client = SearchClient.__new__(SearchClient)
    client._providers = [first, second]
    client._circuit = MagicMock()
    client._circuit.is_open.return_value = False

    response = client.search("protein")

    assert response.provider == "first"
    assert len(response.results) == 1
    first.search.assert_called_once()
    second.search.assert_not_called()


def test_search_client_falls_back_on_failure() -> None:
    first = MagicMock()
    first.name = "first"
    first.is_available.return_value = True
    first.search.side_effect = RuntimeError("boom")

    second = MagicMock()
    second.name = "second"
    second.is_available.return_value = True
    second.search.return_value = WebSearchResponse(
        query="protein",
        provider="second",
        results=[
            SearchResult(
                title="T",
                url="https://example.com",
                snippet="S",
                source_domain="example.com",
                provider="second",
                rank=1,
            )
        ],
    )

    client = SearchClient.__new__(SearchClient)
    client._providers = [first, second]
    client._circuit = MagicMock()
    client._circuit.is_open.return_value = False

    response = client.search("protein")

    assert response.provider == "second"
    assert first.search.call_count == 2  # one retry


def test_search_client_deduplicates_all_queries() -> None:
    a = MagicMock()
    a.name = "a"
    a.is_available.return_value = True
    a.search.return_value = WebSearchResponse(
        query="q1",
        provider="a",
        results=[
            SearchResult(
                title="T",
                url="https://example.com",
                snippet="S",
                source_domain="example.com",
                provider="a",
                rank=1,
            )
        ],
    )

    client = SearchClient.__new__(SearchClient)
    client._providers = [a]
    client._circuit = MagicMock()
    client._circuit.is_open.return_value = False

    results = client.search_all(["q1", "q2"])

    assert len(results) == 1
    assert a.search.call_count == 2
