"""Location helper endpoints (geocoding)."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser
from app.tools.location import geocode, reverse_geocode

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/geocode", status_code=status.HTTP_200_OK)
def geocode_place(
    current_user: CurrentUser,
    place: str = Query(min_length=1, max_length=200),
) -> dict[str, object]:
    """Geocode a place name to coordinates."""
    return geocode(place)


@router.get("/reverse", status_code=status.HTTP_200_OK)
def reverse_geocode_coords(
    current_user: CurrentUser,
    lat: float = Query(...),
    lon: float = Query(...),
) -> dict[str, object]:
    """Reverse geocode coordinates to a place name."""
    return reverse_geocode(lat, lon)
