"""Tests for OpenAI-style tool definitions and executor."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.tool_definitions import TOOL_DEFINITIONS, execute_tool


def test_tool_definitions_include_canonical_and_alias() -> None:
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "web_search" in names
    assert "web.run" in names
    assert "nearby_gyms" in names


def test_execute_tool_routes_web_search() -> None:
    with patch("app.tools.tool_definitions.ddgs_web_search") as mock_search:
        mock_search.return_value = {"results": []}
        result = execute_tool("web_search", {"query": "keto diet", "max_results": 3})
        mock_search.assert_called_once_with("keto diet", max_results=3)
        assert result == {"results": []}


def test_execute_tool_aliases_web_run() -> None:
    with patch("app.tools.tool_definitions.ddgs_web_search") as mock_search:
        mock_search.return_value = {"results": []}
        result = execute_tool("web.run", {"query": "Mylapore gyms", "topn": 5})
        mock_search.assert_called_once_with("Mylapore gyms", max_results=5)
        assert result == {"results": []}


def test_execute_tool_routes_nearby_gyms() -> None:
    with patch("app.tools.tool_definitions.nearby_gyms") as mock_gyms:
        mock_gyms.return_value = {"places": []}
        result = execute_tool("nearby_gyms", {"location": "Mylapore, Chennai", "radius_m": 2000})
        mock_gyms.assert_called_once_with("Mylapore, Chennai", radius_m=2000)
        assert result == {"places": []}


def test_execute_tool_unknown_tool_returns_error() -> None:
    result = execute_tool("unknown_tool", {})
    assert "error" in result
    assert "unknown_tool" in result["error"]
