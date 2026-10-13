"""Typed LangGraph state."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.memory.change_detector import MemoryEntry
from app.memory.confirmation import Decision
from app.memory.extractor import ExtractedFact
from app.safety import SafetyResult

__all__ = ["AgentState", "SafetyResult"]


class AgentState(TypedDict, total=False):
    user_message: str
    user_id: str  # authenticated ID, set by caller only
    conversation_context: list[dict[str, str]]  # [{"role","content"}, ...]
    retrieved_memory: dict[str, MemoryEntry]
    retrieved_profile: dict[str, object] | None  # pinned core memory from user profile
    extracted_facts: list[ExtractedFact]
    proposed_updates: list[Decision]
    tool_results: Annotated[list[dict[str, Any]], operator.add]  # retrieval + memory write outcomes
    safety: SafetyResult
    response: str
    sources: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    errors: Annotated[list[str], operator.add]
