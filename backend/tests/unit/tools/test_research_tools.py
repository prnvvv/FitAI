"""Unit tests for live research tools."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.nearby_gyms import nearby_gyms
from app.tools.web_search import web_search


def test_web_search_returns_formatted_results() -> None:
    mock_result = [
        {"title": "Example", "body": "A useful snippet", "href": "https://example.com"},
    ]
    with patch("app.tools.web_search.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        instance.text.return_value = iter(mock_result)
        mock_ddgs.return_value = instance

        result = web_search("best protein sources")

    assert result["query"] == "best protein sources"
    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://example.com"
    assert "error" not in result


def test_web_search_handles_failure() -> None:
    with patch("app.tools.web_search.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        instance.text.side_effect = RuntimeError("blocked")
        mock_ddgs.return_value = instance

        result = web_search("query")

    assert result["results"] == []
    assert "error" in result


def test_nearby_gyms_requires_location() -> None:
    result = nearby_gyms(None)
    assert result["places"] == []
    assert "provide" in result["error"].lower()


def test_nearby_gyms_returns_places() -> None:
    nominatim_response = [{"lat": "51.5", "lon": "-0.1"}]
    overpass_response = {
        "elements": [
            {
                "type": "node",
                "lat": 51.501,
                "lon": -0.101,
                "tags": {"name": "Test Gym", "leisure": "fitness_centre", "addr:street": "Main St"},
            }
        ]
    }
    with patch("app.tools.nearby_gyms.httpx.Client") as mock_client:
        client_instance = MagicMock()
        client_instance.get.return_value.raise_for_status = MagicMock()
        client_instance.get.return_value.json.return_value = nominatim_response
        client_instance.post.return_value.raise_for_status = MagicMock()
        client_instance.post.return_value.json.return_value = overpass_response
        client_instance.__enter__ = MagicMock(return_value=client_instance)
        client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = client_instance

        result = nearby_gyms("London")

    assert len(result["places"]) == 1
    assert result["places"][0]["name"] == "Test Gym"
    assert "map_url" in result["places"][0]
    assert "error" not in result


def test_nearby_gyms_handles_geocode_failure() -> None:
    with patch("app.tools.nearby_gyms.httpx.Client") as mock_client:
        client_instance = MagicMock()
        client_instance.get.side_effect = RuntimeError("network")
        client_instance.__enter__ = MagicMock(return_value=client_instance)
        client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = client_instance

        result = nearby_gyms("London")

    assert result["places"] == []
    assert "error" in result
