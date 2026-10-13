"""OpenAI-style tool definitions for the Groq tool-calling loop."""

from __future__ import annotations

from typing import Any

from app.tools.nearby_gyms import nearby_gyms
from app.tools.web_fetch import fetch_url
from app.tools.web_search import web_search


def _web_search_tool(*, name: str = "web_search") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Search the live web for current information such as news, guidelines, "
                "business listings, or general facts. Use this when the user asks for "
                "something that requires up-to-date or location-specific information "
                "not present in the conversation memory or uploaded library."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A concise, specific search query in English.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (1-10).",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
        },
    }


def _nearby_gyms_tool(*, name: str = "nearby_gyms") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Find gyms and fitness facilities near a location. Use this when the user "
                "asks for gyms nearby, places to work out, or fitness centres in a specific "
                "area. If the user says 'near me' and no location is known, ask them for a "
                "city or area instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "A city, neighbourhood, postcode or address to search near, "
                            "e.g. 'Mylapore, Chennai' or 'London N1'."
                        ),
                    },
                    "radius_m": {
                        "type": "integer",
                        "description": "Search radius in metres (1000-20000). Default 5000.",
                        "minimum": 1000,
                        "maximum": 20000,
                    },
                },
                "required": ["location"],
            },
        },
    }


def _fetch_url_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Retrieve the readable text of a specific web page. Use after a web search "
                "when the user needs details from a particular source or when a search snippet "
                "is too short. Do not use this to visit arbitrary untrusted URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the page to retrieve.",
                    },
                },
                "required": ["url"],
            },
        },
    }


# Expose the canonical names plus aliases some models use for built-in web search.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _web_search_tool(name="web_search"),
    _web_search_tool(name="web.run"),
    _fetch_url_tool(),
    _nearby_gyms_tool(name="nearby_gyms"),
]


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool by name with validated arguments.

    Also recognises a few aliases that models (including OpenAI-hosted models on
    Groq) sometimes emit for built-in web search.
    """
    if name in ("web_search", "web.run", "search"):
        return web_search(
            args.get("query", ""),
            max_results=args.get("max_results") or args.get("topn") or 5,
        )
    if name == "fetch_url":
        return fetch_url(args.get("url", ""))
    if name in ("nearby_gyms", "find_gyms", "gyms_nearby"):
        return nearby_gyms(args.get("location"), radius_m=args.get("radius_m", 5000))
    return {"error": f"Unknown tool: {name}"}
