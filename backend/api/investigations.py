"""
Investigations API — trigger runs, check budget, deep-investigate a single parcel.

  POST /api/investigations/run              — trigger a new run (dry-run or real)
  GET  /api/investigations/budget           — current SerpAPI budget state
  POST /api/investigations/parcel/:pin/deep — on-demand deep-investigate one parcel

All runs honor MAX_SEARCHES_PER_RUN and MAX_SEARCHES_PER_MONTH env caps.
Dry-run must be approved before the real run will spend any SerpAPI credits.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from backend.api.db import get_supabase_client
from backend.api.zip_gate import require_any_coverage
from backend.investigation import persistence

router = APIRouter()


class RunRequest(BaseModel):
    zip_code: str = Field(..., regex=r'^\d{5}$')
    max_finalists: int = Field(15, ge=1, le=30)
    dry_run: bool = True


@router.post("/run")
async def run_investigation(req: RunRequest):
    """
    Trigger an investigation run for a ZIP.

    ZIP must be in coverage (any status — 'in_development' is allowed
    because this is a build-lifecycle endpoint, not a public-consumer one).

    If dry_run=True (default), returns cost estimate without spending any
    SerpAPI credits. If dry_run=False, spends credits subject to budget caps.
    """
    # Validate ZIP exists in coverage
    from backend.api.zip_gate import get_zip_status
    status = get_zip_status(req.zip_code)
    if status is None:
        raise HTTPException(404, f"ZIP {req.zip_code} not in coverage")

    from backend.selection.zip_investigation import run_investigation_for_zip
    try:
        result = run_investigation_for_zip(
            req.zip_code,
            dry_run=req.dry_run,
            max_finalists=req.max_finalists,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Investigation run failed: {e}")


@router.get("/budget")
async def get_budget_state():
    """
    Returns current SerpAPI budget state for this month.

    Fields:
      - month_key:              '2026-04'
      - searches_this_month:    current usage count
      - cost_this_month_usd:    spend-to-date in dollars
      - monthly_cap:            MAX_SEARCHES_PER_MONTH ceiling
      - remaining_this_month:   how many more searches are available
    """
    return persistence.get_budget_state()


@router.post("/parcel/{pin}/deep")
async def deep_investigate_parcel(pin: str):
    """
    On-demand deep investigation for one parcel. Use when an agent clicks
    'investigate this lead' on a parcel that hasn't been investigated yet
    or has stale cache.

    Spends ~22 SerpAPI searches (~$0.33). Gated by the monthly budget cap.
    Validates that the parcel's ZIP is in coverage before spending anything.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Fetch parcel first — must exist and must be in a covered ZIP
    parcel_res = (supa.table('parcels_v3')
                  .select('*')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
    parcel = parcel_res.data if parcel_res else None
    if not parcel:
        raise HTTPException(404, f"Parcel {pin} not found")

    from backend.api.zip_gate import get_zip_status
    zip_code = parcel.get('zip_code')
    status = get_zip_status(zip_code or '')
    if status is None:
        raise HTTPException(404, f"Parcel's ZIP not in coverage")

    # Budget gate — a single deep run is ~22 searches
    budget_check = persistence.estimate_run_cost(25)  # small buffer above 22
    if not budget_check['approved']:
        raise HTTPException(429, {
            'error': 'budget_exceeded',
            'reasons': budget_check['reasons'],
        })

    from backend.investigation import investigate_parcel
    try:
        result = investigate_parcel(parcel, mode='deep', use_cache=True)
        # Persist the result
        persistence.cache_put(parcel, 'deep', result)
        if not result.get('from_cache'):
            persistence.record_searches(result.get('search_count', 0))
        return {
            'pin':                pin,
            'signals':            result.get('signals', []),
            'signal_count':       result.get('signal_count', 0),
            'recommended_action': result.get('recommended_action'),
            'from_cache':         result.get('from_cache', False),
            'searches_used':      result.get('search_count', 0),
        }
    except Exception as e:
        raise HTTPException(500, f"Deep investigation failed: {e}")
