"""
Coverage API — lists ZIPs that SellerSignal supports.

  GET /api/coverage         — public list of live ZIPs
  GET /api/coverage/:zip    — details for a specific ZIP (any status, admin-visible)

The frontend calls /api/coverage to populate the ZIP selector dropdown.
Only live ZIPs are returned by default — in-development ZIPs are hidden.
"""
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

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

    # Investigation counts — by action_category.
    # Paginate: Supabase REST client has a 1000-row default cap regardless
    # of .limit(); range-based pagination is the only way past it.
    # Also dedupe by pin because investigations_v3 has both 'screen' and
    # 'deep' rows per parcel — we only want one per pin for the counts
    # (prefer 'deep' since action_category there is authoritative).
    inv_by_pin: dict = {}
    offset = 0
    PAGE = 1000
    errors: list[str] = []
    while True:
        try:
            page = (supa.table('investigations_v3')
                    .select('pin, mode, action_category, updated_at')
                    .eq('zip_code', zip_code)
                    .range(offset, offset + PAGE - 1)
                    .execute())
        except Exception as e:
            errors.append(f"investigations page at {offset}: {e}")
            break
        rows = page.data or []
        for r in rows:
            pin = r.get('pin')
            if not pin:
                continue
            # Prefer 'deep' mode over 'screen' when both exist for same pin
            existing = inv_by_pin.get(pin)
            if existing is None or (r.get('mode') == 'deep' and existing.get('mode') != 'deep'):
                inv_by_pin[pin] = r
        if len(rows) < PAGE:
            break
        offset += PAGE
        if offset > 100000:
            break

    inv_rows = list(inv_by_pin.values())
    investigated_count = len(inv_rows)
    call_now_count  = sum(1 for r in inv_rows if r.get('action_category') == 'call_now')
    build_now_count = sum(1 for r in inv_rows if r.get('action_category') == 'build_now')

    last_refresh = None
    if inv_rows:
        stamps = [r.get('updated_at') for r in inv_rows if r.get('updated_at')]
        if stamps:
            last_refresh = max(stamps)

    resp = {
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
    if errors:
        # Surface pagination errors rather than silently returning zero
        # counts — callers can see something's wrong and act.
        resp['warnings'] = errors
    return resp


# ─── Admin: refresh stored Call Now counts ────────────────────────────────

def _require_admin(x_admin_key: Optional[str]):
    """Local guard for admin endpoints (mirrors backend.api.harvest._require_admin)."""
    server_key = os.environ.get("ADMIN_KEY")
    if not server_key:
        raise HTTPException(503, "ADMIN_KEY not configured server-side")
    if x_admin_key != server_key:
        raise HTTPException(401, "Missing or invalid X-Admin-Key header")


@router.post("/refresh-counts")
async def refresh_coverage_counts(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
    zip_code: Optional[str] = None,
):
    """
    Refresh the stored `current_call_now_count` on every live ZIP in
    zip_coverage_v3 by computing the count from the live briefing logic
    and writing it back to the database.

    Why: the territories list page reads `current_call_now_count` as a
    pre-computed snapshot for fast at-a-glance display. The stored value
    is only updated when a "deep investigation" runs (zip_investigation.py),
    which is a different code path that costs SerpAPI credits and isn't
    triggered by the matcher/briefing pipeline. So when matches change
    (e.g. after a rematch like the multi-ZIP fix), the territories page
    keeps showing stale numbers — accurate-when-clicked but wrong on the
    overview list.

    This endpoint reconciles them. It calls the briefing endpoint
    in-process (via httpx to the local FastAPI port), counts call_now
    leads, and writes the result back to zip_coverage_v3.

    Args:
      zip_code   — Optional. If set, refresh only that ZIP. Otherwise
                   refresh every live ZIP.

    Read-from-API + write-to-DB. Safe to call repeatedly. Idempotent.
    """
    _require_admin(x_admin_key)
    if not confirm:
        raise HTTPException(
            400,
            "This rewrites current_call_now_count on every live ZIP. "
            "Pass ?confirm=true to proceed.",
        )

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Find target ZIPs.
    q = (supa.table('zip_coverage_v3')
         .select('zip_code, current_call_now_count')
         .eq('status', 'live'))
    if zip_code:
        q = q.eq('zip_code', zip_code)
    target_rows = (q.execute().data) or []
    if not target_rows:
        return {
            'updated':    0,
            'targets':    0,
            'message':    'no live ZIPs match the filter',
            'zip_code':   zip_code,
        }

    # Hit the local briefing endpoint per ZIP.
    local_port = int(os.environ.get("PORT", "8000"))
    base_url   = f"http://127.0.0.1:{local_port}"
    admin_key  = os.environ.get("ADMIN_KEY", "")

    transitions: list = []
    errors: list      = []

    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
        for row in target_rows:
            z = row['zip_code']
            old_count = row.get('current_call_now_count') or 0
            try:
                resp = await client.get(
                    f"/api/briefings/{z}",
                    params={'force_rebuild': 'true'},
                    headers={'X-Admin-Key': admin_key},
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                errors.append({'zip_code': z, 'error': f"briefing fetch failed: {str(e)[:200]}"})
                continue

            try:
                playbook = payload.get('playbook', {}) or {}
                new_count = len(playbook.get('call_now', []) or [])
                # Pre-cap per-bucket totals (same source as the drive-by
                # writeback in briefings.py). Falls back to {} if a
                # cached briefing predates the bucket work.
                totals = payload.get('playbook', {}).get('contact_now_totals') or {}
            except Exception as e:
                errors.append({'zip_code': z, 'error': f"playbook parse failed: {str(e)[:200]}"})
                continue

            try:
                update_payload = {
                    'current_call_now_count': new_count,
                    'contact_now_probate':  int(totals.get('probate', 0)),
                    'contact_now_divorce':  int(totals.get('divorce', 0)),
                    'contact_now_trust':    int(totals.get('aging_trust', 0)),
                    'contact_now_llc':      int(totals.get('llc_long_hold', 0)),
                    'contact_now_absentee': int(totals.get('absentee', 0)),
                    'contact_now_tenure':   int(totals.get('long_tenure', 0)),
                }
                (supa.table('zip_coverage_v3')
                 .update(update_payload)
                 .eq('zip_code', z)
                 .execute())
            except Exception as e:
                errors.append({'zip_code': z, 'error': f"db update failed: {str(e)[:200]}"})
                continue

            transitions.append({
                'zip_code':  z,
                'old_count': old_count,
                'new_count': new_count,
                'delta':     new_count - old_count,
                'buckets':   {
                    'probate':  int(totals.get('probate', 0)),
                    'divorce':  int(totals.get('divorce', 0)),
                    'trust':    int(totals.get('aging_trust', 0)),
                    'llc':      int(totals.get('llc_long_hold', 0)),
                    'absentee': int(totals.get('absentee', 0)),
                    'tenure':   int(totals.get('long_tenure', 0)),
                },
            })

    return {
        'targets':      len(target_rows),
        'updated':      len(transitions),
        'transitions':  transitions,
        'errors':       errors,
    }
