"""
Coverage API — lists ZIPs that SellerSignal supports.

  GET /api/coverage         — public list of live ZIPs
  GET /api/coverage/:zip    — details for a specific ZIP (any status, admin-visible)

The frontend calls /api/coverage to populate the ZIP selector dropdown.
Only live ZIPs are returned by default — in-development ZIPs are hidden.
"""
from fastapi import APIRouter, HTTPException, Query
from backend.api.db import get_supabase_client

router = APIRouter()


@router.get("")
async def list_coverage(
    include_development: bool = Query(False,
        description="Include in-development ZIPs (admin only)"),
):
    """
    List covered ZIPs. By default only returns status='live' ZIPs.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        q = supa.table('zip_coverage_v3').select(
            'zip_code, market_key, city, state, status, '
            'parcel_count, investigated_count, current_call_now_count, went_live_at'
        )
        if include_development:
            q = q.in_('status', ['live', 'in_development'])
        else:
            q = q.eq('status', 'live')

        result = q.order('went_live_at', desc=True).execute()
        return {
            'coverage': result.data or [],
            'count': len(result.data or []),
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching coverage: {e}")


@router.get("/{zip_code}")
async def get_coverage_detail(zip_code: str):
    """
    Detailed coverage status for a specific ZIP.
    Returns build lifecycle progress — useful for admin dashboards.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        result = (supa.table('zip_coverage_v3')
                  .select('*')
                  .eq('zip_code', zip_code)
                  .maybe_single()
                  .execute())
        row = result.data if result else None
        if not row:
            raise HTTPException(404, f"ZIP {zip_code} is not in coverage")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching coverage: {e}")
