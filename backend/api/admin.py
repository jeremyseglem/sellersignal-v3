"""
Admin API — operator-only maintenance endpoints.

All endpoints guarded by an X-Admin-Key header that must match the
ADMIN_KEY env var. If ADMIN_KEY is not set server-side, these endpoints
return 503 (refuse-unsafe-default, don't open unauthenticated admin
access).

Endpoints:
  POST /api/admin/rescore/{zip_code}             — re-run recommend_action on cached investigations
  GET  /api/admin/rescore/{zip_code}/dry-run     — preview deltas without writing
  POST /api/admin/canonicalize/{zip_code}        — parse owner_name via Haiku 4.5 into owner_canonical_v3
  GET  /api/admin/canonicalize/{zip_code}/status — report canonicalize coverage
  POST /api/admin/geometry/{zip_code}            — fill missing lat/lng from county ArcGIS
  GET  /api/admin/geometry/{zip_code}/status     — report geometry coverage
  POST /api/admin/legal-filings/upload           — (placeholder, not yet wired)
"""
import os
from fastapi import APIRouter, HTTPException, Header, Depends, Path
from typing import Optional

from backend.api.db import get_supabase_client

router = APIRouter()


# ─── Auth ────────────────────────────────────────────────────────────────

def require_admin(x_admin_key: Optional[str] = Header(None)) -> None:
    """
    Gate admin endpoints on a matching X-Admin-Key header.

    If the ADMIN_KEY env var isn't set server-side, we refuse access
    entirely — we don't want 'no password means open' as a failure mode.
    """
    server_key = os.environ.get('ADMIN_KEY')
    if not server_key:
        raise HTTPException(
            503,
            "ADMIN_KEY not configured on server — admin endpoints disabled.",
        )
    if not x_admin_key:
        raise HTTPException(401, "Missing X-Admin-Key header.")
    if x_admin_key != server_key:
        raise HTTPException(403, "Invalid admin key.")


# ─── Rescore ─────────────────────────────────────────────────────────────

@router.post("/rescore/{zip_code}", dependencies=[Depends(require_admin)])
async def rescore_zip_endpoint(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    dry_run: bool = False,
):
    """
    Re-run recommend_action against all cached investigations for a ZIP
    using the current pressure-engine logic.

    Zero SerpAPI cost — reads existing investigations_v3.signals (JSONB),
    reconstructs parcel context from parcels_v3, calls recommend_action,
    writes back action_category/action_pressure/action_reason/action_tone/
    action_next_step.

    Use this after pressure-engine logic changes to apply the new scoring
    to existing data without re-investigating.

    Body: none
    Query: ?dry_run=true to preview deltas without writing

    Returns:
      {
        "rescored":    int,    total investigations processed
        "changed":     int,    rows where action fields changed
        "promotions":  int,    hold -> actionable transitions
        "demotions":   int,    actionable -> hold transitions
        "dry_run":     bool,
        "before": { "call_now|pressure=3": N, "hold|pressure=0": N, ... },
        "after":  { ... }
      }
    """
    try:
        from backend.ingest.rescore import rescore_zip
    except Exception as e:
        raise HTTPException(500, f"rescore module failed to import: {e}")

    # Verify ZIP exists in coverage before rescoring
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    cov = (supa.table('zip_coverage_v3')
           .select('zip_code, parcel_count, investigated_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} not in coverage.")
    if (cov.data.get('investigated_count') or 0) == 0:
        raise HTTPException(
            409,
            f"ZIP {zip_code} has no investigations to rescore.",
        )

    try:
        result = rescore_zip(zip_code, dry_run=dry_run)
    except Exception as e:
        raise HTTPException(500, f"Rescore failed: {e}")

    result['dry_run'] = dry_run
    result['zip_code'] = zip_code
    return result


@router.get("/ping", dependencies=[Depends(require_admin)])
async def admin_ping():
    """Cheap auth check. Returns {'ok': true} if the caller's key is valid."""
    return {"ok": True}


# ─── Canonicalize owner names ────────────────────────────────────────────

@router.post("/canonicalize/{zip_code}", dependencies=[Depends(require_admin)])
async def canonicalize_zip_endpoint(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    dry_run: bool = False,
    limit: Optional[int] = None,
    force: bool = False,
    sleep_ms: int = 50,
):
    """
    Parse owner_name for every parcel in this ZIP via Claude Haiku 4.5,
    writing structured output to owner_canonical_v3.

    Idempotent: skips PINs that already have a canonical row (unless
    ?force=true). Safe to re-run after adding new parcels.

    Cost: ~$0.0005/parcel. A 6,000-parcel ZIP ≈ $3. Smoke-test with
    ?limit=10 before a full run (expect ~$0.005).

    Query params:
      ?dry_run=true   — count + show first 5 parcels, no API calls
      ?limit=N        — process only first N parcels (smoke test)
      ?force=true     — re-parse parcels that already have a row
      ?sleep_ms=N     — polite pause between calls (default 50ms)

    Returns:
      {
        "zip_code":     str,
        "dry_run":      bool,
        "eligible":     int,     # parcels with owner_name
        "already_done": int,     # skipped (had canonical row)
        "processed":    int,     # API calls made this run
        "low_conf":     int,     # confidence < 0.5
        "errors":       list,
        "low_conf_rows": list,
        "tokens_in":    int,
        "tokens_out":   int,
        "cost_usd":     float,
        "wall_time_s":  float,
        "est_cost_usd": float,   # only on dry_run
      }

    Note: Haiku 4.5 rate limit is ~50 req/min on Tier 1 keys. A
    6,000-parcel ZIP serial-runs in ~2 hours. Railway HTTP timeout
    may interrupt — prefer smaller --limit batches for full backfills.
    """
    try:
        from backend.ingest.backfill_owner_canonical import backfill_zip
    except Exception as e:
        raise HTTPException(500, f"backfill module failed to import: {e}")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    cov = (supa.table('zip_coverage_v3')
           .select('zip_code, parcel_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} not in coverage.")
    if (cov.data.get('parcel_count') or 0) == 0:
        raise HTTPException(
            409,
            f"ZIP {zip_code} has no parcels — run 'ingest' first.",
        )

    # Guard: refuse large runs without explicit limit to avoid HTTP timeout
    if not dry_run and not limit and (cov.data.get('parcel_count') or 0) > 500:
        raise HTTPException(
            413,
            f"ZIP {zip_code} has {cov.data['parcel_count']} parcels. "
            "Full-ZIP canonicalize exceeds HTTP timeout — either set "
            "?limit=500 and call repeatedly, or run from Railway shell: "
            f"python -m backend.ingest.zip_builder canonicalize {zip_code}",
        )

    try:
        result = backfill_zip(
            zip_code=zip_code,
            dry_run=dry_run,
            limit=limit,
            force=force,
            sleep_ms=sleep_ms,
            verbose=False,   # silence stdout; stats dict is the response
        )
    except Exception as e:
        raise HTTPException(500, f"Canonicalize failed: {e}")

    return result


@router.get("/canonicalize/{zip_code}/status",
            dependencies=[Depends(require_admin)])
async def canonicalize_status_endpoint(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
):
    """
    Report canonicalize coverage for a ZIP without any API calls.

    Returns:
      {
        "zip_code":         str,
        "parcel_count":     int,     # from zip_coverage_v3
        "canonicalized":    int,     # count of owner_canonical_v3 rows whose pin is in this ZIP
        "coverage_pct":     float,
        "low_confidence":   int,     # confidence < 0.5
        "by_entity_type":   {...}    # counts of individual/trust/llc/company/unknown
      }
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    # Parcel count from coverage
    cov = (supa.table('zip_coverage_v3')
           .select('parcel_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} not in coverage.")
    parcel_count = cov.data.get('parcel_count') or 0

    # Pull pins in this ZIP
    pins = []
    offset = 0
    while True:
        page_res = (supa.table('parcels_v3')
                    .select('pin')
                    .eq('zip_code', zip_code)
                    .range(offset, offset + 999)
                    .execute())
        batch = page_res.data or []
        pins.extend(p['pin'] for p in batch)
        if len(batch) < 1000:
            break
        offset += 1000
        if offset > 200000:
            break

    if not pins:
        return {
            'zip_code': zip_code, 'parcel_count': parcel_count,
            'canonicalized': 0, 'coverage_pct': 0.0,
            'low_confidence': 0, 'by_entity_type': {},
        }

    # Query canonical rows — batches of 500 to stay under URL length limits
    entity_counts: dict[str, int] = {}
    canonicalized = 0
    low_conf = 0
    BATCH = 500
    for i in range(0, len(pins), BATCH):
        batch = pins[i:i + BATCH]
        res = (supa.table('owner_canonical_v3')
               .select('pin, entity_type, confidence')
               .in_('pin', batch)
               .execute())
        for row in (res.data or []):
            canonicalized += 1
            et = row.get('entity_type') or 'unknown'
            entity_counts[et] = entity_counts.get(et, 0) + 1
            if (row.get('confidence') or 0) < 0.5:
                low_conf += 1

    coverage_pct = round(100.0 * canonicalized / max(parcel_count, 1), 2)
    return {
        'zip_code': zip_code,
        'parcel_count': parcel_count,
        'canonicalized': canonicalized,
        'coverage_pct': coverage_pct,
        'low_confidence': low_conf,
        'by_entity_type': entity_counts,
    }


# ─── Geometry backfill ────────────────────────────────────────────────

@router.post("/geometry/{zip_code}", dependencies=[Depends(require_admin)])
async def geometry_backfill_endpoint(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    dry_run: bool = False,
    limit: Optional[int] = None,
    market_key: str = 'WA_KING',
):
    """
    Fill lat/lng on parcels_v3 rows that are missing geometry.

    Queries the county ArcGIS by PIN and updates parcels_v3.lat/lng
    only. Does NOT touch owner_name, value, or any other column — safe
    to run against canonicalized/classified/banded parcels.

    Needed for 98004 because an earlier ingest produced 6,658 parcels
    with null coordinates, making the map unusable.

    Query params:
      ?dry_run=true   — count PINs needing geometry, don't call ArcGIS
      ?limit=N        — process only first N PINs (smoke test)
      ?market_key=WA_KING — county config (only WA_KING supported today)

    Returns:
      {
        "zip_code":     str,
        "market_key":   str,
        "dry_run":      bool,
        "missing_geom": int,     # parcels with null lat/lng before
        "fetched":      int,     # ArcGIS returned geometry for this many
        "updated":      int,     # rows updated in Supabase
        "not_found":    int,     # PINs ArcGIS has no record for
        "errors":       list
      }
    """
    try:
        from backend.ingest.geometry_backfill import backfill_geometry_zip_async
    except Exception as e:
        raise HTTPException(500, f"geometry_backfill module failed to import: {e}")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    cov = (supa.table('zip_coverage_v3')
           .select('parcel_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} not in coverage.")

    # Guard: full-ZIP ArcGIS + Supabase updates can easily exceed 60-120s HTTP timeout.
    # Require explicit --limit for any run with more than 500 missing coords.
    if not dry_run and not limit:
        # Quickly estimate how many need backfill
        quick_check = (supa.table('parcels_v3')
                       .select('pin', count='exact')
                       .eq('zip_code', zip_code)
                       .or_('lat.is.null,lng.is.null')
                       .limit(1)
                       .execute())
        approx_missing = quick_check.count if quick_check.count is not None else 0
        if approx_missing > 500:
            raise HTTPException(
                413,
                f"ZIP {zip_code} has ~{approx_missing} parcels missing geometry. "
                "Full-ZIP backfill exceeds HTTP timeout — pass ?limit=500 and "
                "call repeatedly until remaining = 0.",
            )

    try:
        result = await backfill_geometry_zip_async(
            zip_code=zip_code,
            market_key=market_key,
            dry_run=dry_run,
            limit=limit,
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Geometry backfill failed: {e}")

    return result


@router.get("/geometry/{zip_code}/status",
            dependencies=[Depends(require_admin)])
async def geometry_status_endpoint(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
):
    """
    Report geometry coverage for a ZIP. Zero cost, no ArcGIS calls.

    Returns:
      {
        "zip_code":      str,
        "parcel_count":  int,
        "with_geom":     int,
        "missing_geom":  int,
        "coverage_pct":  float
      }
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    cov = (supa.table('zip_coverage_v3')
           .select('parcel_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        raise HTTPException(404, f"ZIP {zip_code} not in coverage.")
    parcel_count = cov.data.get('parcel_count') or 0

    missing_res = (supa.table('parcels_v3')
                   .select('pin', count='exact')
                   .eq('zip_code', zip_code)
                   .or_('lat.is.null,lng.is.null')
                   .limit(1)
                   .execute())
    missing = missing_res.count or 0
    with_geom = parcel_count - missing
    coverage_pct = round(100.0 * with_geom / max(parcel_count, 1), 2)
    return {
        'zip_code': zip_code,
        'parcel_count': parcel_count,
        'with_geom': with_geom,
        'missing_geom': missing,
        'coverage_pct': coverage_pct,
    }


# ─── Re-ingest property details from ArcGIS ──────────────────────────────

@router.post("/reingest-property-details/{zip_code}",
             dependencies=[Depends(require_admin)])
async def reingest_property_details(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    market_key: str = 'WA_KING',
    dry_run: bool = False,
):
    """
    Backfill land_value, building_value, total_value, prop_type, acres,
    is_absentee, is_out_of_state, owner_city, owner_state from the
    correctly-pointed ArcGIS endpoint.

    Why this endpoint exists: parcels_v3 was historically ingested from
    a broken ArcGIS URL (Property/KingCo_Parcels layer 0 — 7-field
    geometry layer that returned 400 errors for the fields we asked
    for). Owner names, tenure, and total_value got loaded via some other
    path (likely a CSV), but property-detail columns stayed NULL. Fix 2
    of Option 2 re-points arcgis.py to the correct endpoint
    (OpenDataPortal/property__parcel_address_area layer 1722); this
    endpoint runs the re-ingest on demand.

    Upsert behavior (see _parse_feature comments): owner_name and
    owner_name_raw are NOT touched — we only set property-detail
    columns. Existing owner data is preserved.

    Rate safety: the ArcGIS service caps at 2000 features/page and we
    sleep 0.3s between pages. 98004 has ~6,658 parcels so full ingest
    is 4 pages / ~1.2s + response time — well under Railway's 5-min
    proxy cutoff. For larger ZIPs this may need background execution.

    Response:
        {
          "zip_code": "98004",
          "fetched": 6658,
          "upserted": 6658,
          "failed": 0,
          "dry_run": false,
          "sample": {...}    // first parcel's parsed payload, for audit
        }
    """
    import asyncio
    from backend.ingest.arcgis import (
        fetch_parcels_for_zip, upsert_parcels, MARKET_CONFIGS,
    )

    if market_key not in MARKET_CONFIGS:
        raise HTTPException(400, f"Unknown market_key {market_key}")

    try:
        parcels = await fetch_parcels_for_zip(zip_code, market_key)
    except Exception as e:
        raise HTTPException(502, f"ArcGIS fetch failed: {e}")

    if not parcels:
        return {
            'zip_code': zip_code,
            'fetched':  0,
            'upserted': 0,
            'failed':   0,
            'dry_run':  dry_run,
            'note':     'No parcels returned from ArcGIS for this ZIP.',
        }

    sample = dict(parcels[0])

    if dry_run:
        return {
            'zip_code': zip_code,
            'fetched':  len(parcels),
            'upserted': 0,
            'failed':   0,
            'dry_run':  True,
            'sample':   sample,
            'note':     'Dry run — no DB writes. Review sample, then repeat without dry_run=true.',
        }

    stats = upsert_parcels(parcels)
    return {
        'zip_code': zip_code,
        'fetched':  len(parcels),
        'upserted': stats.get('inserted_or_updated', 0),
        'failed':   stats.get('failed', 0),
        'batches':  stats.get('batches', 0),
        'dry_run':  False,
        'sample':   sample,
    }


# ─── Reclassify owner_type from owner_name_raw ──────────────────────────

@router.post("/reclassify-owner-type/{zip_code}",
             dependencies=[Depends(require_admin)])
async def reclassify_owner_type(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    dry_run: bool = False,
):
    """
    Re-run _derive_owner_type on existing parcels_v3.owner_name_raw and
    update owner_type in place. Used to apply Fix 1 (LLP classification
    bug) to parcels already in the database — the re-ingest endpoint
    intentionally doesn't touch owner_type so existing owner_name data
    is preserved, but that also means the LLP fix can't take effect
    retroactively without this reclassify pass.

    Reads owner_name_raw (or owner_name if raw is missing), recomputes
    owner_type, and updates the row only when the new classification
    differs from the stored value. Returns counts of changes made.
    """
    from backend.ingest.arcgis import _derive_owner_type

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")

    # Page through parcels in the ZIP
    all_rows: list[dict] = []
    offset = 0
    while True:
        page = (supa.table('parcels_v3')
                .select('pin, owner_name, owner_name_raw, owner_type')
                .eq('zip_code', zip_code)
                .range(offset, offset + 999)
                .execute())
        rows = page.data or []
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
        if offset > 100_000:
            break  # safety

    # Never-downgrade guardrail. Some rows have owner_type set to a
    # high-specificity category (llc / trust / estate / gov) via a
    # previous hand-curation or a different loader that this function
    # doesn't know about. The current classifier may not reproduce
    # those classifications (e.g. 'BUCHAN BROS INVESTMENT PROPERTIES'
    # has no LLC suffix but was marked llc at some point; churches
    # were bucketed as 'gov' historically). We only apply changes that
    # are strict upgrades:
    #   - None -> anything                          (initial fill)
    #   - 'individual' -> anything stronger         (upgrade)
    #   - 'unknown' -> anything stronger            (upgrade)
    # and block:
    #   - any high-specificity -> 'individual'      (downgrade)
    #   - any high-specificity -> 'unknown'         (downgrade)
    #   - 'gov' -> anything except upgrades to 'nonprofit' (not yet implemented)
    # Trust<->estate cross is allowed because the TRUST vs SURVIVORS-TRUST
    # ordering fix correctly re-reads the data.
    HIGHER_SPECIFICITY = {'llc', 'trust', 'estate', 'gov', 'nonprofit'}
    changes: list[dict] = []
    skipped_downgrades = 0
    for r in all_rows:
        name = r.get('owner_name_raw') or r.get('owner_name') or ''
        new_type = _derive_owner_type(name)
        old_type = r.get('owner_type')
        if new_type == old_type:
            continue

        # Guardrail: skip downgrades
        if (old_type in HIGHER_SPECIFICITY
                and new_type in ('individual', 'unknown')):
            skipped_downgrades += 1
            continue

        changes.append({
            'pin':      r['pin'],
            'name':     name,
            'old_type': old_type,
            'new_type': new_type,
        })

    # Summarize the transitions (e.g. {'individual->llc': 150,
    # 'gov->llc': 5, 'trust->individual': 0, ...}) so operators can
    # sanity-check the overall shape of the change before applying.
    from collections import Counter
    transitions: Counter = Counter()
    for ch in changes:
        old = str(ch['old_type']) if ch['old_type'] is not None else 'None'
        transitions[f"{old} -> {ch['new_type']}"] += 1

    if dry_run:
        return {
            'zip_code':           zip_code,
            'examined':           len(all_rows),
            'would_change':       len(changes),
            'skipped_downgrades': skipped_downgrades,
            'transitions':        dict(transitions.most_common()),
            'sample':             changes[:30],
            'dry_run':            True,
        }

    # Apply in batches of 200 — many small updates, one per row
    applied = 0
    errors = 0
    for ch in changes:
        try:
            supa.table('parcels_v3').update(
                {'owner_type': ch['new_type']}
            ).eq('pin', ch['pin']).execute()
            applied += 1
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"[reclassify] {ch['pin']}: {e}")

    return {
        'zip_code':           zip_code,
        'examined':           len(all_rows),
        'changed':            applied,
        'skipped_downgrades': skipped_downgrades,
        'errors':             errors,
        'transitions':        dict(transitions.most_common()),
        'sample':             changes[:10],
        'dry_run':            False,
    }
