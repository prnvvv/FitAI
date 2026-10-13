"""Unit tests for the multi-agent orchestrator.

All LLM and external calls are mocked so the tests run without live keys.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agent.multi.graph import (
    local_research_node,
    router_node,
    run_multi_turn,
    synthesizer_node,
    web_research_node,
)
from app.agent.nodes import AgentDeps


@pytest.fixture
def deps() -> AgentDeps:
    return AgentDeps(
        llm=MagicMock(),
        memory_reader=SimpleNamespace(get_current_memory=lambda _uid: {}),
        memory_writer=MagicMock(),
        profile_reader=SimpleNamespace(get_profile=lambda _uid: {"units": "metric"}),
    )


class _FakeLLM:
    """Callable that returns a fixed string."""

    def __init__(self, response: str) -> None:
        self.response = response

    def __call__(self, *args, **kwargs):
        return self.response


def test_router_node_classifies_intent(monkeypatch, deps):
    monkeypatch.setattr(
        "app.agent.multi.graph._llm",
        lambda model=None: _FakeLLM(json.dumps({"category": "web"})),
    )
    state = {"user_id": "u1", "user_message": "What is the latest protein research?"}
    out = router_node(state, deps)  # type: ignore[arg-type]
    assert out["route"] == "web"
    assert any(e["tool"] == "router" and e["route"] == "web" for e in out["tool_results"])


def test_router_node_defaults_to_mixed_on_bad_json(monkeypatch, deps):
    monkeypatch.setattr(
        "app.agent.multi.graph._llm",
        lambda model=None: _FakeLLM("not json"),
    )
    state = {"user_id": "u1", "user_message": "hello"}
    out = router_node(state, deps)  # type: ignore[arg-type]
    assert out["route"] == "mixed"


def test_web_research_node_with_results(monkeypatch, deps):
    plan = json.dumps({"queries": ["protein research 2026"]})
    brief = json.dumps(
        {
            "findings": "Higher protein intake supports muscle retention.",
            "sources": [],
            "confidence": "medium",
            "gaps": "",
        }
    )
    calls = {"count": 0}

    def fake_llm(model=None):
        calls["count"] += 1
        return _FakeLLM(plan if calls["count"] == 1 else brief)

    monkeypatch.setattr("app.agent.multi.graph._llm", fake_llm)

    fake_result = SimpleNamespace(
        title="Example Study",
        url="https://example.com/study",
        source_domain="example.com",
    )
    monkeypatch.setattr(
        "app.agent.multi.graph.SearchClient",
        lambda: SimpleNamespace(search_all=lambda _queries, max_results: [fake_result]),
    )
    monkeypatch.setattr(
        "app.agent.multi.graph.fetch_url",
        lambda _url: {"text": "Protein is good." * 10, "error": None},
    )

    state = {"user_id": "u1", "user_message": "latest protein research", "route": "web"}
    out = web_research_node(state, deps)  # type: ignore[arg-type]

    assert out["web_brief"]["findings"]
    assert any(s["url"] == "https://example.com/study" for s in out["web_brief"]["sources"])
    assert any(e["tool"] == "web_search" for e in out["tool_results"])
    assert any(e["tool"] == "read_webpage" for e in out["tool_results"])


def test_web_research_node_returns_empty_brief_when_no_results(monkeypatch, deps):
    monkeypatch.setattr(
        "app.agent.multi.graph._llm",
        lambda model=None: _FakeLLM(json.dumps({"queries": ["x"], "findings": ""})),
    )
    monkeypatch.setattr(
        "app.agent.multi.graph.SearchClient",
        lambda: SimpleNamespace(search_all=lambda _queries, max_results: []),
    )
    state = {"user_id": "u1", "user_message": "xyz", "route": "web"}
    out = web_research_node(state, deps)  # type: ignore[arg-type]
    assert out["web_brief"]["confidence"] == "low"


def test_local_research_node_with_profile_location(monkeypatch, deps):
    brief = json.dumps(
        {
            "findings": "Sunny gyms nearby.",
            "places": [],
            "confidence": "medium",
            "gaps": "",
        }
    )
    monkeypatch.setattr(
        "app.agent.multi.graph._llm",
        lambda model=None: _FakeLLM(brief),
    )
    monkeypatch.setattr(
        "app.agent.multi.graph.find_places",
        lambda **kwargs: {"places": [{"name": "Gym A", "map_url": "https://maps/a"}]},
    )
    monkeypatch.setattr(
        "app.agent.multi.graph.get_weather",
        lambda *args, **kwargs: {"temperature": 22, "condition": "sunny"},
    )

    state = {
        "user_id": "u1",
        "user_message": "find gyms",
        "route": "local",
        "retrieved_profile": {"location": "Brooklyn, NY", "units": "metric"},
    }
    out = local_research_node(state, deps)  # type: ignore[arg-type]
    assert out["local_brief"]["findings"]
    assert any(e["tool"] == "find_places" for e in out["tool_results"])
    assert any(e["tool"] == "get_weather" for e in out["tool_results"])


def test_local_research_node_prompts_for_location_when_unknown(deps):
    state = {
        "user_id": "u1",
        "user_message": "find gyms",
        "route": "local",
        "retrieved_profile": {},
    }
    out = local_research_node(state, deps)  # type: ignore[arg-type]
    assert "don't know your location" in out["local_brief"]["findings"].lower()


def test_synthesizer_node_builds_numbered_sources(deps):
    state = {
        "user_id": "u1",
        "user_message": "tell me more",
        "web_brief": {
            "findings": "Findings.",
            "sources": [
                {"title": "Source 1", "url": "https://one.com"},
                {"title": "Source 2", "url": "https://two.com"},
            ],
        },
        "local_brief": {
            "findings": "Local.",
            "places": [{"name": "Gym", "map_url": "https://maps/gym"}],
        },
    }
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.agent.multi.graph._llm",
        lambda model=None: _FakeLLM("Answer with [1] and [2]."),
    )
    try:
        out = synthesizer_node(state, deps)  # type: ignore[arg-type]
    finally:
        monkeypatch.undo()
    assert out["response"]
    assert len(out["sources"]) == 3
    assert {1, 2, 3} == {s["index"] for s in out["sources"]}


def test_run_multi_turn_falls_back_to_single_agent_for_personal(deps, monkeypatch):
    """Personal turns should run the existing memory-aware single-agent graph."""
    single_result = {"response": "got it", "sources": [], "actions": [], "tool_results": []}
    multi_out = {"route": "personal", "response": "", "sources": [], "actions": []}

    def fake_graph(_deps):
        return SimpleNamespace(invoke=lambda _state: multi_out)

    monkeypatch.setattr("app.agent.multi.graph.build_multi_graph", fake_graph)
    monkeypatch.setattr("app.agent.graph.build_graph", lambda _deps: MagicMock())
    monkeypatch.setattr("app.agent.graph.run_turn", lambda _g, _uid, _msg, _ctx: single_result)

    result = run_multi_turn(deps, "u1", "I weigh 80 kg")
    assert result["response"] == "got it"


def test_run_multi_turn_returns_multi_agent_result_when_not_personal(deps, monkeypatch):
    multi_out = {
        "route": "web",
        "response": "web answer",
        "sources": [{"title": "T", "url": "https://t", "index": 1}],
        "actions": [],
        "tool_results": [{"tool": "web_search", "sources": 1}],
    }

    def fake_graph(_deps):
        return SimpleNamespace(invoke=lambda _state: multi_out)

    monkeypatch.setattr("app.agent.multi.graph.build_multi_graph", fake_graph)

    result = run_multi_turn(deps, "u1", "latest news")
    assert result["response"] == "web answer"
    assert result["sources"]
    assert any(e["tool"] == "multi_agent" for e in result["tool_results"])
