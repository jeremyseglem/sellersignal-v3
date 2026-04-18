"""
Map data API.

  GET /api/map/:zip                       — all parcels with lat/lng for heat map
  GET /api/map/:zip/bounds                — bounding box for initial map center
  GET /api/map/streetview/:pin            — Google Street View URL for a parcel

Heat map coloring uses the pressure score:
  pressure 3 = red (call_now)
  pressure 2 = amber (build_now)
  pressure 1 = light gold (hold with soft signal)
  pressure 0 = cool blue (nothing actionable)
"""
from fastapi import APIRouter, HTTPException, Query
from backend.api.db import get_supabase_client
import os

router = APIRouter()


@router.get("/{zip_code}")
async def get_map_data(
    zip_code: str,
    include_uninvestigated: bool = Query(True,
        description="Include parcels with no investigation data"),
):
    """
    All parcels in a ZIP with the data needed to render a heat map + pins.
    Each parcel returns:
      - pin, address, owner_name, value
      - lat, lng
      - band, signal_family
      - pressure (0-3) if investigated, else null
      - category (call_now / build_now / hold / avoid / uninvestigated)
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")
    return {
        "zip": zip_code,
        "status": "scaffold_only",
        "parcels": [],
        "bounds": None,
    }


@router.get("/{zip_code}/bounds")
async def get_zip_bounds(zip_code: str):
    """
    Lat/lng bounding box for the ZIP. Used by the frontend to center
    the map on first load.
    """
    return {
        "zip": zip_code,
        "status": "scaffold_only",
        "min_lat": None,
        "max_lat": None,
        "min_lng": None,
        "max_lng": None,
        "center": None,
    }


@router.get("/streetview/{pin}")
async def get_streetview_url(pin: str, size: str = "640x400"):
    """
    Returns a signed Google Street View Static URL for a parcel.
    Cached per parcel for 30 days since the photo doesn't change often.
    """
    api_key = os.environ.get('GOOGLE_STREET_VIEW_API_KEY') or os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        raise HTTPException(503, "Google Maps key not configured")
    return {
        "pin": pin,
        "status": "scaffold_only",
        "url": None,
    }
