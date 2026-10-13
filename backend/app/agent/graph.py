"""LangGraph workflow.

safety_check -> blocked: safe_response -> END   (no tool/memory node is reachable)
             -> personal statement: extract_facts -> detect_changes -> apply_updates
             -> question: retrieve_context -> generate_response
             -> otherwise: generate_response
After memory handling, questions still get context retrieval.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

# Suppress noisy LangGraph pending-deprecation warning about default allowed_objects.
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

from langgraph.graph import END, StateGraph  # noqa: E402

from app.memory.confirmation import Action  # noqa: E402

from .nodes import (  # noqa: E402
    AgentDeps,
    apply_updates_node,
    detect_changes_node,
    extract_facts_node,
    generate_response,
    looks_like_question,
    looks_personal,
    retrieve_context_node,
    safe_response,
    safety_check,
)
from .state import AgentState  # noqa: E402


def route_after_safety(state: AgentState) -> str:
    s = state.get("safety")
    if s is None or s.blocked:
        return "safe_response"
    msg = state.get("user_message", "")
    if looks_personal(msg):
        return "extract_facts"
    return "retrieve_context" if looks_like_question(msg) else "generate_response"


def route_after_updates(state: AgentState) -> str:
    return (
        "retrieve_context"
        if looks_like_question(state.get("user_message", ""))
        else "generate_response"
    )


def route_after_extract(state: AgentState) -> str:
    return "detect_changes" if state.get("extracted_facts") else route_after_updates(state)


def route_after_detect(state: AgentState) -> str:
    if any(d.action is not Action.SKIP for d in state.get("proposed_updates", [])):
        return "apply_updates"
    return route_after_updates(state)


def _bind(
    fn: Callable[[AgentState, AgentDeps], dict[str, Any]], deps: AgentDeps
) -> Callable[[AgentState], dict[str, Any]]:
    def node(state: AgentState) -> dict[str, Any]:
        return fn(state, deps)

    return node


def build_graph(deps: AgentDeps) -> Any:
    """Compile the agent graph with injected dependencies."""
    g = StateGraph(AgentState)
    g.add_node("safety_check", safety_check)
    g.add_node("safe_response", safe_response)
    g.add_node("extract_facts", _bind(extract_facts_node, deps))
    g.add_node("detect_changes", _bind(detect_changes_node, deps))
    g.add_node("apply_updates", _bind(apply_updates_node, deps))
    g.add_node("retrieve_context", _bind(retrieve_context_node, deps))
    g.add_node("generate_response", _bind(generate_response, deps))

    g.set_entry_point("safety_check")
    g.add_conditional_edges(
        "safety_check",
        route_after_safety,
        ["safe_response", "extract_facts", "retrieve_context", "generate_response"],
    )
    g.add_conditional_edges(
        "extract_facts",
        route_after_extract,
        ["detect_changes", "retrieve_context", "generate_response"],
    )
    g.add_conditional_edges(
        "detect_changes",
        route_after_detect,
        ["apply_updates", "retrieve_context", "generate_response"],
    )
    g.add_conditional_edges(
        "apply_updates", route_after_updates, ["retrieve_context", "generate_response"]
    )
    g.add_edge("retrieve_context", "generate_response")
    g.add_edge("generate_response", END)
    g.add_edge("safe_response", END)
    return g.compile()


def run_turn(
    graph: Any, user_id: str, message: str, context: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """Run one turn. `user_id` must come from authentication, never from the message."""
    out: dict[str, Any] = graph.invoke(
        {
            "user_id": user_id,
            "user_message": message,
            "conversation_context": context or [],
            "tool_results": [],
            "errors": [],
        }
    )
    return {"response": str(out.get("response", "")), "tool_results": out.get("tool_results", [])}
