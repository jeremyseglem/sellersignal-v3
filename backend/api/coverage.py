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


@router.get("/{zip_code}/stats")
async def get_zip_stats(zip_code: str):
    """
    Territory stats for the briefing header:
      - parcel_count
      - median_value (computed from parcels_v3.total_value)
      - investigated_count
      - call_now_count, build_now_count
      - last_refresh (most recent investigations_v3.updated_at)

    All aggregation — no scoring changes, no LLM calls, no external APIs.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Parcel count + city/state from coverage row (already maintained)
    try:
        cov = (supa.table('zip_coverage_v3')
               .select('parcel_count, city, state')
               .eq('zip_code', zip_code)
               .maybe_single()
               .execute())
    except Exception as e:
        raise HTTPException(500, f"Error fetching coverage row: {e}")
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} is not in coverage")
    parcel_count = cov.data.get('parcel_count') or 0
    city  = cov.data.get('city')
    state = cov.data.get('state')

    # Median assessed value — fetched in pages, computed in-memory.
    # Supabase has no percentile aggregate without an RPC; for ~7k parcels
    # this is cheap enough to do client-side.
    values: list[float] = []
    offset = 0
    PAGE = 1000
    while True:
        try:
            page = (supa.table('parcels_v3')
                    .select('total_value')
                    .eq('zip_code', zip_code)
                    .not_.is_('total_value', 'null')
                    .range(offset, offset + PAGE - 1)
                    .execute())
        except Exception:
            break
        rows = page.data or []
        for r in rows:
            v = r.get('total_value')
            if v is not None:
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    pass
        if len(rows) < PAGE:
            break
        offset += PAGE
        if offset > 50000:
            break

    median_value = None
    if values:
        values.sort()
        n = len(values)
        median_value = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0

    # Investigation counts — by action_category
    try:
        invs = (supa.table('investigations_v3')
                .select('pin, action_category, updated_at')
                .eq('zip_code', zip_code)
                .execute())
    except Exception:
        invs = None
    inv_rows = (invs.data if invs else []) or []
    investigated_count = len(inv_rows)
    call_now_count  = sum(1 for r in inv_rows if r.get('action_category') == 'call_now')
    build_now_count = sum(1 for r in inv_rows if r.get('action_category') == 'build_now')

    last_refresh = None
    if inv_rows:
        stamps = [r.get('updated_at') for r in inv_rows if r.get('updated_at')]
        if stamps:
            last_refresh = max(stamps)

    return {
        'zip_code':           zip_code,
        'city':               city,
        'state':              state,
        'parcel_count':       parcel_count,
        'median_value':       median_value,
        'investigated_count': investigated_count,
        'call_now_count':     call_now_count,
        'build_now_count':    build_now_count,
        'last_refresh':       last_refresh,
    }
