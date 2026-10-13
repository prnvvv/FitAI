"""Location/geocoding tools (keyless Nominatim by default)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

NOMINATIM_USER_AGENT = "FitAI/0.1 (fitness location assistant)"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
TIMEOUT = 10.0

# Nominatim requires max 1 req/sec; keep a simple last-call throttle.
_last_nominatim_call = 0.0


def _throttled() -> None:
    global _last_nominatim_call
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_nominatim_call = time.monotonic()


def geocode(place_text: str) -> dict[str, Any]:
    """Return lat/lon and display name for a place string."""
    if not place_text or not place_text.strip():
        return {"query": place_text, "error": "Please provide a place name"}

    provider = settings.geocoding_provider
    if provider == "nominatim":
        return _nominatim_geocode(place_text)
    return {"query": place_text, "error": f"Geocoding provider '{provider}' not implemented"}


def _nominatim_geocode(place_text: str) -> dict[str, Any]:
    _throttled()
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(
                NOMINATIM_SEARCH,
                params={"q": place_text, "format": "json", "limit": 1},
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
            if not data:
                return {"query": place_text, "error": f"Could not locate '{place_text}'"}
            result = data[0]
            return {
                "query": place_text,
                "label": result.get("display_name", place_text),
                "lat": round(float(result["lat"]), 5),
                "lon": round(float(result["lon"]), 5),
                "timezone": None,  # would need a second service
            }
    except Exception as exc:
        log.warning("geocode failed: %s", exc)
        return {"query": place_text, "error": f"Geocoding failed: {type(exc).__name__}"}


def reverse_geocode(lat: float, lon: float) -> dict[str, Any]:
    """Return a display name for coordinates."""
    provider = settings.geocoding_provider
    if provider == "nominatim":
        return _nominatim_reverse(lat, lon)
    return {"lat": lat, "lon": lon, "error": f"Geocoding provider '{provider}' not implemented"}


def _nominatim_reverse(lat: float, lon: float) -> dict[str, Any]:
    _throttled()
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(
                NOMINATIM_REVERSE,
                params={"lat": lat, "lon": lon, "format": "json"},
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "lat": lat,
                "lon": lon,
                "label": data.get("display_name", f"{lat}, {lon}"),
                "timezone": None,
            }
    except Exception as exc:
        log.warning("reverse geocode failed: %s", exc)
        return {"lat": lat, "lon": lon, "error": f"Reverse geocoding failed: {type(exc).__name__}"}


def find_places(
    query: str | None,
    near: str,
    *,
    radius_km: int = 5,
    category: str = "fitness",
) -> dict[str, Any]:
    """Find local places near a location using OSM Overpass."""
    provider = settings.places_provider
    if provider == "overpass":
        return _overpass_places(query, near, radius_km, category)
    return {"near": near, "error": f"Places provider '{provider}' not implemented"}


def _overpass_places(
    query: str | None,
    near: str,
    radius_km: int,
    category: str,
) -> dict[str, Any]:
    geo = geocode(near)
    if geo.get("error"):
        return geo
    lat = geo["lat"]
    lon = geo["lon"]
    radius_m = int(radius_km * 1000)

    # Map common categories to OSM tags.
    tag_map = {
        "fitness": '["leisure"="fitness_centre"]',
        "gym": '["leisure"="fitness_centre"]',
        "restaurant": '["amenity"="restaurant"]',
        "cafe": '["amenity"="cafe"]',
        "park": '["leisure"="park"]',
        "clinic": '["amenity"="clinic"]',
        "hospital": '["amenity"="hospital"]',
        "store": '["shop"]',
    }
    tag = tag_map.get(category.lower(), '["leisure"="fitness_centre"]')

    overpass_query = f"""
    [out:json][timeout:25];
    (
      node{tag}(around:{radius_m},{lat},{lon});
      way{tag}(around:{radius_m},{lat},{lon});
    );
    out center 20;
    """

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": overpass_query},
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])
    except Exception as exc:
        log.warning("overpass places failed: %s", exc)
        return {"near": near, "error": f"Places search failed: {type(exc).__name__}"}

    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed")
        key = f"{name}|{el.get('lat')}|{el.get('lon')}"
        if key in seen:
            continue
        seen.add(key)
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        address_parts = [
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
            tags.get("addr:city"),
            tags.get("addr:postcode"),
        ]
        address = ", ".join(p for p in address_parts if p)
        places.append(
            {
                "name": name,
                "category": category,
                "address": address or "Address not available",
                "lat": el_lat,
                "lon": el_lon,
                "map_url": f"https://www.openstreetmap.org/?mlat={el_lat}&mlon={el_lon}#map=17/{el_lat}/{el_lon}",
                "phone": tags.get("phone") or tags.get("contact:phone") or None,
                "website": tags.get("website") or tags.get("contact:website") or None,
                "opening_hours": tags.get("opening_hours") or None,
            }
        )

    return {"near": near, "location_label": geo.get("label"), "places": places}
