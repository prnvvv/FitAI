"""Tests for LangGraph agent nodes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agent.nodes import (
    AgentDeps,
    extract_facts_node,
    generate_response,
    looks_like_question,
    looks_personal,
    retrieve_context_node,
    safe_response,
    safety_check,
)
from app.agent.state import AgentState
from app.memory.change_detector import MemoryEntry
from app.safety import SafetyResult


def _deps(fake_llm: Any, fake_memory_reader: Any, fake_memory_writer: Any,
          fake_retriever: Any | None = None) -> AgentDeps:
    return AgentDeps(
        llm=fake_llm,
        memory_reader=fake_memory_reader,
        memory_writer=fake_memory_writer,
        retriever=fake_retriever,
        clock=lambda: datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_looks_personal_detects_weight() -> None:
    assert looks_personal("I weigh 70 kg") is True


def test_looks_personal_detects_goal() -> None:
    assert looks_personal("my goal is to gain muscle") is True


def test_looks_personal_false_for_question() -> None:
    assert looks_personal("What is protein?") is False


def test_looks_like_question_detects_question_mark() -> None:
    assert looks_like_question("How much protein?") is True


def test_looks_like_question_detects_how() -> None:
    assert looks_like_question("how do I lose weight") is True


def test_safety_check_blocks_self_harm() -> None:
    state: AgentState = {"user_message": "I want to kill myself"}
    result = safety_check(state)
    assert result["safety"].blocked is True
    assert result["safety"].category == "self_harm"


def test_safe_response_uses_blocked_reply() -> None:
    safety = SafetyResult(blocked=True, response="Blocked reply")
    state: AgentState = {"safety": safety}
    result = safe_response(state)
    assert result["response"] == "Blocked reply"


def test_safe_response_fallback() -> None:
    state: AgentState = {"safety": SafetyResult(blocked=True)}
    result = safe_response(state)
    assert "can't help" in result["response"]


def test_extract_facts_node_blocked_returns_empty() -> None:
    state: AgentState = {"user_message": "test", "safety": SafetyResult(blocked=True)}
    deps = _deps(None, None, None)
    assert extract_facts_node(state, deps) == {}


def test_extract_facts_node_extracts(fake_llm: Any, fake_memory_reader: Any,
                                     fake_memory_writer: Any, now: datetime) -> None:
    fake_llm.response = '{"facts":[{"field":"weight","value":70,"unit":"kg","confidence":0.9,"timestamp":null,"tense":"present","statement_type":"explicit","source_text":"I weigh 70 kg"}]}'
    state: AgentState = {"user_message": "I weigh 70 kg", "safety": SafetyResult()}
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    result = extract_facts_node(state, deps)
    assert len(result["extracted_facts"]) == 1


def test_retrieve_context_node_loads_memory_and_docs(fake_memory_reader: Any,
                                                     fake_memory_writer: Any,
                                                     fake_retriever: Any) -> None:
    fake_memory_reader.memory = {"weight": MemoryEntry(key="weight", value=70, unit="kg")}
    fake_retriever.docs = ["[source] protein info"]
    state: AgentState = {"user_message": "How much protein?", "user_id": "user-1",
                         "safety": SafetyResult()}
    deps = _deps(None, fake_memory_reader, fake_memory_writer, fake_retriever)
    result = retrieve_context_node(state, deps)
    assert "retrieved_memory" in result
    assert result["retrieved_memory"]["weight"].value == 70
    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["docs"] == ["[source] protein info"]


def test_generate_response_includes_status_footer(fake_llm: Any, fake_memory_reader: Any,
                                                   fake_memory_writer: Any) -> None:
    fake_llm.response = "You need more protein."
    state: AgentState = {
        "user_message": "How much protein?",
        "conversation_context": [],
        "tool_results": [{"tool": "memory_write", "status": "applied", "summary": "weight = 70 kg",
                          "key": "weight", "history_recorded": False}],
        "errors": [],
    }
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    result = generate_response(state, deps)
    assert "You need more protein." in result["response"]
    assert "Saved: weight = 70 kg" in result["response"]
