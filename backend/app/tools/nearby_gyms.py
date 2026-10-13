"""Nearby gym/fitness facility search using OpenStreetMap data.

Geocoding is done with Nominatim; place discovery uses the Overpass API.
No API key is required. Attribution: data from OpenStreetMap contributors.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

GEOCODE_TIMEOUT = 10.0
OVERPASS_TIMEOUT = 15.0
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass QL query for fitness facilities near a point."""
    return f"""
[out:json][timeout:25];
(
  node["leisure"="fitness_centre"](around:{radius_m},{lat},{lon});
  way["leisure"="fitness_centre"](around:{radius_m},{lat},{lon});
  node["leisure"="sports_centre"](around:{radius_m},{lat},{lon});
  way["leisure"="sports_centre"](around:{radius_m},{lat},{lon});
  node["sport"="fitness"](around:{radius_m},{lat},{lon});
  way["sport"="fitness"](around:{radius_m},{lat},{lon});
)
out center 10;
"""


def _format_address(tags: dict[str, str]) -> str:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
        tags.get("addr:country"),
    ]
    return ", ".join(p for p in parts if p)


def nearby_gyms(location: str | None, *, radius_m: int = 5000) -> dict[str, Any]:
    """Find gyms and fitness facilities near the given location.

    Args:
        location: Free-text location (city, area, postcode). If None or empty,
            the tool returns an error asking for a location.
        radius_m: Search radius in meters (default 5000).

    Returns:
        A dict with ``location``, ``places`` and optional ``error``.
    """
    if not location or not location.strip():
        return {
            "location": None,
            "places": [],
            "error": "Please provide a city, area, or postcode so I can search nearby.",
        }

    try:
        with httpx.Client(timeout=GEOCODE_TIMEOUT) as client:
            geo_resp = client.get(
                NOMINATIM_URL,
                params={"q": location.strip(), "format": "json", "limit": 1},
                headers={"User-Agent": "FitAI/0.1 (fitness search assistant)"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            if not geo_data:
                return {
                    "location": location,
                    "places": [],
                    "error": f"Could not locate '{location}'. Try a city or postcode.",
                }
            lat = float(geo_data[0]["lat"])
            lon = float(geo_data[0]["lon"])
    except Exception as exc:
        log.warning("geocoding failed for '%s': %s", location, exc)
        return {
            "location": location,
            "places": [],
            "error": f"Could not look up location: {type(exc).__name__}",
        }

    try:
        with httpx.Client(timeout=OVERPASS_TIMEOUT) as client:
            over_resp = client.post(
                OVERPASS_URL,
                data={"data": _overpass_query(lat, lon, radius_m)},
                headers={"User-Agent": "FitAI/0.1 (fitness search assistant)"},
            )
            over_resp.raise_for_status()
            elements = over_resp.json().get("elements", [])
    except Exception as exc:
        log.warning("overpass query failed: %s", exc)
        return {
            "location": location,
            "places": [],
            "error": f"Could not search nearby facilities: {type(exc).__name__}",
        }

    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed fitness facility")
        key = f"{name}|{el.get('lat')}|{el.get('lon')}"
        if key in seen:
            continue
        seen.add(key)
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        places.append(
            {
                "name": name,
                "address": _format_address(tags) or "Address not available",
                "type": tags.get("leisure") or tags.get("sport") or "fitness",
                "lat": el_lat,
                "lon": el_lon,
                "map_url": f"https://www.openstreetmap.org/?mlat={el_lat}&mlon={el_lon}#map=17/{el_lat}/{el_lon}",
            }
        )

    return {"location": location, "places": places}
