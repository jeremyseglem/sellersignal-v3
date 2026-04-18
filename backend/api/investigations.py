"""
Investigation run API.

  POST /api/investigations/run     — trigger a new run (weekly cron + manual)
  GET  /api/investigations/budget  — current budget state
  POST /api/investigations/parcel/:pin/deep — deep-investigate one parcel on demand

All runs are gated by MAX_SEARCHES_PER_RUN and MAX_SEARCHES_PER_MONTH
budget caps (env vars). Dry-run approval happens before any spend.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.api.db import get_supabase_client

router = APIRouter()


class RunRequest(BaseModel):
    zip_code: str
    max_finalists: int = 15
    dry_run: bool = False


@router.post("/run")
async def run_investigation(req: RunRequest):
    """
    Trigger an investigation run for a ZIP.
    If dry_run=True, returns cost estimate without spending.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # TODO: Wire to backend.selection.run_investigation.main()
    return {
        "zip": req.zip_code,
        "status": "scaffold_only",
        "dry_run": req.dry_run,
        "estimated_searches": 0,
        "estimated_cost_usd": 0.0,
        "approved": False,
    }


@router.get("/budget")
async def get_budget_state():
    """
    Returns current SerpAPI budget state.
      - month_key
      - searches_this_month
      - last_run_searches
      - all_time_searches
      - monthly_cap_remaining
    """
    return {
        "status": "scaffold_only",
        "month_key": None,
        "searches_this_month": 0,
        "monthly_cap": 0,
        "remaining_this_month": 0,
    }


@router.post("/parcel/{pin}/deep")
async def deep_investigate_parcel(pin: str):
    """
    On-demand deep investigation for one parcel.
    Used when an agent clicks 'investigate this lead' on the map UI.
    Spends ~25 SerpAPI searches (~$0.38).
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")
    return {
        "pin": pin,
        "status": "scaffold_only",
        "searches_used": 0,
        "signals_found": [],
        "recommended_action": None,
    }
