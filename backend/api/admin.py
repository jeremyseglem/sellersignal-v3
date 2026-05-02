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
from fastapi import APIRouter, HTTPException, Header, Depends, Path, BackgroundTasks
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


# ─── eReal Property backfill (Fix 3 of Option 2) ─────────────────────────

@router.post("/ereal-backfill/{zip_code}",
             dependencies=[Depends(require_admin)])
async def ereal_backfill(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    limit: int = 100,
    ttl_days: int = 30,
    force: bool = False,
):
    """
    Run one batch of KC eReal Property detail-page fetches against the
    parcels in a ZIP. Each parcel gets:
      - owner_name_raw refreshed (from assessor's authoritative page)
      - sqft, year_built filled in parcels_v3
      - sales history upserted to sales_history_v3
      - meta row written to parcel_ereal_meta_v3

    A batch is limited to `limit` parcels (default 100) so each HTTP
    call completes under Railway's 5-minute proxy timeout. At the
    default 1.2s rate limit per parcel, 100 parcels is ~2 minutes.

    Operator runs this repeatedly until everything in the ZIP is
    populated (or until candidates_found is 0). The harvester picks up
    where it left off via parcel_ereal_meta_v3.fetched_at.

    Parameters:
      limit      — max parcels this call (1..500; default 100)
      ttl_days   — skip parcels fetched within this many days (default 30)
      force      — ignore TTL and re-fetch everything in ZIP

    Does NOT re-fetch parcels that failed recently unless `force=True`
    (failures are captured in parcel_ereal_meta_v3.last_error).

    Response includes aggregate stats, fetch/parse counts, sales
    upserted, and a sample of any errors encountered.
    """
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")

    # Lazy import to keep the admin router light when not used
    from backend.harvesters.ereal_property import run_batch

    try:
        result = run_batch(
            supa=supa,
            zip_code=zip_code,
            limit=limit,
            ttl_days=ttl_days,
            force=force,
        )
    except Exception as e:
        raise HTTPException(500, f"ereal batch failed: {e}")

    return result


@router.get("/ereal-backfill/{zip_code}/status",
            dependencies=[Depends(require_admin)])
async def ereal_backfill_status(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
):
    """
    Report eReal Property fetch coverage for a ZIP. Returns counts of
    parcels with/without a successful fetch, the oldest fetched_at
    (so operators know if a refresh is overdue), and error counts.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")

    # Total parcels in ZIP
    total_res = (
        supa.table('parcels_v3')
        .select('pin', count='exact')
        .eq('zip_code', zip_code)
        .limit(1)
        .execute()
    )
    total = total_res.count or 0

    # Parcels with eReal meta (any attempt)
    meta_res = (
        supa.table('parcel_ereal_meta_v3')
        .select('pin, fetched_at, last_error, consecutive_errors')
        .in_('pin',
             [r['pin'] for r in
              (supa.table('parcels_v3').select('pin')
               .eq('zip_code', zip_code).limit(50000).execute().data or [])])
        .execute()
    )
    meta_rows = meta_res.data or []
    fetched_ok = sum(1 for r in meta_rows if r.get('fetched_at'))
    with_errors = sum(1 for r in meta_rows if r.get('last_error'))
    never_touched = total - len(meta_rows)

    # Oldest successful fetch
    oldest = None
    for r in meta_rows:
        f = r.get('fetched_at')
        if f and (oldest is None or f < oldest):
            oldest = f

    return {
        'zip_code':          zip_code,
        'total_parcels':     total,
        'meta_rows':         len(meta_rows),
        'fetched_ok':        fetched_ok,
        'with_errors':       with_errors,
        'never_touched':     never_touched,
        'oldest_fetched_at': oldest,
        'coverage_pct':      round(100.0 * fetched_ok / max(total, 1), 1),
    }


@router.get("/ereal-backfill/{zip_code}/recent",
            dependencies=[Depends(require_admin)])
async def ereal_backfill_recent(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    limit: int = 20,
):
    """
    List recently-fetched eReal meta rows for a ZIP. Diagnostic aid
    for verifying what the backfill actually touched.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")

    pin_res = (supa.table('parcels_v3').select('pin')
               .eq('zip_code', zip_code).limit(50000).execute())
    pins = [r['pin'] for r in (pin_res.data or [])]

    meta = (supa.table('parcel_ereal_meta_v3')
            .select('pin, fetched_at, last_attempt_at, last_error, '
                    'http_status, body_length, sales_count, parser_version')
            .in_('pin', pins)
            .order('last_attempt_at', desc=True)
            .limit(limit)
            .execute())

    # Also pull each pin's current parcels_v3 state for sqft/year_built/owner_name_raw
    rows = meta.data or []
    if rows:
        pr = (supa.table('parcels_v3')
              .select('pin, sqft, year_built, owner_name_raw')
              .in_('pin', [r['pin'] for r in rows])
              .execute())
        pmap = {p['pin']: p for p in (pr.data or [])}
        for r in rows:
            r['parcel_state'] = pmap.get(r['pin']) or {}

    return {'zip_code': zip_code, 'rows': rows}


@router.get("/ereal-sales/{pin}",
            dependencies=[Depends(require_admin)])
async def ereal_sales(pin: str = Path(..., pattern=r'^[0-9A-Z]+$')):
    """Read sales_history_v3 for a specific pin for quick inspection."""
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")
    res = (supa.table('sales_history_v3')
           .select('*')
           .eq('pin', pin)
           .order('sale_date', desc=True)
           .execute())
    return {'pin': pin, 'sales': res.data or []}


# ─── Reband (re-run band assignment after reclassify) ────────────────────────

@router.post("/reband/{zip_code}", dependencies=[Depends(require_admin)])
async def reband_zip(zip_code: str = Path(..., pattern=r'^\d{5}$')):
    """
    Re-run band assignment for a ZIP. Use after reclassify-owner-type to
    let the new owner classifications propagate into Band 0-4 priority
    (which drives CALL NOW / BUILD NOW selection).

    Idempotent. Returns the band distribution.
    """
    from backend.ingest.zip_builder import cmd_band
    import io
    import contextlib

    # cmd_band prints to stdout — capture for the response
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_band(zip_code)

    output = buf.getvalue()
    if rc != 0:
        raise HTTPException(500, f"Reband failed: {output}")
    return {"ok": True, "zip_code": zip_code, "log": output}


# ─── Reclassify archetypes (re-run signal_family assignment) ─────────────────

@router.post("/reclassify-archetypes/{zip_code}",
             dependencies=[Depends(require_admin)])
async def reclassify_archetypes_zip(zip_code: str = Path(..., pattern=r'^\d{5}$')):
    """
    Re-run archetype classification for every parcel in the ZIP.

    This sets parcels_v3.signal_family to one of the archetype labels
    (trust_mature, individual_long_tenure, llc_investor_mature, etc.)
    based on owner_type + tenure + value + activity patterns.

    Distinct from /reclassify-owner-type (which only parses owner_name
    into individual/llc/trust). Run AFTER reclassify-owner-type so the
    archetype classifier has correct owner_type to read from.

    Pairs with /reband — banding reads signal_family, so reband must
    run after this for Band 0-4 to update.

    Idempotent. Returns the archetype distribution.
    """
    from backend.ingest.zip_builder import cmd_classify
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_classify(zip_code)

    output = buf.getvalue()
    if rc != 0:
        raise HTTPException(500, f"Reclassify-archetypes failed: {output}")
    return {"ok": True, "zip_code": zip_code, "log": output}


# ─── Backfill tenure from sales history ──────────────────────────────────────

@router.post("/backfill-tenure/{zip_code}",
             dependencies=[Depends(require_admin)])
async def backfill_tenure(zip_code: str = Path(..., pattern=r'^\d{5}$')):
    """
    Compute parcels_v3.last_transfer_date and tenure_years from
    sales_history_v3 for every parcel in the ZIP.

    KC ArcGIS doesn't include transfer date. The eReal harvester
    populates sales_history_v3, but never propagates the most recent
    sale date back to parcels_v3. Without that, tenure_years stays
    null on every parcel — which means the archetype classifier maps
    everyone to early/young/active variants (Band 1) instead of
    long_tenure/mature/aging variants (Band 2+). Result: empty BUILD
    NOW deck.

    This endpoint:
      1. For each parcel in the ZIP, finds the most recent sale in
         sales_history_v3 (preferring is_arms_length=true if any
         exist, else most-recent-of-any).
      2. Writes last_transfer_date and tenure_years to parcels_v3.

    After running this, run /reclassify-archetypes and /reband to
    let the new tenure data drive Band 2+ assignments.

    Idempotent. Returns counts.
    """
    from datetime import date, datetime
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured")

    # Pull all parcel PINs in the ZIP. PostgREST on this project
    # caps responses at 1,000 rows (PGRST_DB_MAX_ROWS). Paginate
    # explicitly with .range() to get past the cap.
    PAGE_SIZE = 1000
    all_pins = []
    page = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin')
               .eq('zip_code', zip_code)
               .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
               .execute())
        rows = res.data or []
        if not rows:
            break
        all_pins.extend(r['pin'] for r in rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
        if page > 100:    # 100K parcels per ZIP safety cap
            break

    today = date.today()
    updated = 0
    no_sales = 0
    errors = 0
    error_samples = []  # capture first few errors for debugging

    # Per-parcel: pull sales, pick best, update parcel. One round-trip
    # per parcel; ~1k parcels in Medina = ~10-20 seconds total.
    for pin in all_pins:
        try:
            sales_res = (supa.table('sales_history_v3')
                         .select('sale_date, is_arms_length, sale_price')
                         .eq('pin', pin)
                         .order('sale_date', desc=True)
                         .execute())
            sales = sales_res.data or []
            if not sales:
                no_sales += 1
                continue

            # Prefer most recent arms-length sale; fall back to
            # most recent of any kind.
            best = next((s for s in sales if s.get('is_arms_length')), sales[0])
            sale_date_str = best.get('sale_date')
            if not sale_date_str:
                no_sales += 1
                continue

            try:
                sale_date = datetime.fromisoformat(str(sale_date_str)[:10]).date()
            except (ValueError, TypeError):
                no_sales += 1
                continue

            tenure = round((today - sale_date).days / 365.25, 1)

            # Only update real parcels_v3 columns. last_arms_length_*
            # are computed via the parcel_last_arms_length_v3 view —
            # they live on sales_history_v3 and shouldn't be written
            # to the parcel directly.
            (supa.table('parcels_v3')
             .update({
                 'last_transfer_date': sale_date.isoformat(),
                 'tenure_years': tenure,
             })
             .eq('pin', pin)
             .execute())
            updated += 1
        except Exception as e:
            errors += 1
            if len(error_samples) < 3:
                error_samples.append(f"{pin}: {type(e).__name__}: {str(e)[:120]}")

    return {
        "ok": True,
        "zip_code": zip_code,
        "total_parcels": len(all_pins),
        "updated_with_tenure": updated,
        "no_sales_history": no_sales,
        "errors": errors,
        "error_samples": error_samples,
    }


# ─── Seed parcels from pre-computed JSON ─────────────────────────────────────

# ZIP → city mapping for the 11 KC ZIPs (10 new + 98004). seed_from_json
# defaults to "Bellevue" but Medina/Kirkland/Redmond/Mercer Island/Seattle
# parcels need their actual city for accurate display.
KC_ZIP_TO_CITY = {
    "98004": "Bellevue",
    "98005": "Bellevue",
    "98006": "Bellevue",
    "98007": "Bellevue",
    "98033": "Kirkland",
    "98039": "Medina",
    "98040": "Mercer Island",
    "98052": "Redmond",
    "98105": "Seattle",
    "98112": "Seattle",
    "98199": "Seattle",
}


@router.post("/seed-from-json/{zip_code}",
             dependencies=[Depends(require_admin)])
async def seed_from_json_zip(zip_code: str = Path(..., pattern=r'^\d{5}$')):
    """
    Seed parcels_v3 for a ZIP from a pre-computed owner JSON file in
    data/seeds/. Each JSON is keyed by PIN and contains owner_name,
    last_transfer_date, tenure_years, sale_price, address, value,
    owner_type — derived from the King County EXTR_RPSale.csv bulk
    export joined against the ArcGIS PIN list.

    File path is determined by zip_code:
      - 98004           -> data/seeds/wa-king-98004.json (the original baseline)
      - 98005..98199    -> data/seeds/wa-king-{zip}-owners.json (10 new ZIPs)

    Same upsert path as the original 98004 seed used. Idempotent —
    re-running just refreshes the rows. Returns row counts and the
    file used.

    After this endpoint completes for a ZIP, run:
      1. /reclassify-archetypes/{zip} — uses owner_type + tenure to
         assign signal_family
      2. /reband/{zip}                — uses signal_family to assign
         band 0-4

    These two run fast (seconds each) because all the data they need
    is now in parcels_v3. After both, the ZIP's briefing renders
    with real archetypes, real tenure, real Band 2+ promotion — the
    same way 98004 has been working.
    """
    from pathlib import Path as PathLib
    from backend.ingest.seed_from_json import (
        load_parcels_from_json, upsert_parcels, stamp_ingest_complete,
    )

    # Resolve seed path. Repo root is two parents up from this file
    # (backend/api/admin.py -> backend/ -> repo root).
    repo_root = PathLib(__file__).resolve().parent.parent.parent

    # 98004 uses the original baseline filename; new ZIPs use the
    # generated filename pattern.
    if zip_code == "98004":
        seed_path = repo_root / "data" / "seeds" / "wa-king-98004.json"
    else:
        seed_path = repo_root / "data" / "seeds" / f"wa-king-{zip_code}-owners.json"

    if not seed_path.exists():
        raise HTTPException(404,
            f"Seed file not found: {seed_path.name}. Available seeds live "
            f"in data/seeds/. Add the JSON to that directory and redeploy.")

    city = KC_ZIP_TO_CITY.get(zip_code, "Bellevue")

    try:
        rows = load_parcels_from_json(
            json_path=str(seed_path),
            zip_code=zip_code,
            market_key="WA_KING",
            default_state="WA",
            default_city=city,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to load seed: {type(e).__name__}: {e}")

    if not rows:
        return {
            "ok": True,
            "zip_code": zip_code,
            "seed_file": seed_path.name,
            "message": "Seed file contained no rows; nothing to upsert.",
            "stats": {"inserted_or_updated": 0, "failed": 0, "batches": 0},
        }

    try:
        stats = upsert_parcels(rows)
    except Exception as e:
        raise HTTPException(500, f"Upsert failed: {type(e).__name__}: {e}")

    # Stamp coverage with the seed's parcel count so the briefing
    # endpoint sees a consistent count.
    try:
        stamp_ingest_complete(zip_code, len(rows))
    except Exception as e:
        # Non-fatal — the data is in, the stamp is for accounting.
        stats["stamp_warning"] = f"{type(e).__name__}: {e}"

    return {
        "ok": True,
        "zip_code": zip_code,
        "city": city,
        "seed_file": seed_path.name,
        "rows_processed": len(rows),
        "stats": stats,
        "next_steps": [
            f"POST /api/admin/reclassify-archetypes/{zip_code}",
            f"POST /api/admin/reband/{zip_code}",
        ],
    }


# ─── Canonicalize-all: long-running multi-ZIP orchestrator ───────────────────
# Wraps backfill_zip in a background task that loops through every ZIP needing
# canonicalization, in 500-parcel batches, persisting progress to a module-
# level state dict that the status endpoint reads.
#
# Why not a single curl per ZIP? The Haiku rate limit caps us at ~50 req/min,
# so 64K parcels = 21 hours of wall time. Doing this with a synchronous HTTP
# call would hit Railway's edge-proxy 5-minute timeout instantly. The /backfill
# endpoint exists exactly for this case.

import asyncio
import threading
from datetime import datetime, timezone

_canon_lock = threading.Lock()
_canon_job: Optional[dict] = None

DEFAULT_CANON_ROSTER = [
    "98005", "98006", "98007", "98033", "98040",
    "98052", "98105", "98112", "98199", "98039",  # 98039 last as a no-op (already done)
]
CANON_BATCH_LIMIT = 500


def _canon_snapshot() -> Optional[dict]:
    with _canon_lock:
        if _canon_job is None:
            return None
        return dict(_canon_job, zips=dict(_canon_job["zips"]),
                    errors=list(_canon_job["errors"]))


def _canon_update(updates: dict) -> None:
    with _canon_lock:
        if _canon_job is not None:
            _canon_job.update(updates)


def _canon_set_zip(zip_code: str, key: str, value) -> None:
    with _canon_lock:
        if _canon_job is None:
            return
        _canon_job["zips"].setdefault(zip_code, {})[key] = value


def _canon_inc(zip_code: str, key: str, delta: int = 1) -> None:
    with _canon_lock:
        if _canon_job is None:
            return
        z = _canon_job["zips"].setdefault(zip_code, {})
        z[key] = (z.get(key) or 0) + delta


def _run_canonicalize_all(roster: list[str]) -> None:
    """Background task: for each ZIP, loop backfill_zip in 500-parcel
    batches until done. Idempotent — backfill_zip skips already-canonicalized
    parcels. Survives transient errors (logs and continues)."""
    try:
        from backend.ingest.backfill_owner_canonical import backfill_zip
    except Exception as e:
        _canon_update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        with _canon_lock:
            if _canon_job is not None:
                _canon_job["errors"].append({
                    "scope": "outer",
                    "error": f"import failed: {type(e).__name__}: {e}",
                })
        return

    for zip_code in roster:
        with _canon_lock:
            if _canon_job is None:
                return
            _canon_job["current_zip"] = zip_code

        # Loop until backfill_zip reports zero processed in a call,
        # which means everything's already canonicalized for this ZIP.
        # Cap at 50 batches per ZIP (= 25,000 parcels — more than any
        # single ZIP we have).
        zip_total_processed = 0
        zip_total_cost = 0.0
        for batch_n in range(50):
            try:
                stats = backfill_zip(
                    zip_code=zip_code,
                    dry_run=False,
                    limit=CANON_BATCH_LIMIT,
                    force=False,
                    sleep_ms=0,
                    verbose=False,
                    concurrency=10,    # ~10x speedup over serial
                )
            except Exception as e:
                _canon_inc(zip_code, "batch_errors")
                with _canon_lock:
                    if _canon_job is not None:
                        _canon_job["errors"].append({
                            "scope": zip_code,
                            "batch": batch_n,
                            "error": f"{type(e).__name__}: {str(e)[:200]}",
                        })
                # Don't break — try next batch, transient errors happen.
                continue

            processed = stats.get("processed") or 0
            zip_total_processed += processed
            zip_total_cost += stats.get("cost_usd") or 0.0

            _canon_set_zip(zip_code, "batches_run", batch_n + 1)
            _canon_set_zip(zip_code, "processed", zip_total_processed)
            _canon_set_zip(zip_code, "cost_usd", round(zip_total_cost, 4))
            _canon_set_zip(zip_code, "low_conf",
                           (stats.get("low_conf") or 0)
                           + (_canon_job["zips"].get(zip_code, {}).get("low_conf") or 0)
                           if _canon_job is not None else 0)

            if processed == 0:
                # Already-done state: backfill_zip skipped everything.
                # ZIP is fully canonicalized. Move on.
                _canon_set_zip(zip_code, "status", "complete")
                break
        else:
            # 50 batches without a zero-result; bail with a flag.
            _canon_set_zip(zip_code, "status", "max_batches_hit")

    _canon_update({
        "status":       "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "current_zip":  None,
    })


@router.post("/canonicalize-all", dependencies=[Depends(require_admin)])
async def canonicalize_all(background_tasks: BackgroundTasks):
    """
    Long-running multi-ZIP canonicalize. Loops the roster in 500-parcel
    batches and persists progress so a slow run doesn't hit the Railway
    edge-proxy timeout. Call once, poll /canonicalize-all/status to
    track. Idempotent — re-running picks up where the prior run left off.
    """
    global _canon_job

    with _canon_lock:
        if _canon_job is not None and _canon_job.get("status") == "running":
            raise HTTPException(409,
                "A canonicalize-all job is already running. Poll "
                "/api/admin/canonicalize-all/status for progress.")
        _canon_job = {
            "started_at":   datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "status":       "running",
            "roster":       list(DEFAULT_CANON_ROSTER),
            "current_zip":  None,
            "zips":         {z: {"batches_run": 0, "processed": 0,
                                  "cost_usd": 0.0, "low_conf": 0}
                              for z in DEFAULT_CANON_ROSTER},
            "errors":       [],
        }

    background_tasks.add_task(_run_canonicalize_all, list(DEFAULT_CANON_ROSTER))

    return {
        "ok":               True,
        "message":          f"Canonicalize-all started for {len(DEFAULT_CANON_ROSTER)} ZIPs.",
        "estimated_cost":   "~$32 USD (Haiku 4.5 tokens, ~$0.0005/parcel × ~64K parcels)",
        "estimated_hours":  "20-25 (rate-limited at ~50 req/min)",
        "poll_url":         "/api/admin/canonicalize-all/status",
        "job":              _canon_snapshot(),
    }


@router.get("/canonicalize-all/status", dependencies=[Depends(require_admin)])
async def canonicalize_all_status():
    """In-memory job state. Falls back to a per-ZIP coverage summary
    from canonicalize/{zip}/status if no in-memory job exists."""
    snap = _canon_snapshot()
    if snap is not None:
        return snap

    # No in-memory job — derive from canonicalize/{zip}/status data.
    # Same pattern as hydrate_owners_status: survive container restarts
    # by reading ground truth from owner_canonical_v3.
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    out = {}
    for z in DEFAULT_CANON_ROSTER:
        try:
            cov = (supa.table('zip_coverage_v3')
                   .select('parcel_count')
                   .eq('zip_code', z)
                   .maybe_single()
                   .execute())
            total = (cov.data or {}).get('parcel_count') or 0
            cnt = (supa.table('owner_canonical_v3')
                   .select('pin', count='exact')
                   .eq('zip_code', z)
                   .limit(1)
                   .execute())
            canonicalized = cnt.count or 0
            out[z] = {
                "total":        total,
                "canonicalized": canonicalized,
                "pct":          round(100.0 * canonicalized / total, 1) if total else 0,
            }
        except Exception as e:
            out[z] = {"error": f"{type(e).__name__}: {e}"}

    return {
        "source":  "db",
        "as_of":   datetime.now(timezone.utc).isoformat(),
        "roster":  DEFAULT_CANON_ROSTER,
        "zips":    out,
    }


# ─── Safe rematch: reset matched_at, re-run matcher all-ZIPs ─────────────────

@router.post("/rematch-safe", dependencies=[Depends(require_admin)])
async def rematch_safe(confirm: bool = False):
    """
    SAFE rematch: resets raw_signals_v3.matched_at to NULL for already-
    processed signals, then runs the matcher with zip_filter=None so it
    writes matches for ALL 11 covered ZIPs.

    DOES NOT DELETE existing match rows. Existing matches (especially
    98004's 309-match baseline) remain intact during the rerun. The
    matcher uses .upsert() semantics so re-creating an identical match
    is a no-op.

    Use case: new ZIPs were canonicalized after the matcher last ran,
    and we want existing raw_signals to be re-evaluated against the
    expanded canonicalized-owner pool.

    Pass ?confirm=true to execute.
    """
    if not confirm:
        raise HTTPException(
            400,
            "This resets matched_at on every processed signal and triggers "
            "a full rematch. Existing match rows are preserved (no DELETE). "
            "Pass ?confirm=true to proceed.",
        )

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # 1. Reset matched_at to NULL on every signal that has been processed.
    #    This is the only mutation. Existing raw_signal_matches_v3 rows
    #    are NOT touched.
    page = 1000
    reset_count = 0
    while True:
        rows = (supa.table('raw_signals_v3')
                .select('id')
                .not_.is_('matched_at', 'null')
                .range(0, page - 1)
                .execute()).data or []
        if not rows:
            break
        ids = [r['id'] for r in rows]
        (supa.table('raw_signals_v3')
         .update({'matched_at': None})
         .in_('id', ids)
         .execute())
        reset_count += len(ids)
        if len(rows) < page:
            break

    # 2. Run the matcher with zip_filter=None so it scopes matches
    #    across ALL covered ZIPs, not just one.
    from backend.harvesters import matcher
    stats = matcher.process_unmatched(
        supa,
        zip_filter=None,
        batch_size=100,
        max_batches=500,
    )

    return {
        "ok":            True,
        "signals_reset": reset_count,
        "match_stats":   stats,
        "note":          "98004's existing matches were preserved (no DELETE). "
                         "Identical matches re-created during the rerun are upserts.",
    }


# ─── Reset bogus low-confidence canonical rows ───────────────────────────────

@router.post("/reset-canonical/{zip_code}",
             dependencies=[Depends(require_admin)])
async def reset_canonical_zip(
    zip_code: str = Path(..., pattern=r'^\d{5}$'),
    only_zero_confidence: bool = True,
):
    """
    Delete owner_canonical_v3 rows for a ZIP that were written as "unknown"
    fallbacks when the Anthropic API was unavailable. After deletion, the
    rows naturally re-queue on the next canonicalize-all run because the
    backfiller's "already done" check looks for row existence.

    Use case: API credits ran out mid-canonicalize, the canonicalizer's
    fallback path wrote `entity_type='unknown', confidence=0.0` rows for
    every parcel it tried to process. Those rows are useless (no parsed
    owner data) and should be retried. This endpoint deletes them safely.

    Defaults are conservative — `only_zero_confidence=true` deletes only
    the rows that match the API-failure fallback signature (entity_type
    'unknown' AND confidence 0.0). Pass `only_zero_confidence=false` to
    delete ALL low-confidence rows for the ZIP (less common; more
    aggressive).

    Returns count of rows deleted.
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # Find target rows. We need to scope to this ZIP — but
    # owner_canonical_v3 has no zip_code column. Join via parcels_v3.

    # Step 1: pull all PINs in this ZIP (paginated; PostgREST caps at 1000).
    all_pins = []
    page_size = 1000
    page = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin')
               .eq('zip_code', zip_code)
               .range(page * page_size, (page + 1) * page_size - 1)
               .execute())
        rows = res.data or []
        if not rows:
            break
        all_pins.extend(r['pin'] for r in rows)
        if len(rows) < page_size:
            break
        page += 1
        if page > 50:
            break

    if not all_pins:
        return {"ok": True, "zip_code": zip_code, "deleted": 0,
                "note": "No parcels found in this ZIP."}

    # Step 2: find canonical rows matching the bogus signature.
    # Chunk the IN list to keep response sizes under PostgREST cap.
    target_pins = []
    chunk = 500
    for i in range(0, len(all_pins), chunk):
        pins_chunk = all_pins[i:i + chunk]
        q = (supa.table('owner_canonical_v3')
             .select('pin, entity_type, confidence')
             .in_('pin', pins_chunk))
        if only_zero_confidence:
            q = q.eq('entity_type', 'unknown').eq('confidence', 0.0)
        else:
            q = q.lt('confidence', 0.5)
        res = q.execute()
        for r in (res.data or []):
            target_pins.append(r['pin'])

    if not target_pins:
        return {"ok": True, "zip_code": zip_code, "deleted": 0,
                "note": "No bogus low-confidence rows found."}

    # Step 3: delete them. Chunk the DELETE too.
    deleted = 0
    for i in range(0, len(target_pins), chunk):
        pins_chunk = target_pins[i:i + chunk]
        (supa.table('owner_canonical_v3')
         .delete()
         .in_('pin', pins_chunk)
         .execute())
        deleted += len(pins_chunk)

    return {
        "ok": True,
        "zip_code": zip_code,
        "parcels_in_zip": len(all_pins),
        "matched_for_deletion": len(target_pins),
        "deleted": deleted,
        "filter": ("entity_type=unknown AND confidence=0"
                   if only_zero_confidence else "confidence<0.5"),
        "note": "These PINs will be re-queued on the next canonicalize-all run.",
    }


# ─── Clean fabricated previously_listed signals (one-shot data fix) ─────

@router.post("/clean-listing-signals", dependencies=[Depends(require_admin)])
async def clean_listing_signals_endpoint(
    confirm: bool = False,
    zip_code: Optional[str] = None,
    limit: Optional[int] = None,
):
    """
    One-shot cleanup for fabricated `previously_listed` signals that
    came from listing-site SerpAPI results before commit aefd60b
    landed the own-URL gate + tightened regex.

    Why this exists. The pre-fix regex tagged `previously_listed` from
    snippet text any time it matched 'off market' / 'removed' / etc.
    SerpAPI returns Zillow / Redfin / Realtor pages whose 'nearby homes'
    sidebars carry our address with 'Off Market' chrome adjacent — and
    even on a parcel's own page Zillow says 'this property is off market'
    as generic explainer text, not as a listing-history claim. The
    regex couldn't tell the difference.

    Result: investigations_v3 contains fabricated `previously_listed`
    signals on parcels that have never been on MLS, and deep_signals_v3
    contains LLM 'What to Say' copy that faithfully paraphrases the
    fake signal into 'previously listed but is now off market'.

    What this endpoint does (in confirm=true mode):
      1. Find every investigations_v3 row with a previously_listed signal
         where source_type = 'listing_site' (Zillow / Redfin / Realtor /
         Trulia). Only listing-site signals are removed; any from other
         sources (e.g. Property History label with source_type=
         generic_web) are left alone — those weren't observed misfiring
         and removing them might delete real signals.
      2. For each affected investigation: filter the signals array,
         recompute signal_count + has_* flags + trust_summary, write
         back. action_category / action_pressure are NOT recomputed —
         that's a separate operation via /api/admin/rescore/{zip}.
      3. Delete the corresponding deep_signals_v3 row (cache will
         regenerate fresh from cleaned investigation on next view).

    Idempotent: a second run finds zero affected rows.
    Cost: zero (no SerpAPI, no Anthropic).

    Query params:
      ?confirm=true     — required for any writes; default is dry-run
      ?zip_code=98004   — limit to one ZIP (optional)
      ?limit=N          — process only first N affected rows (smoke test)

    Returns:
      {
        "dry_run":              bool,
        "zip_code":             str | null,
        "limit":                int | null,
        "investigations_scanned": int,
        "investigations_affected": int,    # contained at least one bad signal
        "signals_removed":        int,    # total bad signals stripped
        "investigations_written": int,    # 0 if dry_run
        "deep_signals_invalidated": int,  # 0 if dry_run
        "per_zip": { "98004": {"affected": N, "signals_removed": N}, ... },
        "sample_before_after": [          # first 3 affected rows (dry_run only)
           {"pin": ..., "before": [...], "after": [...]}
        ]
      }
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    # ── Pull candidate investigations ─────────────────────────────────────
    # Supabase REST doesn't support JSONB-array element filters cleanly,
    # so we fetch the rows we plausibly need (filtered by zip if given)
    # and do the signal-level filter in Python. This is the same approach
    # used by /admin/rescore.
    page_size = 1000
    rows_all = []
    offset = 0
    while True:
        q = (supa.table('investigations_v3')
                .select('pin, zip_code, signals, signal_count, '
                        'has_life_event, has_financial, has_blocker, '
                        'identity_resolved, trust_summary, mode')
                .range(offset, offset + page_size - 1))
        if zip_code:
            q = q.eq('zip_code', zip_code)
        page = q.execute()
        if not page.data: break
        rows_all.extend(page.data)
        if len(page.data) < page_size: break
        offset += page_size

    # ── Identify rows containing offending signals ────────────────────────
    def is_bad_signal(s: dict) -> bool:
        return (s.get('type') == 'previously_listed'
                and s.get('source_type') == 'listing_site')

    affected = []   # list of {pin, zip, before_sigs, after_sigs}
    signals_removed_total = 0
    per_zip: dict = {}

    for row in rows_all:
        sigs = row.get('signals') or []
        bad_count = sum(1 for s in sigs if is_bad_signal(s))
        if bad_count == 0: continue
        clean_sigs = [s for s in sigs if not is_bad_signal(s)]
        affected.append({
            'pin': row['pin'],
            'zip_code': row['zip_code'],
            'before_sigs': sigs,
            'after_sigs': clean_sigs,
            'mode': row.get('mode'),
        })
        signals_removed_total += bad_count
        z = row['zip_code']
        per_zip.setdefault(z, {'affected': 0, 'signals_removed': 0})
        per_zip[z]['affected'] += 1
        per_zip[z]['signals_removed'] += bad_count

    if limit is not None:
        affected = affected[:limit]

    # ── Dry-run: report and exit ──────────────────────────────────────────
    if not confirm:
        sample = []
        for a in affected[:3]:
            sample.append({
                'pin': a['pin'],
                'zip_code': a['zip_code'],
                'before_signal_count': len(a['before_sigs']),
                'after_signal_count': len(a['after_sigs']),
                'removed_sources': [
                    s.get('source_label')
                    for s in a['before_sigs']
                    if is_bad_signal(s)
                ],
            })
        return {
            'dry_run': True,
            'zip_code': zip_code,
            'limit': limit,
            'investigations_scanned': len(rows_all),
            'investigations_affected': len(affected),
            'signals_removed': sum(
                sum(1 for s in a['before_sigs'] if is_bad_signal(s))
                for a in affected
            ),
            'investigations_written': 0,
            'deep_signals_invalidated': 0,
            'per_zip': per_zip,
            'sample_before_after': sample,
            'note': 'Dry run only. Pass ?confirm=true to execute.',
        }

    # ── Confirmed: write cleaned investigations + invalidate cache ────────
    investigations_written = 0
    deep_signals_invalidated = 0

    for a in affected:
        clean_sigs = a['after_sigs']

        # Recompute roll-ups using the same logic as investigate_parcel().
        trust_summary = {'high': 0, 'medium': 0, 'low': 0}
        for s in clean_sigs:
            t = s.get('trust', 'medium')
            trust_summary[t] = trust_summary.get(t, 0) + 1

        update_row = {
            'signals': clean_sigs,
            'signal_count': len(clean_sigs),
            'has_life_event': any(s.get('category') == 'life_event' for s in clean_sigs),
            'has_financial':  any(s.get('category') == 'financial'  for s in clean_sigs),
            'has_blocker':    any(s.get('category') == 'blocker'    for s in clean_sigs),
            'identity_resolved': any(s.get('type') in ('linkedin_found', 'age_found', 'entity_info') for s in clean_sigs),
            'trust_summary':  trust_summary,
        }

        try:
            (supa.table('investigations_v3')
                 .update(update_row)
                 .eq('pin', a['pin'])
                 .execute())
            investigations_written += 1
        except Exception:
            # Skip on individual failure rather than abort the batch —
            # we'd rather make partial progress than orphan everyone.
            continue

        # Invalidate deep_signals cache. Best-effort; if no row exists,
        # delete is a no-op.
        try:
            res = (supa.table('deep_signals_v3')
                       .delete()
                       .eq('pin', a['pin'])
                       .execute())
            if res.data:
                deep_signals_invalidated += len(res.data)
        except Exception:
            pass

    return {
        'dry_run': False,
        'zip_code': zip_code,
        'limit': limit,
        'investigations_scanned': len(rows_all),
        'investigations_affected': len(affected),
        'signals_removed': signals_removed_total if limit is None else sum(
            sum(1 for s in a['before_sigs'] if is_bad_signal(s))
            for a in affected
        ),
        'investigations_written': investigations_written,
        'deep_signals_invalidated': deep_signals_invalidated,
        'per_zip': per_zip,
        'note': ('Action category / pressure NOT recomputed — '
                 'run /api/admin/rescore/{zip} after this if you want '
                 'leads re-evaluated against the cleaned signal set.'),
    }


# ─── Shadow-mode match review (calibration layer) ─────────────────────

@router.post("/audit-match-review", dependencies=[Depends(require_admin)])
async def audit_match_review_endpoint(
    confirm: bool = False,
    zip_code: Optional[str] = None,
    limit: Optional[int] = None,
):
    """
    Run the shadow-strict matcher (backend.scoring.match_review.classify_match)
    over rows in raw_signal_matches_v3 and populate the review columns:
      - match_review_status   ('likely_valid' / 'needs_review' / 'likely_false_positive')
      - match_review_reason   (short tag like 'particle_only', 'middle_disagree', etc.)
      - match_confidence_score (0.0 – 1.0)

    DOES NOT change which matches the briefings selector returns. The
    selector ignores these columns. This endpoint exists purely to
    populate a flagged-match dataset for human review before any
    stricter rule is promoted to the live gate.

    Implementation: raw_signal_matches_v3 stores only pin + raw_signal_id.
    Owner-name comes from parcels_v3 (joined by pin). Filing party comes
    from raw_signals_v3.party_names (joined by raw_signal_id) — the
    "matched party" is the first entry in that array, matching the
    convention used by GET /api/harvest/matches/:zip.

    Idempotent: re-running with the same data writes the same verdicts.
    Cheap: zero external API calls.

    Query params:
      ?confirm=true     — required for any writes; default is dry-run
      ?zip_code=98004   — limit to one ZIP (optional)
      ?limit=N          — process only first N rows (smoke test)

    Returns counts of each verdict + a sample of the most-flagged rows.
    """
    from backend.scoring.match_review import classify_match

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    # Step 1: build pin -> (zip_code, owner_name) map. If zip_code is
    # provided, only fetch parcels in that ZIP (much smaller); otherwise
    # we need all parcels because matches reference any pin.
    parcels_by_pin: dict = {}
    page = 1000
    off = 0
    while True:
        q = supa.table('parcels_v3').select('pin, zip_code, owner_name').range(off, off + page - 1)
        if zip_code:
            q = q.eq('zip_code', zip_code)
        res = q.execute()
        batch = res.data or []
        for r in batch:
            parcels_by_pin[r['pin']] = r
        if len(batch) < page: break
        off += page
        if off > 200000: break  # safety bound

    if not parcels_by_pin:
        return {'dry_run': not confirm, 'rows_scanned': 0,
                'note': 'No parcels found' + (f' in ZIP {zip_code}' if zip_code else '')}

    # Step 2: pull strict matches for those pins (in chunks).
    pins = list(parcels_by_pin.keys())
    matches_all: list[dict] = []
    CHUNK = 200
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i:i+CHUNK]
        res = (supa.table('raw_signal_matches_v3')
                  .select('id, raw_signal_id, pin, match_strength')
                  .in_('pin', chunk)
                  .eq('match_strength', 'strict')
                  .limit(5000)
                  .execute())
        matches_all.extend(res.data or [])

    if limit is not None:
        matches_all = matches_all[:limit]

    if not matches_all:
        return {'dry_run': not confirm, 'rows_scanned': 0,
                'note': 'No strict matches found'}

    # Step 3: pull the raw_signals for these matches.
    signal_ids = list({m['raw_signal_id'] for m in matches_all})
    signals_by_id: dict = {}
    CHUNK_S = 300
    for i in range(0, len(signal_ids), CHUNK_S):
        chunk = signal_ids[i:i+CHUNK_S]
        res = (supa.table('raw_signals_v3')
                  .select('id, signal_type, party_names')
                  .in_('id', chunk)
                  .execute())
        for r in (res.data or []):
            signals_by_id[r['id']] = r

    # Step 4: classify each match.
    verdicts = []
    status_counts: dict = {}
    reason_counts: dict = {}
    skipped_no_signal = 0
    skipped_no_parcel = 0

    for m in matches_all:
        signal = signals_by_id.get(m['raw_signal_id'])
        parcel = parcels_by_pin.get(m['pin'])
        if not signal:
            skipped_no_signal += 1
            continue
        if not parcel:
            skipped_no_parcel += 1
            continue
        owner_name = parcel.get('owner_name') or ''
        # matched_party = first entry in party_names (same convention as
        # /api/harvest/matches/:zip)
        parties = signal.get('party_names') or []
        if not parties:
            continue
        first = parties[0]
        if isinstance(first, dict):
            matched_party = first.get('raw') or first.get('name') or ''
        else:
            matched_party = str(first)

        status, reason, conf = classify_match(matched_party, owner_name)
        verdicts.append({
            'id': m['id'],
            'pin': m['pin'],
            'zip_code': parcel.get('zip_code'),
            'signal_type': signal.get('signal_type'),
            'owner_name': owner_name,
            'matched_party': matched_party,
            'status': status,
            'reason': reason,
            'confidence': conf,
        })
        status_counts[status] = status_counts.get(status, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # Dry-run report
    if not confirm:
        samples_by_status: dict = {}
        for v in verdicts:
            samples_by_status.setdefault(v['status'], [])
            if len(samples_by_status[v['status']]) < 3:
                samples_by_status[v['status']].append({
                    'pin': v['pin'],
                    'zip_code': v['zip_code'],
                    'signal_type': v['signal_type'],
                    'owner_name': v['owner_name'],
                    'matched_party': v['matched_party'],
                    'reason': v['reason'],
                    'confidence': v['confidence'],
                })
        return {
            'dry_run': True,
            'rows_scanned': len(matches_all),
            'rows_classified': len(verdicts),
            'skipped_no_signal': skipped_no_signal,
            'skipped_no_parcel': skipped_no_parcel,
            'verdict_counts': status_counts,
            'reason_counts': reason_counts,
            'samples_by_status': samples_by_status,
            'note': ('Dry run only. Pass ?confirm=true to write verdicts. '
                     'No leads will be removed — the selector does not '
                     'read these columns.'),
        }

    # Write verdicts.
    written = 0
    failed = 0
    for v in verdicts:
        try:
            (supa.table('raw_signal_matches_v3')
                 .update({
                     'match_review_status': v['status'],
                     'match_review_reason': v['reason'],
                     'match_confidence_score': v['confidence'],
                 })
                 .eq('id', v['id'])
                 .execute())
            written += 1
        except Exception:
            failed += 1
            continue

    return {
        'dry_run': False,
        'rows_scanned': len(matches_all),
        'rows_classified': len(verdicts),
        'rows_written': written,
        'rows_failed': failed,
        'verdict_counts': status_counts,
        'reason_counts': reason_counts,
    }


@router.get("/match-review-queue", dependencies=[Depends(require_admin)])
async def match_review_queue_endpoint(
    status: Optional[str] = None,
    zip_code: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Read endpoint for the human review workflow.

    Returns flagged matches sorted by confidence ascending (lowest
    confidence first = most likely misfire). Each row is enriched with
    owner_name + matched_party + signal_type from the joined parcels
    and signals tables.

    Query params:
      ?status=likely_false_positive | needs_review | likely_valid
      ?zip_code=98004
      ?limit=N (default 100, max 1000)
      ?offset=N
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    limit = min(limit, 1000)

    # Step 1: pull match rows with verdicts (sorted by confidence asc).
    q = (supa.table('raw_signal_matches_v3')
             .select('id, pin, raw_signal_id, '
                     'match_review_status, match_review_reason, '
                     'match_confidence_score')
             .not_.is_('match_review_status', 'null')
             .order('match_confidence_score', desc=False)
             .order('id', desc=False))
    if status:
        q = q.eq('match_review_status', status)

    # Pull more than `limit` so we can ZIP-filter post-fetch (ZIP lives on
    # parcels_v3, not on the match row itself). Cap the prefetch at 5000
    # to bound memory.
    PREFETCH_CAP = max(limit + offset, 1000) * 3
    PREFETCH_CAP = min(PREFETCH_CAP, 5000)
    q = q.limit(PREFETCH_CAP)
    res = q.execute()
    raw_rows = res.data or []

    # Step 2: enrich with parcel + signal data.
    pins = list({r['pin'] for r in raw_rows})
    signal_ids = list({r['raw_signal_id'] for r in raw_rows})

    parcels_by_pin: dict = {}
    if pins:
        for i in range(0, len(pins), 200):
            chunk = pins[i:i+200]
            res = (supa.table('parcels_v3')
                       .select('pin, zip_code, owner_name, address')
                       .in_('pin', chunk)
                       .execute())
            for r in (res.data or []):
                parcels_by_pin[r['pin']] = r

    signals_by_id: dict = {}
    if signal_ids:
        for i in range(0, len(signal_ids), 300):
            chunk = signal_ids[i:i+300]
            res = (supa.table('raw_signals_v3')
                       .select('id, signal_type, party_names')
                       .in_('id', chunk)
                       .execute())
            for r in (res.data or []):
                signals_by_id[r['id']] = r

    # Step 3: build enriched rows, ZIP-filtering as we go.
    enriched = []
    for r in raw_rows:
        parcel = parcels_by_pin.get(r['pin']) or {}
        if zip_code and parcel.get('zip_code') != zip_code:
            continue
        signal = signals_by_id.get(r['raw_signal_id']) or {}
        parties = signal.get('party_names') or []
        first = parties[0] if parties else None
        if isinstance(first, dict):
            matched_party = first.get('raw') or first.get('name') or ''
        elif first is not None:
            matched_party = str(first)
        else:
            matched_party = ''
        enriched.append({
            'id': r['id'],
            'pin': r['pin'],
            'zip_code': parcel.get('zip_code'),
            'address': parcel.get('address'),
            'owner_name': parcel.get('owner_name'),
            'matched_party': matched_party,
            'signal_type': signal.get('signal_type'),
            'match_review_status': r['match_review_status'],
            'match_review_reason': r['match_review_reason'],
            'match_confidence_score': r['match_confidence_score'],
        })

    # Step 4: paginate the post-filtered set.
    total_found = len(enriched)
    page = enriched[offset:offset+limit]

    return {
        'rows': page,
        'limit': limit,
        'offset': offset,
        'total_in_filter': total_found,
        'prefetched': len(raw_rows),
        'filtered_by_status': status,
        'filtered_by_zip': zip_code,
    }


@router.post("/promote-match-review-deletion", dependencies=[Depends(require_admin)])
async def promote_match_review_deletion_endpoint(
    confirm: bool = False,
    reason: Optional[str] = None,
):
    """
    DELETE rows from raw_signal_matches_v3 whose shadow-mode verdict
    matches the given reason (and is `likely_false_positive`).

    This is the "promotion" step that turns a shadow-mode finding into a
    real cleanup. Use this AFTER reviewing the queue endpoint output and
    confirming the reason cohort is safe to remove.

    Required:
      ?reason=<tag>           e.g. 'insufficient_overlap',
                                   'first_name_diff',
                                   'middle_initial_disagree'

    Optional:
      ?confirm=true           required for any writes; default is dry-run

    Behavior:
      - Only deletes rows where match_review_status='likely_false_positive'
        AND match_review_reason=<reason>.
      - Does NOT delete other false-positive reasons; one promotion =
        one named cohort. This keeps each cleanup step traceable.
      - Does NOT touch raw_signals_v3 or parcels_v3 — the underlying
        court filing is preserved, only the (probably-bad) parcel
        attribution is removed.
      - Is destructive. The deleted rows are gone; re-creating them
        requires re-running the matcher against the original signals.

    Returns row counts before/after.
    """
    if not reason:
        raise HTTPException(400, "reason query param is required (e.g. ?reason=insufficient_overlap)")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase not configured.")

    # Count what we'd delete
    count_q = (supa.table('raw_signal_matches_v3')
                  .select('id', count='exact')
                  .eq('match_review_status', 'likely_false_positive')
                  .eq('match_review_reason', reason)
                  .limit(1)
                  .execute())
    n_to_delete = count_q.count or 0

    if not confirm:
        # Pull a sample for the dry-run report
        sample = (supa.table('raw_signal_matches_v3')
                     .select('id, pin, raw_signal_id, match_confidence_score')
                     .eq('match_review_status', 'likely_false_positive')
                     .eq('match_review_reason', reason)
                     .limit(5)
                     .execute())
        return {
            'dry_run': True,
            'reason': reason,
            'rows_matching': n_to_delete,
            'sample_ids': [r['id'] for r in (sample.data or [])],
            'note': f'Pass ?confirm=true to delete these {n_to_delete} rows.',
        }

    # Execute deletion
    res = (supa.table('raw_signal_matches_v3')
              .delete()
              .eq('match_review_status', 'likely_false_positive')
              .eq('match_review_reason', reason)
              .execute())
    deleted = len(res.data or [])

    return {
        'dry_run': False,
        'reason': reason,
        'rows_matched_before': n_to_delete,
        'rows_deleted': deleted,
        'note': ('Run /api/admin/rescore/{zip} for any affected ZIP if '
                 'you want lead categories re-evaluated against the '
                 'reduced match set.'),
    }


# ─── Agent voice generation — smoke test endpoint ─────────────────────
# This is the prompt that will become POST /api/agent/generate-scripts
# once the schema lands. For now it's a passthrough: takes voice/stance/
# bio in the request body, constructs the prompt, calls Anthropic,
# returns raw output. No auth-coupling, no DB write, no validation —
# just lets us iterate the prompt against real model output before
# committing to the surrounding infrastructure.
#
# Once we're satisfied with output quality:
#   1. Migrate this prompt construction into a helper module
#   2. Build POST /api/agent/generate-scripts that reads from the
#      authenticated user's agent_profiles_v3 row
#   3. Delete this endpoint

_AGENT_VOICE_SYSTEM_PROMPT = """You are helping a real estate agent write seller outreach in their own voice.

Your job is not to create a polished marketing template.
Your job is to preserve the agent's actual tone, restraint, confidence, and way of speaking.

CRITICAL: Do not fall back to generic real-estate copywriting. The default LLM register for "thoughtful agent letter" is exactly what we are NOT trying to produce. If the output reads like it could have been written by any competent agent, you have failed. It must read like THIS agent — and only this agent — wrote it.

Three fidelity rules that override everything else:

1. CADENCE matters more than vocabulary. Read the voice sample carefully and mirror its sentence rhythm:
   - Match em-dash usage. If the sample uses em-dashes for clarifying or qualifying clauses, your output must too.
   - Match colon-after-setup constructions (e.g. "comes down to one thing: who's running the process").
   - Match the alternation between long, clause-stacked sentences and short flat ones. Short declarative sentences after longer ones land hard. Use them.
   - Match where the warmth lives. In some voices, warmth lives in the third beat after an em-dash. In others, it lives in a brief sign-off. Read the sample and match.

2. DISTINCTIVE PHRASES from the voice sample should appear VERBATIM somewhere in the output, not paraphrased. If the sample says "That's your decision, on your timeline" — use that exact phrase, do not rewrite it as "the timing is yours" or "it's your call." The agent's signature moves are the most important voice signal.

3. BANNED PHRASES — these are dead giveaways of LLM house style and must not appear:
   - "I'd be honored" / "honored to"
   - "navigating" (as in "navigating decisions")
   - "I hope this finds you well"
   - "weight of both" / "weight of this" / similar sentimental abstraction
   - "during this difficult time"
   - "if it ever does" (corny redundancy after a conditional)
   - "I understand how complex this process can be"
   - "I want you to know that..." (preamble)
   - "Please don't hesitate to..." (formal cliche)
   - "I'd love to..." / "I'd welcome the opportunity to..."
   - Any sentence that begins with "Whether you..." or "Whether that's..." (LLM tic)

Other rules:
- Sound like the agent, not like a copywriter.
- Avoid salesy language.
- Avoid pressure.
- Avoid overexplaining.
- Do not invent credentials, statistics, or personal claims.
- Use plain words. Complexity comes from sentence structure, not vocabulary.
- If you are tempted to add an adjective for warmth ("genuine," "heartfelt," "sincere," "thoughtful"), don't. The structure does the work; adjectives drain it.
- Sign-offs that do warmth work the body should be doing ("Warm regards," "With sincere gratitude") are forbidden. End on the actual point or a flat closer."""


_ARCHETYPE_CONTEXT = {
    'probate': """The recipient is the personal representative of an estate after a death — a family member (often spouse, adult child, or sibling) who has been appointed by the court to administer the deceased's affairs. They are dealing with grief AND administrative complexity simultaneously. The property may need to be sold, transferred to a beneficiary, or held; that decision belongs to the family on their timeline. The agent should NOT pressure, NOT assume the property will be sold, and NOT address the deceased.""",

    'divorce': """The recipient is an owner navigating a divorce or asset division. The property may be subject to a settlement decision. This requires extreme discretion — the agent must NOT mention divorce directly, MUST NOT imply the agent has private knowledge of the situation, and should frame outreach around generic "property decisions during life transitions" without specifying what kind. The owner may not yet have decided whether to sell.""",

    'investor': """The recipient is an institutional or investor owner (often an LLC, trust holding investment property, or out-of-area individual). The property is held as an asset, not a primary residence. Conversation expectations are business-tone — disposition timing, cap rate, 1031 considerations, off-market opportunity. The owner is sophisticated; do not over-explain market basics.""",

    'trust': """The recipient is the trustee of a trust holding the property. The trustee may be the spouse, an adult child, a professional, or a family-elected representative. The decision about the property is FIDUCIARY — made on behalf of beneficiaries, in coordination with counsel and accountants, on the trust's timeline. Tone should be respectful of fiduciary duty, institutional rather than personal.""",

    'longTenure': """The recipient is a long-time homeowner — typically 15+ years at the property — with no obvious distress signal or court filing. There is no urgent trigger. The goal is to start a relationship, not push for a listing. Tone should be soft, patient, locally credible. Avoid 'your home is worth' hype. Do not assume they want to sell or that life events are imminent.""",

    'estateTransition': """The recipient is part of a family with a long-held property in a transition phase — multi-generational ownership, possible upcoming inheritance, or recent family changes that may affect the property. No court filing has occurred yet. Tone should be relational, family-aware, low-pressure.""",
}


_BIO_USAGE_RULES = """Bio material rules:

- The agent has provided background information. Use it ONLY when it connects organically to this specific lead's parcel, neighborhood, or situation.

- Most letters should NOT reference the agent's background at all. Default to silence on bio.

- When background is referenced, it should appear once, briefly, in service of the lead — never as preamble or self-introduction.

- NEVER force a connection that isn't there. "As a fellow Bellevue resident" only works when the lead is in Bellevue AND the agent has named Bellevue in their geographic_anchors.

- Bio material should NEVER reference the lead's personal details (their employer, their school, their family). Bio matches happen at the parcel/neighborhood level, not the person level.

- Affiliations (brokerage, boards, press) belong in letter 4 or letter 6 of a sequence, not letter 1."""


def _stance_to_behavior(stance: dict) -> str:
    """Convert the stance vector into explicit behavioral instructions.
    The LLM sees the behavioral instructions, not the raw keys. This
    is what makes outputs deterministic per agent."""
    lines = []

    sa = stance.get('structural_acknowledgment', 'indirect')
    if sa == 'direct':
        lines.append('- It is acceptable to reference the situation explicitly (e.g., "I came across the probate filing"). The agent prefers being upfront about the source.')
    elif sa == 'indirect':
        lines.append('- Do not reference filings, court records, or the source of how the agent learned about this situation. Keep the source vague (e.g., "I work with families navigating decisions about a home").')
    else:
        lines.append('- The agent reads the situation case-by-case. Default to vague unless the lead context strongly justifies being explicit.')

    tempo = stance.get('first_contact_tempo', 'first')
    if tempo == 'first':
        lines.append('- This agent values being early. Tone of letter 1 is timely, not delayed or hesitant.')
    else:
        lines.append('- This agent prefers to come in late and quiet. Letter 1 should acknowledge the volume of cold outreach and position itself as different.')

    sub = stance.get('first_letter_substance', 'relationship')
    if sub == 'substance':
        lines.append('- Lead with substance and market knowledge in early letters, not introduction or relationship.')
    else:
        lines.append('- Lead with introduction and relationship in early letters. Substance and market data appear in later letters (60+ days in).')

    length = stance.get('preferred_length', 'long_rare')
    if length == 'short_frequent':
        lines.append('- Letters should run SHORT — 3-5 sentences max per letter. Brevity is part of the voice.')
    else:
        lines.append('- Letters can run longer (5-12 sentences) — this agent prefers fewer, weightier touches over short frequent ones.')

    fu = stance.get('follow_up_posture', 'cadence')
    if fu == 'cadence':
        lines.append('- Continue the cadence even without response. The full 6-letter sequence runs regardless of reply.')
    else:
        lines.append('- After 1-2 letters with no response, the sequence steps back. Letters 3-6 should reflect that posture (less frequent, more "standing offer" tone).')

    pv = stance.get('price_voice', 'only_when_asked')
    if pv == 'comfortable_early':
        lines.append('- The agent is comfortable referencing specific values, comps, or dollar figures in early letters where useful.')
    else:
        lines.append('- Avoid specific numbers, comps, or valuations unless the lead has explicitly asked. Substance comes through framing, not numbers, in cold outreach.')

    sp = stance.get('self_presentation', 'understated')
    if sp == 'direct':
        lines.append('- The agent will reference experience, transactions, and credentials directly when relevant to credibility.')
    else:
        lines.append('- Do not foreground the agent\'s experience or credentials. The work speaks. Letters should rarely reference the agent\'s background.')

    ca = stance.get('competitor_acknowledgment', 'dont_reference')
    if ca == 'acknowledge':
        lines.append('- It is acceptable to acknowledge the agent\'s competition directly (e.g., "if you\'ve decided to work with someone else, that\'s fine"). Naming the elephant builds trust.')
    else:
        lines.append('- Do not reference other agents or competing offers. Focus on what this agent brings.')

    dk = stance.get('door_knock_posture', 'signal_required')
    if dk == 'cold_open':
        lines.append('- Door scripts can assume the agent is comfortable cold-knocking. Default opener engages directly when someone answers.')
    else:
        lines.append('- Door scripts should default to leave-behind only — cards and notes left at the door, not active engagement, unless explicit signal indicates the recipient wants conversation.')

    pp = stance.get('phone_posture', 'letter_first')
    if pp == 'comfortable_cold':
        lines.append('- Phone scripts assume the agent is comfortable calling cold as the first touch.')
    else:
        lines.append('- Phone scripts default to letter-first posture: the call comes only after a letter, or only after the recipient has signaled willingness.')

    return '\n'.join(lines)


def _format_bio(bio: dict) -> str:
    """Format bio dict into the prompt-block. Returns 'No bio provided.'
    when empty — the prompt rules already say to default to silence on
    bio, so empty just makes that explicit."""
    if not bio:
        return 'No bio provided.'

    parts = []

    bg = bio.get('background', '').strip()
    if bg:
        parts.append(f'Background:\n{bg}')

    anchors = bio.get('geographic_anchors', [])
    if anchors:
        anchor_lines = []
        for a in anchors:
            if isinstance(a, dict):
                n = a.get('neighborhood', '').strip()
                r = a.get('relationship', '').strip()
                if n and r:
                    anchor_lines.append(f'- {n}: {r}')
                elif n:
                    anchor_lines.append(f'- {n}')
        if anchor_lines:
            parts.append('Geographic anchors:\n' + '\n'.join(anchor_lines))

    aff = bio.get('affiliations', '').strip()
    if aff:
        parts.append(f'Affiliations:\n{aff}')

    if not parts:
        return 'No bio provided.'
    return '\n\n'.join(parts)


def _build_voice_prompt(voice_sample: str, stance: dict, bio: dict,
                        archetype: str) -> str:
    """Construct the per-archetype user prompt."""
    archetype_context = _ARCHETYPE_CONTEXT.get(archetype, _ARCHETYPE_CONTEXT['longTenure'])
    behavior = _stance_to_behavior(stance)
    bio_block = _format_bio(bio)

    return f"""Here is how this agent communicates:

{voice_sample.strip() if voice_sample else '(No voice sample provided — use a neutral, measured, professional voice as a default.)'}

Behavioral implications for this agent (apply these strictly):
{behavior}

Agent bio (use only when organically relevant to the lead's parcel or neighborhood):

{bio_block}

{_BIO_USAGE_RULES}

Now write this agent's outreach for the following situation:

Archetype: {archetype}

Context:
{archetype_context}

Write the full outreach package as a JSON object with these keys:

{{
  "letter_sequence": [
    {{ "day": 1,   "title": "...", "body": "..." }},
    {{ "day": 30,  "title": "...", "body": "..." }},
    {{ "day": 60,  "title": "...", "body": "..." }},
    {{ "day": 90,  "title": "...", "body": "..." }},
    {{ "day": 135, "title": "...", "body": "..." }},
    {{ "day": 180, "title": "...", "body": "..." }}
  ],
  "phone_script": "...",
  "door_script": "..."
}}

Use these placeholder tokens for lead-specific details (they will be substituted at render time):
- [PROPERTY_ADDRESS]
- [NEIGHBORHOOD]
- [RECIPIENT_NAME]   (the personal representative for probate, the trustee for trust, the owner for others)
- [DECEDENT_NAME]    (probate only — the name of the deceased)
- [AGENT_NAME]       (the agent's signature)

Phone script formatting: include "BEFORE YOU CALL" / "OPENER" / "REASON" / "LIKELY REACTIONS" (with 3 reaction branches: send-info / not-interested / busy) / "GRACEFUL EXIT" / "AFTER THE CALL" sections. The agent's spoken lines should be marked "YOU:".

Door script formatting: include "BEFORE YOU KNOCK — JUDGMENT CALL" (with at least 2-3 specific situational rules: when to knock, when to leave a card without knocking) / "OPENER" / "LIKELY REACTIONS" / "LEAVE-BEHIND" sections.

Output only the JSON object. No preamble, no markdown fence."""


@router.post("/voice-smoketest", dependencies=[Depends(require_admin)])
async def voice_smoketest_endpoint(payload: dict):
    """
    Construct the agent-voice prompt from the supplied inputs, call
    Anthropic, return raw output. No DB write, no auth-tied storage.
    Pure passthrough so we can iterate the prompt against real model
    output before building the surrounding infrastructure.

    Request body:
    {
      "voice_sample": "...",
      "stance": { ...10 keys... },
      "bio": { background, geographic_anchors, affiliations },
      "archetype": "probate" | "divorce" | "investor" | "trust" |
                   "longTenure" | "estateTransition"
    }

    Returns:
    {
      "archetype": "...",
      "model": "claude-sonnet-4-20250514",
      "tokens_in": N, "tokens_out": N,
      "raw_output": "...",       # the full string Anthropic returned
      "parsed": { ... } | null,  # JSON.parse'd if it parses cleanly
      "user_prompt": "...",      # the full constructed user prompt,
                                 # for prompt-debugging
    }

    Errors out if the Anthropic SDK is unavailable or the API call fails.
    """
    voice_sample = payload.get('voice_sample', '')
    stance = payload.get('stance', {}) or {}
    bio = payload.get('bio', {}) or {}
    archetype = payload.get('archetype', 'longTenure')

    if archetype not in _ARCHETYPE_CONTEXT:
        raise HTTPException(400, f"unknown archetype: {archetype}")

    user_prompt = _build_voice_prompt(voice_sample, stance, bio, archetype)

    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise HTTPException(503, f"Anthropic SDK not available: {e}")

    client = Anthropic()

    try:
        resp = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            system=_AGENT_VOICE_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
    except Exception as e:
        raise HTTPException(502, f"Anthropic API call failed: {e}")

    raw_output = resp.content[0].text if resp.content else ''

    # Try to JSON-parse — if it works, return parsed. If not, return null
    # for parsed and let the caller eyeball raw_output.
    parsed = None
    try:
        import json as _json
        # Strip markdown code fences if the model added them despite instructions
        clean = raw_output.strip()
        if clean.startswith('```'):
            # Remove first line (```json or ```) and last line (```)
            lines = clean.split('\n')
            if lines[0].startswith('```'): lines = lines[1:]
            if lines and lines[-1].strip() == '```': lines = lines[:-1]
            clean = '\n'.join(lines)
        parsed = _json.loads(clean)
    except Exception:
        parsed = None

    return {
        'archetype': archetype,
        'model': 'claude-sonnet-4-20250514',
        'tokens_in': getattr(resp.usage, 'input_tokens', None),
        'tokens_out': getattr(resp.usage, 'output_tokens', None),
        'raw_output': raw_output,
        'parsed': parsed,
        'user_prompt': user_prompt,
    }
