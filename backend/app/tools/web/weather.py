"""Weather and datetime tools (keyless providers)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger(__name__)

OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_WEATHER = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10.0


def _user_friendly_temp(value: float, units: str) -> str:
    if units.lower() == "imperial":
        return f"{value * 9 / 5 + 32:.0f}°F"
    return f"{value:.0f}°C"


def get_weather(location: str, *, units: str = "metric", days: int = 1) -> dict[str, Any]:
    """Return current weather and a short forecast from Open-Meteo."""
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            geo = client.get(OPEN_METEO_GEO, params={"name": location, "count": 1})
            geo.raise_for_status()
            geo_data = geo.json()
            results = geo_data.get("results") or []
            if not results:
                return {
                    "location": location,
                    "error": f"Could not find weather location '{location}'",
                }
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            resolved = results[0].get("name", location)

            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": max(1, min(days, 7)),
            }
            if units.lower() == "imperial":
                params["temperature_unit"] = "fahrenheit"

            weather = client.get(OPEN_METEO_WEATHER, params=params)
            weather.raise_for_status()
            data = weather.json()
    except Exception as exc:
        log.warning("weather lookup failed: %s", exc)
        return {"location": location, "error": f"Weather lookup failed: {type(exc).__name__}"}

    current = data.get("current", {})
    daily = data.get("daily", {})
    forecast: list[dict[str, Any]] = []
    for i, date in enumerate(daily.get("time", [])):
        forecast.append(
            {
                "date": date,
                "max": daily.get("temperature_2m_max", [None] * (i + 1))[i],
                "min": daily.get("temperature_2m_min", [None] * (i + 1))[i],
            }
        )

    return {
        "location": resolved,
        "timezone": data.get("timezone"),
        "current": {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "weather_code": current.get("weather_code"),
        },
        "forecast": forecast,
        "units": units,
    }


def get_datetime(timezone_name: str | None = None) -> dict[str, Any]:
    """Return the current UTC and local date/time."""
    now = datetime.now(timezone.utc)
    local = now
    if timezone_name:
        try:
            from zoneinfo import ZoneInfo

            local = now.astimezone(ZoneInfo(timezone_name))
        except Exception as exc:
            log.warning("invalid timezone %s: %s", timezone_name, exc)
    return {
        "utc_iso": now.isoformat(),
        "local_iso": local.isoformat(),
        "timezone": timezone_name or "UTC",
        "date": local.date().isoformat(),
    }
