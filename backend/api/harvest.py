"""
Harvester API endpoints.

Gate: admin-key (same mechanism as the canonicalize/rescore endpoints).
Harvester runs can be expensive and shouldn't be casually triggered.

Endpoints:
  POST /api/harvest/run             Run a harvest + match cycle
  GET  /api/harvest/status/{zip}    Summary of raw_signals + matches for a ZIP
"""

from __future__ import annotations

import os
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.harvesters.orchestrator import run_harvest, HARVESTERS
from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

router = APIRouter()


# ─── Admin-key guard ───────────────────────────────────────────────────

def _require_admin(x_admin_key: Optional[str]):
    server_key = os.environ.get("ADMIN_KEY")
    if not server_key:
        raise HTTPException(503, "ADMIN_KEY not configured server-side")
    if x_admin_key != server_key:
        raise HTTPException(401, "Missing or invalid X-Admin-Key header")


# ─── Request / response models ─────────────────────────────────────────

class HarvestRunRequest(BaseModel):
    source: str = Field(
        "kc_superior_court",
        description="Harvester key. See HARVESTERS registry.",
    )
    case_types: Optional[list[str]] = Field(
        None,
        description=(
            "Harvester-specific subset. For kc_superior_court: "
            "['probate', 'divorce'] (default = both)."
        ),
    )
    since_days_ago: int = Field(
        30,
        ge=1,
        le=730,
        description=(
            "How many days back to harvest from today. Ignored if "
            "since_date is provided."
        ),
    )
    since_date: Optional[str] = Field(
        None,
        description="YYYY-MM-DD. Overrides since_days_ago if set.",
    )
    until_date: Optional[str] = Field(
        None,
        description=(
            "YYYY-MM-DD. Upper bound. Defaults to today. Use with "
            "since_date for arbitrary date windows (e.g. 30-day chunks "
            "to stay under HTTP timeouts on large backfills)."
        ),
    )
    zip_filter: Optional[str] = Field(
        "98004",
        description="Scope matches to this ZIP. None = all covered ZIPs.",
    )
    dry_run: bool = Field(
        False,
        description=(
            "If true, harvester parses but writes NOTHING to Supabase. "
            "Useful for first-run parser validation."
        ),
    )
    match_after: bool = Field(
        True,
        description="Run matcher immediately after harvest.",
    )


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.post("/run")
def harvest_run(
    req: HarvestRunRequest,
    x_admin_key: Optional[str] = Header(None),
):
    """
    Fire a harvest + match cycle.

    For the pilot:
      - source: 'kc_superior_court'
      - case_types: ['probate', 'divorce']
      - since_days_ago: 30-180
      - zip_filter: '98004'

    Response includes harvested count, upsert counts (new vs duplicate),
    and match statistics.
    """
    _require_admin(x_admin_key)

    if req.source not in HARVESTERS:
        raise HTTPException(400, f"Unknown source. Available: {list(HARVESTERS)}")

    # Resolve date window: explicit dates override since_days_ago.
    # Chunking strategy: to avoid Railway's ~5-min HTTP timeout on large
    # backfills, callers can pass 30-day windows (e.g. since_date=2025-11-01,
    # until_date=2025-12-01) and make multiple calls.
    try:
        if req.until_date:
            until = date.fromisoformat(req.until_date)
        else:
            until = date.today()
        if req.since_date:
            since = date.fromisoformat(req.since_date)
        else:
            since = until - timedelta(days=req.since_days_ago)
    except ValueError as e:
        raise HTTPException(400, f"Invalid date format (expected YYYY-MM-DD): {e}")

    if since > until:
        raise HTTPException(400, "since_date must be <= until_date")

    stats = run_harvest(
        source=req.source,
        since=since,
        until=until,
        case_types=req.case_types,
        zip_filter=req.zip_filter,
        dry_run=req.dry_run,
        match_after=req.match_after,
    )
    return stats


@router.post("/match-only")
def harvest_match_only(
    x_admin_key: Optional[str] = Header(None),
    zip_filter: Optional[str] = "98004",
    batch_size: int = 100,
    max_batches: int = 200,
):
    """
    Run JUST the matcher against already-harvested signals. Skips the
    harvest step entirely. Safe to run repeatedly — the matcher only
    processes rows with matched_at IS NULL.

    Use case: a previous harvest wrote signals to raw_signals_v3 but
    the matcher phase never ran (e.g. HTTP timeout killed the request
    handler mid-run). This endpoint picks up where it left off.

    Typical runtime: ~1-3 minutes for a few thousand pending signals.
    Far under the Railway HTTP timeout because matching is just DB
    reads + writes (no external scraping).
    """
    _require_admin(x_admin_key)

    # Import locally to avoid circular-ish load at module import time
    from backend.harvesters import matcher
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    stats = matcher.process_unmatched(
        supa,
        zip_filter=zip_filter,
        batch_size=batch_size,
        max_batches=max_batches,
    )
    return stats


@router.post("/reset")
def harvest_reset(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
):
    """
    Delete ALL rows from raw_signals_v3 and raw_signal_matches_v3.

    For pilot iteration only — gives us a clean slate to re-run
    harvesters after filter changes. Pass ?confirm=true to actually
    perform the delete.
    """
    _require_admin(x_admin_key)

    if not confirm:
        raise HTTPException(
            400,
            "This deletes all harvester data. Pass ?confirm=true to proceed.",
        )

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # Cascade: delete raw_signals deletes raw_signal_matches via FK
    # But be explicit about both for safety + count reporting
    matches_res = (supa.table('raw_signal_matches_v3')
                   .delete()
                   .neq('id', -1)      # match all rows (id > 0)
                   .execute())
    signals_res = (supa.table('raw_signals_v3')
                   .delete()
                   .neq('id', -1)
                   .execute())

    return {
        "deleted_matches": len(matches_res.data or []),
        "deleted_signals": len(signals_res.data or []),
    }



@router.get("/status/{zip_code}")
def harvest_status(zip_code: str):
    """
    Summary of harvested signals and matches for a ZIP.

    Counts:
      - raw_signals_v3 rows total + by (source_type, signal_type)
      - raw_signals_v3 processed vs unmatched
      - raw_signal_matches_v3 rows scoped to this ZIP's parcels
      - Distinct matched parcels in this ZIP
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # All raw signals — paginate because Supabase REST caps at 1000/req
    all_raw: list[dict] = []
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('raw_signals_v3')
               .select('source_type, signal_type, matched_at')
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        all_raw.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 500000:  # safety bound
            break

    by_source_type: dict = {}
    processed = 0
    for row in all_raw:
        key = f"{row['source_type']}::{row['signal_type']}"
        by_source_type[key] = by_source_type.get(key, 0) + 1
        if row.get('matched_at'):
            processed += 1

    # Pins in this ZIP — paginate because Supabase REST caps at 1000/req
    pins: list[str] = []
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin')
               .eq('zip_code', zip_code)
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        pins.extend(r['pin'] for r in batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 100000:
            break

    # Matches for parcels in this ZIP + distinct match pins
    matched_count = 0
    matched_pins: set = set()
    if pins:
        CHUNK = 200
        for i in range(0, len(pins), CHUNK):
            chunk = pins[i : i + CHUNK]
            res = (supa.table('raw_signal_matches_v3')
                   .select('pin', count='exact')
                   .in_('pin', chunk)
                   .limit(5000)
                   .execute())
            matched_count += res.count or 0
            for r in (res.data or []):
                matched_pins.add(r['pin'])

    return {
        "zip_code":              zip_code,
        "parcels_in_zip":        len(pins),
        "raw_signals_total":     len(all_raw),
        "raw_signals_processed": processed,
        "raw_signals_pending":   len(all_raw) - processed,
        "raw_signals_by_type":   by_source_type,
        "total_matches":         matched_count,
        "distinct_matched_pins": len(matched_pins),
    }


@router.get("/matches/{zip_code}")
def harvest_matches(
    zip_code: str,
    limit: int = 100,
    include_weak: bool = False,
):
    """
    The actual prospect list: matched parcels in this ZIP with their
    triggering signals.

    Returns one row per (parcel, signal) match, joined to parcel info
    and signal detail. Sorted by most recent event_date first.

    By default, weak-strength matches (surname-only, permissive name
    collisions) are filtered out. Weak matches are overwhelmingly false
    positives in practice — e.g. "John K Anderson" parcel matched to a
    "Mark John Anderson" divorce party because both share the surname.
    Use ?include_weak=true to see everything for debugging.
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be 1–1000")

    # Pins in this ZIP — paginate because Supabase REST caps at 1000/req
    parcels_by_pin: dict = {}
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin, owner_name, address, city, total_value, owner_type')
               .eq('zip_code', zip_code)
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        for r in batch:
            parcels_by_pin[r['pin']] = r
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 100000:
            break
    pins = list(parcels_by_pin.keys())
    if not pins:
        return {"zip_code": zip_code, "matches": []}

    # Fetch matches for these pins
    all_matches: list[dict] = []
    CHUNK = 200
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i : i + CHUNK]
        q = (supa.table('raw_signal_matches_v3')
             .select('raw_signal_id, pin, match_strength, match_method, matched_at')
             .in_('pin', chunk)
             .limit(5000))
        if not include_weak:
            q = q.neq('match_strength', 'weak')
        res = q.execute()
        all_matches.extend(res.data or [])

    if not all_matches:
        return {"zip_code": zip_code, "matches": []}

    # Fetch the signal details for all matched raw_signal_ids
    signal_ids = list({m['raw_signal_id'] for m in all_matches})
    signals_by_id: dict = {}
    CHUNK_S = 300
    for i in range(0, len(signal_ids), CHUNK_S):
        chunk = signal_ids[i : i + CHUNK_S]
        res = (supa.table('raw_signals_v3')
               .select('id, source_type, signal_type, trust_level, party_names, '
                       'event_date, jurisdiction, document_ref, raw_data')
               .in_('id', chunk)
               .execute())
        for r in (res.data or []):
            signals_by_id[r['id']] = r

    # Assemble the response: one row per (parcel, signal)
    matches_out: list[dict] = []
    for m in all_matches:
        signal = signals_by_id.get(m['raw_signal_id'])
        parcel = parcels_by_pin.get(m['pin'])
        if not signal or not parcel:
            continue

        # Extract first party name for quick display
        parties = signal.get('party_names') or []
        first_party = parties[0].get('raw') if parties else None

        matches_out.append({
            "pin":              m['pin'],
            "owner_name":       parcel.get('owner_name'),
            "owner_type":       parcel.get('owner_type'),
            "address":          parcel.get('address'),
            "city":             parcel.get('city'),
            "total_value":      parcel.get('total_value'),
            "signal_type":      signal['signal_type'],
            "signal_source":    signal['source_type'],
            "trust_level":      signal['trust_level'],
            "event_date":       signal.get('event_date'),
            "matched_party":    first_party,
            "all_parties":      parties,
            "document_ref":     signal.get('document_ref'),
            "case_detail":      signal.get('raw_data', {}),
            "match_strength":   m['match_strength'],
            "matched_at":       m['matched_at'],
        })

    # Sort by event_date desc (most recent first), null dates at bottom
    matches_out.sort(
        key=lambda r: r.get('event_date') or '',
        reverse=True,
    )

    return {
        "zip_code":       zip_code,
        "total_matches":  len(matches_out),
        "returned":       min(limit, len(matches_out)),
        "matches":        matches_out[:limit],
    }
