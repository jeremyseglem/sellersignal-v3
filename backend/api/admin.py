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
                    sleep_ms=50,
                    verbose=False,
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
