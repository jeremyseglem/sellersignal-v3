"""
Briefings API — returns the unified map+briefing payload for a ZIP.

Architecture:
  GET  /api/briefings/:zip         — full briefing (10-move playbook + map data)
  GET  /api/briefings/:zip/summary — compact summary (counts + top leads only)

The briefing combines:
  - Weekly playbook: 5 CALL NOW + 3 BUILD NOW + 2 STRATEGIC HOLDS
  - Full map data: every parcel with pressure score for heat-map rendering
  - Per-parcel investigation data where available
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from backend.api.db import get_supabase_client

router = APIRouter()


@router.get("/{zip_code}")
async def get_briefing(
    zip_code: str,
    include_map: bool = Query(True, description="Include full-ZIP map data"),
):
    """
    Full briefing for a ZIP. Returns:
      - week_of: ISO date string
      - playbook: { call_now: [...], build_now: [...], strategic_holds: [...] }
      - map_data: [{ pin, address, lat, lng, value, band, pressure, category }, ...]
      - stats: { total_parcels, call_now_count, investigated_count, last_run_cost }
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # TODO: Wire to the real selection logic once schema is populated.
    # For now, return a scaffold so the frontend team can start building
    # against a stable contract.
    return {
        "zip": zip_code,
        "status": "scaffold_only",
        "week_of": None,
        "playbook": {
            "call_now": [],
            "build_now": [],
            "strategic_holds": [],
        },
        "map_data": [] if include_map else None,
        "stats": {
            "total_parcels": 0,
            "call_now_count": 0,
            "build_now_count": 0,
            "investigated_count": 0,
            "last_run_cost_usd": 0.0,
        },
        "_next": "Wire to selection.weekly_selector once schema populated",
    }


@router.get("/{zip_code}/summary")
async def get_briefing_summary(zip_code: str):
    """Compact version — just counts and top 3 leads."""
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    return {
        "zip": zip_code,
        "status": "scaffold_only",
        "call_now_count": 0,
        "build_now_count": 0,
        "top_3": [],
    }
