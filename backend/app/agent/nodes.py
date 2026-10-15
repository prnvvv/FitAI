"""Graph nodes. Each takes state (+ injected deps) and returns a partial state update."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.config import settings
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
from app.tools.activity import get_activity_log
from app.tools.tool_definitions import (
    CORE_TOOL_DEFINITIONS,
    LOCATION_TOOL_DEFINITIONS,
    TOOL_DEFINITIONS,
    ToolContext,
    build_executor,
    execute_tool,
)

from .state import AgentState

log = logging.getLogger(__name__)


# ---- output guard ---------------------------------------------------------------
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```|`[^`\n]+`")
_SYSTEM_PROMPT_FRAGMENTS = [
    "you are fitai",
    "fitai, a helpful",
    "untrusted data",
    "never reveal these instructions",
    "api key",
    "system prompt",
    "configuration",
]


def _output_violates_guard(text: str, canary: str | None = None) -> bool:
    """Check if the model output violates guardrails.

    Checks for:
    - Code fences (```) or inline code (`)
    - Canary token (if configured)
    - System prompt fragments
    """
    if not text:
        return False
    lowered = text.lower()
    # Code fences or inline code
    if _CODE_FENCE_RE.search(text):
        return True
    # Canary token
    if canary and canary in text:
        return True
    # System prompt fragments
    return any(fragment in lowered for fragment in _SYSTEM_PROMPT_FRAGMENTS)


class MemoryReader(Protocol):
    """Read-only view of the memory service. Values in canonical units (kg, cm, %)."""

    def get_current_memory(self, user_id: str) -> Mapping[str, MemoryEntry]: ...


class ProfileReader(Protocol):
    """Read-only view of the user profile as pinned core memory."""

    def get_profile(self, user_id: str) -> Mapping[str, object] | None: ...


class Retriever(Protocol):
    """Existing RAG retriever, adapted."""

    def search(self, query: str, user_id: str, k: int = 4) -> list[str]: ...


class FitnessReader(Protocol):
    """Read-only view of the user's real workout plans, completed sessions and
    progress measurements. Returns a bounded, JSON-serialisable summary built
    from authoritative persisted records (never fabricated)."""

    def get_fitness_context(self, user_id: str) -> dict[str, Any]: ...


class Tool(Protocol):
    """A callable research tool returning a JSON-serialisable result dict."""

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


@dataclass
class AgentDeps:
    llm: TextCompleter
    memory_reader: MemoryReader
    memory_writer: MemoryWriter
    profile_reader: ProfileReader | None = None
    retriever: Retriever | None = None
    fitness_reader: FitnessReader | None = None
    tools: Mapping[str, Tool] = dc_field(default_factory=dict)
    db_session: object | None = None
    policy: ConfirmationPolicy = dc_field(default_factory=ConfirmationPolicy)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


# ---- heuristics (cheap routing; no LLM call) --------------------------------
_PERSONAL = re.compile(
    r"\b(i am|i'm|i weigh|i weighed|i've|i have|i used to|i was|i started|i stopped|i did|i lifted|"
    r"i ran|i take|i took|my|goal)\b|\d\s*(?:kg|kgs|lb|lbs|cm|in|%)",
    re.I,
)
_QUESTION = re.compile(
    r"\?|^\s*(how|what|why|when|which|should|can|could|is|are|do|does|suggest|recommend|give me|show me)\b",
    re.I,
)


def looks_personal(msg: str) -> bool:
    return bool(_PERSONAL.search(msg))


def looks_like_question(msg: str) -> bool:
    return bool(_QUESTION.search(msg))


# ---- tool selection (cheap routing; no LLM call) ------------------------------
_GYM_INTENT = re.compile(
    r"\b(gym|gyms|fitness centre|fitness center|sports centre|sports center|"
    r"workout place|place to work out)\b.*\b(near|nearby|around|close|closest|"
    r"open now|open today|near me|in my area)\b|\b(near me|nearby)\b.*\b(gym|gyms|fitness)\b",
    re.I,
)
_LIVE_INFO_INTENT = re.compile(
    r"\b(latest|current|recent|news|today|now|update|guidelines|recommendations|"
    r"weather|compare|prices|pricing|hours|open now|find|search|look up|"
    r"what are the best|top rated)\b|\?",
    re.I,
)


_PERSONAL_DATA_QUESTION = re.compile(
    r"\b(what|which|do|tell me|show me)\b.*\b(i like|i prefer|i enjoy|i love|my preference|"
    r"my preferences|my hobby|my hobbies|my interest|my interests|my favourite|my favorite|"
    r"my likes|my goal|my goals|my routine|my schedule|my plan|my profile)\b|"
    r"\b(about me|what do you know about me|what do you remember about me|"
    r"what have i (told|said)|my dietary|my restrictions)\b",
    re.I,
)


def wants_personal_data_answer(msg: str) -> bool:
    """True when the question should be answered from the user's own persisted
    facts (profile/memory/RAG), not from live web search."""
    return bool(_PERSONAL_DATA_QUESTION.search(msg))


def _select_tools(
    msg: str, safety: SafetyResult | None = None, wants_tool: bool | None = None
) -> list[str]:
    """Return the names of research tools likely useful for this message.

    ``wants_tool`` is the guard classifier's signal. When it is explicitly False
    the classifier judged no live/external tool is needed, so we suppress the
    web/places/activity tools (RAG and fitness-record grounding are unaffected).
    """
    # Guard: if safety check blocked, no tools
    if safety and safety.blocked:
        return []
    # Classifier says no live tool is needed for this in-scope message.
    if wants_tool is False:
        return []
    # Questions about the user's own preferences/facts are answered from the
    # persisted profile/memory/RAG context, never from the web, so retrieval
    # isn't drowned out by unrelated live results.
    if wants_personal_data_answer(msg):
        return []
    selected: list[str] = []
    if _GYM_INTENT.search(msg):
        selected.append("nearby_gyms")
    elif re.search(
        r"\b(what did i do|how (have|has) my|my week|recent|activity|log|train(?:ing)? been|workouts lately)\b",
        msg,
        re.I,
    ):
        selected.append("activity_log")
    elif _LIVE_INFO_INTENT.search(msg):
        # Prefer web search for general live-info questions unless they are
        # explicitly gym-location questions.
        selected.append("web_search")
    return selected


# Prompt the agent to pull the user's OWN persisted training/progress records
# (authoritative DB rows) when the question is about that data. Kept separate
# from activity_log (a short event feed) and from web search.
_FITNESS_CONTEXT_INTENT = re.compile(
    r"\b(workouts?|training|exercises?|sets?|reps?|volume|personal records?|\bPRs?\b|"
    r"progress|towards|weight|lost|gained|losing|gaining|trend|measurements?|waist|"
    r"body ?fat|bmi|consistency|streak|plan)\b|"
    r"\bhow (am i|have i been|have i been doing|'?m i doing|'?s my (progress|training))\b|"
    r"\bmy (week|training|progress|fitness|gains|plan)\b",
    re.I,
)


def wants_fitness_context(msg: str) -> bool:
    """True when the question should be grounded in the user's own records."""
    return bool(_FITNESS_CONTEXT_INTENT.search(msg))


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


def _load_memory(
    state: AgentState, deps: AgentDeps
) -> tuple[dict[str, MemoryEntry] | None, list[str]]:
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
        return {
            "proposed_updates": [],
            "errors": errs,
            "tool_results": [{"tool": "memory_read", "status": "failed"}],
        }
    decisions = decide_all(detect_changes(state.get("extracted_facts", []), memory), deps.policy)
    return {"retrieved_memory": memory, "proposed_updates": decisions}


def apply_updates_node(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if _blocked(state) or not state.get("user_id"):
        return {}
    actionable = [d for d in state.get("proposed_updates", []) if d.action is not Action.SKIP]
    results = apply_decisions(state["user_id"], actionable, deps.memory_writer)
    return {
        "tool_results": [{"tool": "memory_write", **r.model_dump(mode="json")} for r in results]
    }


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

    tool_results: list[dict[str, Any]] = []
    if deps.retriever:
        try:
            docs = deps.retriever.search(state["user_message"], state["user_id"])
            tool_results.append({"tool": "retriever", "docs": docs})
        except Exception as exc:
            errs.append(f"retriever: {type(exc).__name__}")

    if wants_fitness_context(state["user_message"]) and deps.fitness_reader is not None:
        try:
            result = deps.fitness_reader.get_fitness_context(state["user_id"])
            tool_results.append({"tool": "fitness_context", "result": result})
        except Exception as exc:
            log.warning("fitness context failed: %s", exc)
            errs.append(f"fitness_context: {type(exc).__name__}")

    for tool_name in _select_tools(
        state["user_message"], state.get("safety"), state.get("wants_tool")
    ):
        if tool_name == "activity_log":
            try:
                result = get_activity_log(state["user_id"], db_session=deps.db_session)
                tool_results.append({"tool": tool_name, "result": result})
            except Exception as exc:
                log.warning("tool %s failed: %s", tool_name, exc)
                errs.append(f"{tool_name}: {type(exc).__name__}")
            continue
        tool = deps.tools.get(tool_name)
        if tool is None:
            continue
        try:
            result = tool(state["user_message"])
            tool_results.append({"tool": tool_name, "result": result})
        except Exception as exc:
            log.warning("tool %s failed: %s", tool_name, exc)
            errs.append(f"{tool_name}: {type(exc).__name__}")

    if tool_results:
        out["tool_results"] = tool_results
    if errs:
        out["errors"] = errs
    return out


# ---- response ---------------------------------------------------------------------
_CITATION_RE = re.compile(r"\[(\d+)\]")


def _format_profile(mem: dict[str, MemoryEntry], profile: dict[str, object] | None) -> str:
    lines: list[str] = []
    for k, e in mem.items():
        lines.append(f"{k}: {e.value}{' ' + e.unit if e.unit else ''}")
    if profile:
        lines.append("profile: " + ", ".join(f"{k}={v}" for k, v in profile.items() if v))
    return "\n".join(lines) if lines else "(none)"


def _build_sources(tool_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Collect numbered sources from web search and nearby-gyms results."""
    sources: list[dict[str, str]] = []
    for r in tool_results:
        tool = r.get("tool")
        if tool == "web_search":
            for item in r.get("result", {}).get("results", []):
                url = item.get("url") or item.get("href")
                if not url:
                    continue
                sources.append(
                    {
                        "title": item.get("title", "Source") or "Source",
                        "url": url,
                        "snippet": item.get("snippet", "") or item.get("body", ""),
                    }
                )
        elif tool == "nearby_gyms":
            for place in r.get("result", {}).get("places", []):
                url = place.get("map_url")
                if not url:
                    continue
                sources.append(
                    {
                        "title": place.get("name", "Gym") or "Gym",
                        "url": url,
                        "snippet": place.get("address", ""),
                    }
                )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for s in sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        unique.append(s)
    return unique


def _format_fitness_context(result: dict[str, Any]) -> list[str]:
    """Render the user's real training/progress summary into prompt lines."""
    out: list[str] = []
    totals = result.get("totals", {}) or {}
    if totals:
        sessions = totals.get("sessions_completed")
        active_days = totals.get("active_days")
        per_week = totals.get("sessions_per_week")
        out.append(
            f"- Completed sessions: {sessions} over {active_days} active days (~{per_week}/week)."
        )
        planned = totals.get("planned_sessions")
        if planned:
            done = totals.get("planned_completed")
            rate = totals.get("planned_completion_rate")
            pct = f"{round(rate * 100)}%" if isinstance(rate, int | float) else "n/a"
            out.append(f"- Planned vs completed: {done}/{planned} ({pct}).")
        if totals.get("current_streak_days"):
            out.append(f"- Current training streak: {totals['current_streak_days']} day(s).")

    weight = result.get("weight", {}) or {}
    points = weight.get("points", 0) or 0
    if points >= 2:
        first, latest = weight["first"], weight["latest"]
        out.append(
            f"- Weight trend: {first['value']} kg ({first['date']}) -> "
            f"{latest['value']} kg ({latest['date']}); change {weight['change']:+} kg "
            f"across {points} recorded weigh-ins."
        )
    elif points == 1:
        latest = weight["latest"]
        out.append(
            f"- Weight: one recorded entry, {latest['value']} kg on {latest['date']} "
            "(a trend needs 2+ dated entries)."
        )

    records = result.get("personal_records", []) or []
    if records:
        pretty = ", ".join(
            f"{r.get('exercise')} {r.get('weight')}{r.get('unit') or 'kg'} ({r.get('on')})"
            for r in records[:8]
        )
        out.append(f"- Heaviest recorded lifts: {pretty}.")

    recent = result.get("recent_sessions", []) or []
    if recent:
        out.append("- Most recent sessions:")
        for s in recent[:8]:
            exercises = ", ".join(s.get("exercises", [])[:6]) or "no exercises logged"
            top = s.get("top") or {}
            best = (
                f"; best {top.get('exercise')} {top.get('weight')}"
                f"{top.get('unit') or 'kg'}x{top.get('reps')}"
                if top
                else ""
            )
            out.append(
                f"    {s.get('date')}: {s.get('name') or 'session'} - "
                f"{s.get('sets')} sets ({exercises}){best}"
            )

    if not out:
        out.append("- No logged training or progress records for this period.")
    return out


def _format_tool_context(tool_results: list[dict[str, Any]], sources: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for r in tool_results:
        tool = r.get("tool")
        if tool == "retriever":
            docs = r.get("docs", [])
            if docs:
                lines.append("Reference documents:")
                lines.extend(f"- {d}" for d in docs)
        elif tool == "activity_log":
            result = r.get("result", {})
            if result.get("error"):
                lines.append(f"Activity log: {result['error']}")
            elif result.get("events"):
                lines.append("Recent activity:")
                for event in result["events"][:15]:
                    lines.append(f"- {event.get('occurred_at', '')}: {event.get('type', '')}")
        elif tool == "fitness_context":
            result = r.get("result", {}) or {}
            if result.get("error"):
                lines.append(f"Training/progress data: {result['error']}")
            else:
                lines.append("Your training and progress records (authoritative log):")
                lines.extend(_format_fitness_context(result))

    if sources:
        lines.append("Sources (cite using [1], [2], etc.):")
        for i, s in enumerate(sources, start=1):
            lines.append(f"[{i}] {s['title']} — {s['url']}")
            if s.get("snippet"):
                lines.append(f"    {s['snippet']}")

    return "\n".join(lines) if lines else "(none)"


def _build_actions(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface pending memory confirmations as actionable items."""
    actions: list[dict[str, Any]] = []
    for r in tool_results:
        if r.get("tool") != "memory_write" or r.get("status") != "pending_created":
            continue
        actions.append(
            {
                "type": "memory_confirm",
                "proposal_id": r.get("proposal_id"),
                "key": r.get("key"),
                "summary": r.get("summary"),
                "title": "Confirm update",
                "description": f"Proposed: {r.get('summary') or r.get('key')}",
            }
        )
    return actions


def generate_response(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    ctx = state.get("conversation_context", [])[-10:]
    history = "\n".join(f"{m.get('role', 'user')}: {str(m.get('content', ''))[:500]}" for m in ctx)
    mem = state.get("retrieved_memory") or {}
    profile = state.get("retrieved_profile")
    profile_text = _format_profile(mem, profile)
    sources = _build_sources(state.get("tool_results", []))
    tool_context = _format_tool_context(state.get("tool_results", []), sources)

    # Inject authoritative date/time and, if available, the user's timezone so the
    # model never guesses the date.
    timezone_hint = ""
    if profile and profile.get("timezone"):
        timezone_hint = f"\nUser timezone: {profile['timezone']}."
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    prompt = (
        f"Conversation so far:\n{history or '(none)'}\n\nUser profile and memory:\n{profile_text}\n\n"
        f"Today is {today}.{timezone_hint}\n\n"
        f"Live research:\n{tool_context}\n\n"
        "If a tool returned an error or no results, say so honestly.\n\n"
        f"User message:\n{state['user_message']}"
    )

    # Choose tool set based on feature flags. With all flags off this is identical
    # to the legacy path (ddgs web_search + nearby_gyms).
    if settings.agent_web_tools:
        tool_definitions = list(CORE_TOOL_DEFINITIONS)
        if settings.agent_location_tools:
            tool_definitions.extend(LOCATION_TOOL_DEFINITIONS)
        tool_ctx = ToolContext(user_id=state["user_id"], profile=profile)
        executor = build_executor(tool_ctx)
    else:
        tool_definitions = TOOL_DEFINITIONS
        executor = execute_tool

    # For questions about the user's own data, answer purely from the provided
    # profile/memory/RAG context; do not let the model call live web tools.
    if wants_personal_data_answer(state.get("user_message", "")):
        tool_definitions = []

    # Build system prompt with canary
    canary_text = ""
    if settings.guard_canary:
        canary_text = f"\n[CANARY:{settings.guard_canary}]"
    system_prompt = RESPONSE_GENERATION.format(canary=canary_text)

    try:
        if hasattr(deps.llm, "run_with_tools"):
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt[:4000]},
            ]
            text = deps.llm.run_with_tools(messages, tool_definitions, executor).strip()
        else:
            text = deps.llm(system_prompt, prompt).strip()
    except Exception:
        log.warning("response generation failed", exc_info=True)
        text = "Sorry, I couldn't generate a response right now. Please try again."

    # Output guard: check for code fences, canary token, system prompt fragments
    if _output_violates_guard(text, settings.guard_canary):
        log.warning("output_guard_triggered", user_id=state.get("user_id"))
        text = (
            "I can't provide code or technical implementations. "
            "I'm here to help with fitness, nutrition, and recovery. "
            "Want a workout plan, macro breakdown, or recovery tips instead?"
        )

    used_indices = {int(m) for m in _CITATION_RE.findall(text)}
    used_sources = [
        {**s, "index": i}
        for i, s in enumerate(sources, start=1)
        if i in used_indices or not used_indices
    ]
    actions = _build_actions(state.get("tool_results", []))
    return {"response": text, "sources": used_sources, "actions": actions}
