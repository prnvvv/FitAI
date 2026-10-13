"""Graph nodes. Each takes state (+ injected deps) and returns a partial state update."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.llm.prompts import RESPONSE_GENERATION
from app.memory.change_detector import MemoryEntry, detect_changes
from app.memory.confirmation import (
    Action,
    ConfirmationPolicy,
    MemoryWriter,
    apply_decisions,
    decide_all,
)
from app.memory.extractor import TextCompleter, extract_facts
from app.safety import SafetyResult, run_safety_rules

from .state import AgentState

log = logging.getLogger(__name__)


class MemoryReader(Protocol):
    """Read-only view of the memory service. Values in canonical units (kg, cm, %)."""

    def get_current_memory(self, user_id: str) -> Mapping[str, MemoryEntry]: ...


class ProfileReader(Protocol):
    """Read-only view of the user profile as pinned core memory."""

    def get_profile(self, user_id: str) -> Mapping[str, object] | None: ...


class Retriever(Protocol):
    """Existing RAG retriever, adapted."""

    def search(self, query: str, user_id: str, k: int = 4) -> list[str]: ...


@dataclass
class AgentDeps:
    llm: TextCompleter
    memory_reader: MemoryReader
    memory_writer: MemoryWriter
    profile_reader: ProfileReader | None = None
    retriever: Retriever | None = None
    policy: ConfirmationPolicy = dc_field(default_factory=ConfirmationPolicy)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


# ---- heuristics (cheap routing; no LLM call) --------------------------------
_PERSONAL = re.compile(
    r"\b(i am|i'm|i weigh|i weighed|i've|i have|i used to|i was|i started|i stopped|i did|i lifted|"
    r"i ran|i take|i took|my|goal)\b|\d\s*(?:kg|kgs|lb|lbs|cm|in|%)", re.I)
_QUESTION = re.compile(
    r"\?|^\s*(how|what|why|when|which|should|can|could|is|are|do|does|suggest|recommend|give me|show me)\b",
    re.I)


def looks_personal(msg: str) -> bool:
    return bool(_PERSONAL.search(msg))


def looks_like_question(msg: str) -> bool:
    return bool(_QUESTION.search(msg))


# ---- safety -------------------------------------------------------------------
def safety_check(state: AgentState) -> dict[str, Any]:
    return {"safety": run_safety_rules(state.get("user_message", ""))}


def safe_response(state: AgentState) -> dict[str, Any]:
    s = state.get("safety") or SafetyResult()
    return {"response": s.response or "I can't help with that request."}


def _blocked(state: AgentState) -> bool:
    s = state.get("safety")
    return s is None or s.blocked  # fail closed: no safety result => no tools


# ---- memory pipeline ------------------------------------------------------------
def extract_facts_node(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if _blocked(state):
        return {}
    res = extract_facts(state["user_message"], deps.llm, deps.clock())
    out: dict[str, Any] = {"extracted_facts": res.facts}
    if res.error:
        out["errors"] = [f"extraction: {res.error}"]
    return out


def _load_memory(state: AgentState, deps: AgentDeps) -> tuple[dict[str, MemoryEntry] | None, list[str]]:
    if state.get("retrieved_memory") is not None:
        return state["retrieved_memory"], []
    try:
        return dict(deps.memory_reader.get_current_memory(state["user_id"])), []
    except Exception as exc:
        log.warning("memory read failed: %s", exc)
        return None, [f"memory_read: {type(exc).__name__}"]


def _load_profile(state: AgentState, deps: AgentDeps) -> dict[str, object] | None:
    if state.get("retrieved_profile") is not None:
        return state["retrieved_profile"]
    if deps.profile_reader is None:
        return None
    try:
        profile = deps.profile_reader.get_profile(state["user_id"])
        return dict(profile) if profile else None
    except Exception as exc:
        log.warning("profile read failed: %s", exc)
        return None


def detect_changes_node(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if _blocked(state) or not state.get("user_id"):
        return {}
    memory, errs = _load_memory(state, deps)
    if memory is None:  # cannot compare => cannot update
        return {"proposed_updates": [], "errors": errs,
                "tool_results": [{"tool": "memory_read", "status": "failed"}]}
    decisions = decide_all(detect_changes(state.get("extracted_facts", []), memory), deps.policy)
    return {"retrieved_memory": memory, "proposed_updates": decisions}


def apply_updates_node(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if _blocked(state) or not state.get("user_id"):
        return {}
    actionable = [d for d in state.get("proposed_updates", []) if d.action is not Action.SKIP]
    results = apply_decisions(state["user_id"], actionable, deps.memory_writer)
    return {"tool_results": [{"tool": "memory_write", **r.model_dump(mode="json")} for r in results]}


def retrieve_context_node(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if _blocked(state) or not state.get("user_id"):
        return {}
    out: dict[str, Any] = {}
    errs: list[str] = []
    memory, e = _load_memory(state, deps)
    errs += e
    if memory is not None:
        out["retrieved_memory"] = memory
    profile = _load_profile(state, deps)
    if profile is not None:
        out["retrieved_profile"] = profile
    if deps.retriever:
        try:
            docs = deps.retriever.search(state["user_message"], state["user_id"])
            out["tool_results"] = [{"tool": "retriever", "docs": docs}]
        except Exception as exc:
            errs.append(f"retriever: {type(exc).__name__}")
    if errs:
        out["errors"] = errs
    return out


# ---- response ---------------------------------------------------------------------
def _status_footer(tool_results: list[dict[str, Any]], errors: list[str]) -> str:
    lines: list[str] = []
    for r in tool_results:
        if r.get("tool") == "memory_read" and r.get("status") == "failed":
            lines.append("I couldn't check your saved profile, so nothing was updated.")
        if r.get("tool") != "memory_write":
            continue
        s, summ = r.get("status"), r.get("summary", r.get("key", ""))
        if s == "applied":
            lines.append(f"Saved: {summ}" + (" (added to history)" if r.get("history_recorded") else ""))
        elif s == "history_recorded":
            lines.append(f"Added to history: {summ}")
        elif s == "pending_created":
            lines.append(f"Please confirm before I save: {summ}")
        elif s == "failed":
            lines.append(f"Couldn't save {r.get('key')}; nothing was changed.")
    return ("\n\n" + "\n".join(dict.fromkeys(lines))) if lines else ""


def _format_profile(mem: dict[str, MemoryEntry], profile: dict[str, object] | None) -> str:
    lines: list[str] = []
    for k, e in mem.items():
        lines.append(f"{k}: {e.value}{' ' + e.unit if e.unit else ''}")
    if profile:
        lines.append("profile: " + ", ".join(f"{k}={v}" for k, v in profile.items() if v))
    return "\n".join(lines) if lines else "(none)"


def generate_response(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    ctx = state.get("conversation_context", [])[-10:]
    history = "\n".join(f"{m.get('role', 'user')}: {str(m.get('content', ''))[:500]}" for m in ctx)
    mem = state.get("retrieved_memory") or {}
    profile = state.get("retrieved_profile")
    profile_text = _format_profile(mem, profile)
    docs = [d for r in state.get("tool_results", []) if r.get("tool") == "retriever" for d in r.get("docs", [])]
    prompt = (f"Conversation so far:\n{history or '(none)'}\n\nUser profile and memory:\n{profile_text}\n\n"
              f"Reference documents:\n{chr(10).join(docs) or '(none)'}\n\nUser message:\n{state['user_message']}")
    try:
        text = deps.llm(RESPONSE_GENERATION, prompt).strip()
    except Exception as exc:
        log.warning("response generation failed: %s", exc)
        text = "Sorry, I couldn't generate a response right now. Please try again."
    return {"response": text + _status_footer(state.get("tool_results", []), state.get("errors", []))}
