"""Tests for LangGraph agent nodes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agent.nodes import (
    AgentDeps,
    _select_tools,
    extract_facts_node,
    generate_response,
    looks_like_question,
    looks_personal,
    retrieve_context_node,
    safe_response,
    safety_check,
    wants_personal_data_answer,
)
from app.agent.state import AgentState
from app.memory.change_detector import MemoryEntry
from app.safety import SafetyResult


def _deps(
    fake_llm: Any,
    fake_memory_reader: Any,
    fake_memory_writer: Any,
    fake_retriever: Any | None = None,
) -> AgentDeps:
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


def test_extract_facts_node_extracts(
    fake_llm: Any, fake_memory_reader: Any, fake_memory_writer: Any, now: datetime
) -> None:
    fake_llm.response = '{"facts":[{"field":"weight","value":70,"unit":"kg","confidence":0.9,"timestamp":null,"tense":"present","statement_type":"explicit","source_text":"I weigh 70 kg"}]}'
    state: AgentState = {"user_message": "I weigh 70 kg", "safety": SafetyResult()}
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    result = extract_facts_node(state, deps)
    assert len(result["extracted_facts"]) == 1


def test_retrieve_context_node_loads_memory_and_docs(
    fake_memory_reader: Any, fake_memory_writer: Any, fake_retriever: Any
) -> None:
    fake_memory_reader.memory = {"weight": MemoryEntry(key="weight", value=70, unit="kg")}
    fake_retriever.docs = ["[source] protein info"]
    state: AgentState = {
        "user_message": "How much protein?",
        "user_id": "user-1",
        "safety": SafetyResult(),
    }
    deps = _deps(None, fake_memory_reader, fake_memory_writer, fake_retriever)
    result = retrieve_context_node(state, deps)
    assert "retrieved_memory" in result
    assert result["retrieved_memory"]["weight"].value == 70
    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["docs"] == ["[source] protein info"]


def test_generate_response_returns_actions_for_pending_updates(
    fake_llm: Any, fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    fake_llm.response = "You need more protein."
    state: AgentState = {
        "user_message": "How much protein?",
        "conversation_context": [],
        "tool_results": [
            {
                "tool": "memory_write",
                "status": "pending_created",
                "proposal_id": "prop-1",
                "summary": "weight = 70 kg",
                "key": "weight",
            }
        ],
        "errors": [],
    }
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    result = generate_response(state, deps)
    assert result["response"] == "You need more protein."
    assert len(result["actions"]) == 1
    assert result["actions"][0]["type"] == "memory_confirm"
    assert result["actions"][0]["proposal_id"] == "prop-1"


def test_generate_response_uses_tool_loop_when_available(
    fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    """When the LLM supports run_with_tools, generate_response uses it."""

    class _ToolLoopLLM:
        def __init__(self) -> None:
            self.tools_passed: list[dict[str, Any]] | None = None

        def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
            return "fallback"

        def run_with_tools(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            execute: Any,
        ) -> str:
            self.tools_passed = tools
            return "tool-loop answer"

    llm = _ToolLoopLLM()
    state: AgentState = {
        "user_message": "Find gyms near me",
        "conversation_context": [],
        "tool_results": [],
        "errors": [],
    }
    deps = _deps(llm, fake_memory_reader, fake_memory_writer)
    result = generate_response(state, deps)
    assert result["response"] == "tool-loop answer"
    assert llm.tools_passed is not None
    assert any(t["function"]["name"] == "nearby_gyms" for t in llm.tools_passed)


def test_generate_response_pins_memory_when_retrieve_node_skipped(
    fake_llm: Any, fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    """Pinned core memory must appear even when retrieve_context_node was skipped.

    Regression: non-question turns route straight to generate_response, so the
    retrieval node never sets retrieved_memory/retrieved_profile. The generator
    must still load them so FitAI doesn't "forget" facts between turns.
    """
    fake_llm.response = "Here's your plan."
    fake_memory_reader.memory = {"weight": MemoryEntry(key="weight", value=70, unit="kg")}
    state: AgentState = {
        "user_message": "Give me a 4 day routine",
        "user_id": "user-1",
        "conversation_context": [],
        "tool_results": [],
        "errors": [],
    }
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    generate_response(state, deps)
    _, prompt, _ = fake_llm.calls[-1]
    assert "User profile and memory:" in prompt
    assert "weight: 70" in prompt
    assert "kg" in prompt


# ---- workout/progress context wiring -----------------------------------------


class _FakeFitnessReader:
    """Stub fitness reader that records calls and returns a fixed summary."""

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self.context = context or {}
        self.calls: list[str] = []

    def get_fitness_context(self, user_id: str) -> dict[str, Any]:
        self.calls.append(user_id)
        return self.context


def _fitness_deps(
    fake_memory_reader: Any, fake_memory_writer: Any, fitness_reader: Any
) -> AgentDeps:
    return AgentDeps(
        llm=None,
        memory_reader=fake_memory_reader,
        memory_writer=fake_memory_writer,
        fitness_reader=fitness_reader,
        clock=lambda: datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_retrieve_context_node_loads_fitness_context(
    fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    reader = _FakeFitnessReader({"totals": {"sessions_completed": 4}, "weight": {"points": 3}})
    state: AgentState = {
        "user_message": "How has my training progress been lately?",
        "user_id": "user-1",
        "safety": SafetyResult(),
    }
    result = retrieve_context_node(
        state, _fitness_deps(fake_memory_reader, fake_memory_writer, reader)
    )
    assert reader.calls == ["user-1"]
    assert any(r.get("tool") == "fitness_context" for r in result["tool_results"])


def test_retrieve_context_node_skips_fitness_when_not_relevant(
    fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    reader = _FakeFitnessReader()
    state: AgentState = {
        "user_message": "How much protein do I need per meal?",
        "user_id": "user-1",
        "safety": SafetyResult(),
    }
    result = retrieve_context_node(
        state, _fitness_deps(fake_memory_reader, fake_memory_writer, reader)
    )
    assert reader.calls == []
    assert all(r.get("tool") != "fitness_context" for r in result.get("tool_results", []))


def test_generate_response_includes_fitness_context(
    fake_llm: Any, fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    fake_llm.response = "Based on your log, you completed four sessions."
    state: AgentState = {
        "user_message": "How has my progress been?",
        "conversation_context": [],
        "tool_results": [
            {
                "tool": "fitness_context",
                "result": {
                    "window_days": 120,
                    "totals": {
                        "sessions_completed": 4,
                        "active_days": 4,
                        "sessions_per_week": 1.0,
                        "current_streak_days": 2,
                        "planned_sessions": 6,
                        "planned_completed": 4,
                        "planned_completion_rate": 0.67,
                    },
                    "weight": {
                        "points": 3,
                        "unit": "kg",
                        "first": {"date": "2026-07-01", "value": 82.0},
                        "latest": {"date": "2026-09-30", "value": 78.0},
                        "change": -4.0,
                    },
                    "recent_sessions": [
                        {
                            "date": "2026-09-20",
                            "name": "Push",
                            "duration_min": 45,
                            "sets": 9,
                            "exercises": ["bench", "overhead press"],
                            "top": {"exercise": "bench", "weight": 80, "unit": "kg", "reps": 5},
                        }
                    ],
                    "personal_records": [
                        {"exercise": "bench", "weight": 80, "unit": "kg", "on": "2026-09-20"}
                    ],
                },
            }
        ],
        "errors": [],
    }
    deps = _deps(fake_llm, fake_memory_reader, fake_memory_writer)
    result = generate_response(state, deps)
    assert result["response"].startswith("Based on your log")
    prompt = fake_llm.calls[-1][1]
    assert "training and progress records" in prompt
    assert "Weight trend" in prompt
    assert "Most recent sessions" in prompt


# ---- personal-data questions answered from the user's own records ----------
def test_personal_data_question_detection() -> None:
    assert wants_personal_data_answer("What do I like to do every day?") is True
    assert wants_personal_data_answer("What are my preferences?") is True
    assert wants_personal_data_answer("What do you know about me?") is True
    # Not personal-data questions: keep normal web/fitness behavior.
    assert wants_personal_data_answer("What are the best protein sources?") is False
    assert wants_personal_data_answer("How has my progress been?") is False


def test_select_tools_skips_web_for_personal_questions() -> None:
    assert _select_tools("What do I like to do every day?") == []
    # A general live-info question still prefers web search.
    assert "web_search" in _select_tools("find the latest protein guidelines?")


def test_generate_response_forbids_web_tools_for_personal_questions(
    fake_memory_reader: Any, fake_memory_writer: Any
) -> None:
    class _ToolLoopLLM:
        def __init__(self) -> None:
            self.tools_passed: list[dict[str, Any]] | None = None

        def __call__(self, system: str, user: str, *, json_mode: bool = False) -> str:
            return "fallback"

        def run_with_tools(self, messages, tools, execute, *, max_iterations: int = 3) -> str:
            self.tools_passed = tools
            return "You told me you like cycling every day."

    llm = _ToolLoopLLM()
    state: AgentState = {
        "user_message": "What do I like to do every day?",
        "conversation_context": [],
        "tool_results": [],
        "errors": [],
        "retrieved_profile": {"interests": ["cycling"]},
    }
    deps = _deps(llm, fake_memory_reader, fake_memory_writer)
    result = generate_response(state, deps)
    assert result["response"].startswith("You told me you like cycling")
    assert llm.tools_passed == []  # no live web tools for personal questions
