"""OpenAI-style tool definitions and a contextual executor for the agent loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.tools.location import find_places, geocode, reverse_geocode
from app.tools.nearby_gyms import nearby_gyms
from app.tools.web.fetch import fetch_url
from app.tools.web.limits import ToolBudget
from app.tools.web.search import WebSearchKit
from app.tools.web.weather import get_datetime, get_weather
from app.tools.web_search import web_search as ddgs_web_search


@dataclass
class ToolContext:
    """Runtime context for executing tools safely."""

    user_id: str
    budget: ToolBudget = field(
        default_factory=lambda: ToolBudget(max_calls=settings.web_max_tool_calls_per_turn)
    )
    profile: dict[str, Any] | None = None


def _web_search_tool(*, name: str = "web_search") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Search the live web for current information such as news, guidelines, "
                "business listings, or general facts. Use only when the user asks for "
                "up-to-date, location-specific, or verifiable information not in memory."
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
                        "description": "Maximum results (1-8).",
                        "minimum": 1,
                        "maximum": 8,
                    },
                    "freshness": {
                        "type": "string",
                        "enum": ["day", "week", "month", "year"],
                        "description": "Optional freshness filter.",
                    },
                },
                "required": ["query"],
            },
        },
    }


def _news_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "news_search",
            "description": (
                "Search for recent news or research. Use for current events, recent studies, "
                "or 'latest' questions. Falls back to a freshness-biased web search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "days": {
                        "type": "integer",
                        "description": "How recent (default 7).",
                        "minimum": 1,
                        "maximum": 365,
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 8,
                    },
                },
                "required": ["query"],
            },
        },
    }


def _fetch_url_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": (
                "Read the main text of a specific web page. Use when the user needs details "
                "from a source found by web_search, or when a snippet is too short. Do not "
                "visit arbitrary untrusted URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the page to read.",
                    },
                },
                "required": ["url"],
            },
        },
    }


def _weather_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get current weather and a short forecast for a location. Use when the user "
                "asks about outdoor training, running, or weather-affected plans."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or area name, e.g. 'Mylapore, Chennai'.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Forecast days (1-7).",
                        "minimum": 1,
                        "maximum": 7,
                    },
                },
                "required": ["location"],
            },
        },
    }


def _datetime_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": (
                "Get the current date and time. Use when the user references today, tomorrow, "
                "or time-sensitive plans. If no timezone is provided, the user's profile "
                "timezone or UTC is used."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone, e.g. 'Asia/Kolkata'. Optional.",
                    },
                },
            },
        },
    }


def _geocode_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "geocode",
            "description": (
                "Convert a place name into latitude/longitude. Use when the user mentions a "
                "location or asks for nearby places and you need coordinates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_text": {
                        "type": "string",
                        "description": "A city, neighbourhood or address.",
                    },
                },
                "required": ["place_text"],
            },
        },
    }


def _find_places_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "find_places",
            "description": (
                "Find gyms, restaurants, clinics, parks or other local places near a location. "
                "Use when the user asks for 'near me', 'near X', or local businesses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "near": {
                        "type": "string",
                        "description": "Location to search near, e.g. 'Mylapore, Chennai'.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional specific name to filter by, e.g. 'Sparkle Gym'.",
                    },
                    "radius_km": {
                        "type": "integer",
                        "description": "Search radius in km (1-20). Default 5.",
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "fitness",
                            "gym",
                            "restaurant",
                            "cafe",
                            "park",
                            "clinic",
                            "hospital",
                            "store",
                        ],
                        "description": "Category of place to find.",
                    },
                },
                "required": ["near"],
            },
        },
    }


def _nearby_gyms_tool(*, name: str = "nearby_gyms") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Find gyms and fitness facilities near a location. Use when the user "
                "asks for gyms nearby. If the user says 'near me' and no location is known, "
                "ask for a city or area."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "A city, neighbourhood, postcode or address.",
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


# Canonical tool definitions exposed to the model. Web/location tools are only
# added at runtime when the corresponding feature flag is enabled.
CORE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _web_search_tool(name="web_search"),
    _web_search_tool(name="web.run"),
    _news_search_tool(),
    _fetch_url_tool(),
    _nearby_gyms_tool(name="nearby_gyms"),
]

LOCATION_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _geocode_tool(),
    _find_places_tool(),
    _weather_tool(),
    _datetime_tool(),
]


def build_executor(ctx: ToolContext) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return a tool executor bound to a user and turn budget."""
    kit = WebSearchKit(ctx.user_id, budget=ctx.budget)
    units = "metric"
    if ctx.profile and isinstance(ctx.profile.get("units"), str):
        units = ctx.profile["units"]
    timezone = ctx.profile.get("timezone") if ctx.profile else None

    def execute(name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name in ("web_search", "web.run", "search"):
            return kit.web_search(
                args.get("query", ""),
                max_results=min(args.get("max_results") or 5, 8),
                freshness=args.get("freshness"),
            )
        if name == "news_search":
            return kit.news_search(
                args.get("query", ""),
                days=args.get("days") or 7,
                max_results=min(args.get("max_results") or 5, 8),
            )
        if name in ("fetch_url", "read_webpage"):
            return fetch_url(args.get("url", ""))
        if name == "get_weather":
            return get_weather(args.get("location", ""), units=units, days=args.get("days") or 1)
        if name == "get_datetime":
            return get_datetime(args.get("timezone") or timezone)
        if name == "geocode":
            return geocode(args.get("place_text", ""))
        if name == "reverse_geocode":
            return reverse_geocode(float(args.get("lat") or 0), float(args.get("lon") or 0))
        if name == "find_places":
            return find_places(
                args.get("query"),
                args.get("near", ""),
                radius_km=args.get("radius_km") or 5,
                category=args.get("category") or "fitness",
            )
        if name in ("nearby_gyms", "find_gyms", "gyms_nearby"):
            return nearby_gyms(args.get("location"), radius_m=args.get("radius_m", 5000))
        return {"error": f"Unknown tool: {name}"}

    return execute


# Legacy static executor kept for backward compatibility when AGENT_WEB_TOOLS is OFF.
# It uses the simple ddgs-based web_search and does not enforce per-turn budgets.
def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool by name with validated arguments."""
    if name in ("web_search", "web.run", "search"):
        return ddgs_web_search(
            args.get("query", ""),
            max_results=args.get("max_results") or args.get("topn") or 5,
        )
    if name in ("fetch_url", "read_webpage"):
        return fetch_url(args.get("url", ""))
    if name in ("nearby_gyms", "find_gyms", "gyms_nearby"):
        return nearby_gyms(args.get("location"), radius_m=args.get("radius_m", 5000))
    return {"error": f"Unknown tool: {name}"}


# Legacy tool definitions for the same backward-compatible path.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _web_search_tool(name="web_search"),
    _web_search_tool(name="web.run"),
    _fetch_url_tool(),
    _nearby_gyms_tool(name="nearby_gyms"),
]
