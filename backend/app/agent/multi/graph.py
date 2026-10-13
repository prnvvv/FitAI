"""Multi-agent orchestrator behind AGENT_MULTI_AGENT.

Topology: router -> (personal fallback | web/local research -> synthesizer).
The existing single-agent graph handles pure personal-statement turns; this
orchestrator handles questions that need live web or local context.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.multi.prompts import (
    LOCAL_BRIEF_PROMPT,
    ROUTER_PROMPT,
    SYNTHESIZER_PROMPT,
    WEB_RESEARCH_PLAN_PROMPT,
    WEB_RESEARCH_SYNTHESIZE_PROMPT,
)
from app.agent.multi.state import MultiAgentState
from app.agent.nodes import AgentDeps, _format_profile
from app.core.config import settings
from app.llm.client import GroqClient
from app.tools.location import find_places
from app.tools.web.fetch import fetch_url
from app.tools.web.providers.registry import SearchClient
from app.tools.web.weather import get_weather

log = logging.getLogger(__name__)

_MAX_RESEARCH_SOURCES = 4


def _llm(model: str | None = None) -> GroqClient:
    return GroqClient(api_key=settings.groq_api_key, model=model or settings.groq_model)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _safe_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        # Try to extract the first JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass
    return {}


def _load_personal_context(state: MultiAgentState, deps: AgentDeps) -> str:
    memory = {}
    if deps.memory_reader:
        try:
            memory = dict(deps.memory_reader.get_current_memory(state["user_id"]))
        except Exception as exc:
            log.warning("multi-agent memory read failed: %s", exc)
    profile = state.get("retrieved_profile")
    return _format_profile(memory, profile)


def router_node(state: MultiAgentState, deps: AgentDeps) -> dict[str, Any]:
    """Classify the turn into a route category."""
    personal_context = _load_personal_context(state, deps)
    prompt = ROUTER_PROMPT.format(
        message=state["user_message"],
        profile_context=personal_context or "(none)",
        today=_today(),
    )
    route = "mixed"
    try:
        text = _llm(settings.router_model)(
            "You classify user intent for a fitness assistant.",
            prompt,
            json_mode=True,
        )
        parsed = _safe_json(text)
        route = str(parsed.get("category", "mixed"))
    except Exception as exc:
        log.warning("router failed, defaulting to mixed: %s", exc)
    if route not in {"direct", "personal", "web", "local", "mixed"}:
        route = "mixed"
    return {
        "route": route,
        "tool_results": [{"tool": "router", "route": route}],
    }


def _resolve_location(state: MultiAgentState) -> dict[str, Any]:
    """Pick a location string from message, profile or browser (not implemented server-side)."""
    msg = state["user_message"].lower()
    profile = state.get("retrieved_profile") or {}
    # explicit place in message (very naive extraction)
    import re

    match = re.search(r"near\s+([a-z\s,]+)(?:\?|$)", msg)
    if match:
        return {"label": match.group(1).strip(), "source": "message"}
    if profile.get("location"):
        return {"label": profile["location"], "source": "profile"}
    return {"label": None, "source": None}


def web_research_node(state: MultiAgentState, deps: AgentDeps) -> dict[str, Any]:
    """Plan queries, search, fetch top pages, and produce a web brief."""
    if state.get("route") not in {"web", "mixed"}:
        return {"web_brief": None}

    plan_prompt = WEB_RESEARCH_PLAN_PROMPT.format(message=state["user_message"])
    try:
        plan_text = _llm(settings.research_model)(
            "You plan web research queries.", plan_prompt, json_mode=True
        )
        plan = _safe_json(plan_text)
        queries = plan.get("queries", [state["user_message"]])
    except Exception as exc:
        log.warning("web research planning failed: %s", exc)
        queries = [state["user_message"]]

    client = SearchClient()
    results = client.search_all(queries, max_results=6)

    # Fetch top pages up to budget.
    fetched: list[dict[str, Any]] = []
    for r in results[:_MAX_RESEARCH_SOURCES]:
        page = fetch_url(r.url)
        if not page.get("error"):
            fetched.append(
                {
                    "title": r.title,
                    "url": r.url,
                    "domain": r.source_domain,
                    "text": page.get("text", "")[:1500],
                }
            )

    research_text = "\n\n".join(f"Source: {s['title']} ({s['url']})\n{s['text']}" for s in fetched)
    if not research_text:
        return {
            "web_brief": {
                "findings": "No reliable web sources were found.",
                "sources": [],
                "confidence": "low",
                "gaps": "No results",
            },
            "tool_results": [{"tool": "web_search", "queries": queries, "sources": 0}],
        }

    synth_prompt = WEB_RESEARCH_SYNTHESIZE_PROMPT.format(research_text=research_text)
    try:
        brief_text = _llm(settings.research_model)(
            "You synthesize web research.", synth_prompt, json_mode=True
        )
        brief = _safe_json(brief_text)
    except Exception as exc:
        log.warning("web research synthesis failed: %s", exc)
        brief = {
            "findings": "Could not synthesize web results.",
            "sources": [],
            "confidence": "low",
            "gaps": "Synthesis failed",
        }

    brief["sources"] = [{"title": s["title"], "url": s["url"]} for s in fetched]
    return {
        "web_brief": brief,
        "tool_results": [
            {
                "tool": "web_search",
                "queries": queries,
                "sources": len(fetched),
            },
            {
                "tool": "read_webpage",
                "pages": len(fetched),
            },
        ],
    }


def local_research_node(state: MultiAgentState, deps: AgentDeps) -> dict[str, Any]:
    """Resolve location, run places/weather, and produce a local brief."""
    if state.get("route") not in {"local", "mixed"}:
        return {"local_brief": None}

    loc = _resolve_location(state)
    if not loc["label"]:
        return {
            "local_brief": {
                "findings": "I don't know your location. Please add one in your profile or mention an area.",
                "places": [],
                "confidence": "low",
                "gaps": "No location",
            },
            "tool_results": [{"tool": "find_places", "location": None, "category": "fitness"}],
        }

    # Determine if this is a business-name search or a category search.
    msg = state["user_message"].lower()
    category = "fitness"
    query = None
    if "gym" in msg or "fitness" in msg:
        category = "fitness"
    elif "restaurant" in msg or "food" in msg or "cafe" in msg:
        category = "restaurant"
    elif "park" in msg:
        category = "park"
    elif "clinic" in msg or "hospital" in msg or "doctor" in msg:
        category = "clinic"

    # If the user asks for a named place, pull a likely name from the message.
    named_match = next(
        (word for word in msg.split() if word[0].isupper() and len(word) > 3),
        None,
    )
    if named_match:
        query = named_match

    places_result = find_places(query=query, near=loc["label"], radius_km=5, category=category)
    profile_units = str((state.get("retrieved_profile") or {}).get("units") or "metric")
    weather = get_weather(loc["label"], units=profile_units, days=1)

    local_data = {
        "location": loc,
        "places": places_result.get("places", []),
        "weather": weather,
    }
    prompt = LOCAL_BRIEF_PROMPT.format(
        message=state["user_message"],
        location_context=json.dumps(loc),
        local_data=json.dumps(local_data, default=str),
    )
    try:
        brief_text = _llm(settings.research_model)(
            "You synthesize local information.", prompt, json_mode=True
        )
        brief = _safe_json(brief_text)
    except Exception as exc:
        log.warning("local research synthesis failed: %s", exc)
        brief = {
            "findings": "Could not synthesize local results.",
            "places": [],
            "confidence": "low",
            "gaps": "Synthesis failed",
        }

    brief["places"] = places_result.get("places", [])
    brief["weather"] = weather
    return {
        "local_brief": brief,
        "tool_results": [
            {
                "tool": "find_places",
                "location": loc["label"],
                "category": category,
                "places": len(places_result.get("places", [])),
            },
            {
                "tool": "get_weather",
                "location": loc["label"],
                "units": profile_units,
            },
        ],
    }


def synthesizer_node(state: MultiAgentState, deps: AgentDeps) -> dict[str, Any]:
    """Merge briefs and write the final answer."""
    personal_context = state.get("personal_context") or _load_personal_context(state, deps)
    web_brief = state.get("web_brief") or {}
    local_brief = state.get("local_brief") or {}

    web_section = ""
    if web_brief:
        web_section = f"Web research brief:\n{web_brief.get('findings', '')}\nSources: {json.dumps(web_brief.get('sources', []))}\n"
    local_section = ""
    if local_brief:
        local_section = f"Local brief:\n{local_brief.get('findings', '')}\n"

    prompt = SYNTHESIZER_PROMPT.format(
        message=state["user_message"],
        personal_context=personal_context or "(none)",
        web_section=web_section,
        local_section=local_section,
    )
    try:
        text = _llm(settings.synth_model)(
            "You are FitAI, a helpful fitness assistant.", prompt
        ).strip()
    except Exception as exc:
        log.warning("synthesizer failed: %s", exc)
        text = "Sorry, I couldn't put together an answer right now. Please try again."

    # Build sources list from briefs for citation rendering.
    sources: list[dict[str, Any]] = []
    for s in web_brief.get("sources", []):
        if s.get("url") and s not in sources:
            sources.append(s)
    for p in local_brief.get("places", []):
        url = p.get("map_url") or p.get("website")
        if url:
            entry = {"title": p.get("name", "Place"), "url": url}
            if entry not in sources:
                sources.append(entry)

    # Number sources.
    numbered = [{**s, "index": i} for i, s in enumerate(sources, start=1)]
    return {"response": text, "sources": numbered, "actions": []}


def route_decision(state: MultiAgentState) -> str:
    return state.get("route", "mixed")


def build_multi_graph(deps: AgentDeps) -> Any:
    """Compile the multi-agent graph."""
    g = StateGraph(MultiAgentState)
    g.add_node("router", lambda state: router_node(state, deps))
    g.add_node("web_research", lambda state: web_research_node(state, deps))
    g.add_node("local_research", lambda state: local_research_node(state, deps))
    g.add_node("synthesize", lambda state: synthesizer_node(state, deps))

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        route_decision,
        {
            "direct": "synthesize",
            "personal": END,  # caller should fall back to single-agent graph
            "web": "web_research",
            "local": "local_research",
            "mixed": "web_research",
        },
    )
    g.add_edge("web_research", "local_research")
    g.add_edge("local_research", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


def run_multi_turn(
    deps: AgentDeps,
    user_id: str,
    message: str,
    context: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run one turn through the multi-agent orchestrator.

    Falls back to the single-agent graph if routing says the turn is personal
    or if anything goes wrong.
    """
    from app.agent.graph import build_graph, run_turn

    graph = build_multi_graph(deps)
    try:
        out: dict[str, Any] = graph.invoke(
            {
                "user_id": user_id,
                "user_message": message,
                "conversation_context": context or [],
                "tool_results": [],
                "errors": [],
                "route": "mixed",
                "web_brief": None,
                "local_brief": None,
                "personal_context": "",
                "final_response": "",
                "final_sources": [],
            }
        )
    except Exception as exc:
        log.warning("multi-agent graph failed, falling back to single agent: %s", exc)
        return run_turn(build_graph(deps), user_id, message, context)

    if out.get("route") == "personal":
        return run_turn(build_graph(deps), user_id, message, context)

    tool_results = list(out.get("tool_results", []))
    tool_results.append({"tool": "multi_agent", "route": out.get("route")})
    return {
        "response": out.get("response", ""),
        "sources": out.get("sources", []),
        "actions": out.get("actions", []),
        "tool_results": tool_results,
    }
