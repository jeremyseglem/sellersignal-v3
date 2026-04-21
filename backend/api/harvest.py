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
        description="How many days back to harvest from today.",
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

    until = date.today()
    since = until - timedelta(days=req.since_days_ago)

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


@router.get("/status/{zip_code}")
def harvest_status(zip_code: str):
    """
    Summary of harvested signals visible for a ZIP.

    Counts:
      - raw_signals_v3 rows by source_type
      - raw_signal_matches_v3 rows scoped to this ZIP's parcels
      - investigations_v3 rows with mode='harvester' for this ZIP
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # Raw signals by source (NOT ZIP-scoped — harvesters pull KC-wide)
    all_raw = (supa.table('raw_signals_v3')
               .select('source_type, signal_type', count='exact')
               .execute())

    by_source: dict = {}
    for row in all_raw.data or []:
        k = row['source_type']
        by_source[k] = by_source.get(k, 0) + 1

    # Matches for parcels in this ZIP
    pins_in_zip_res = (supa.table('parcels_v3')
                       .select('pin')
                       .eq('zip_code', zip_code)
                       .limit(10000)
                       .execute())
    pins = [r['pin'] for r in (pins_in_zip_res.data or [])]

    matched_count = 0
    if pins:
        # Chunk due to .in_ limits
        CHUNK = 200
        for i in range(0, len(pins), CHUNK):
            chunk = pins[i : i + CHUNK]
            res = (supa.table('raw_signal_matches_v3')
                   .select('id', count='exact')
                   .in_('pin', chunk)
                   .execute())
            matched_count += res.count or 0

    # Investigations from harvester mode
    harvester_invs = (supa.table('investigations_v3')
                      .select('pin', count='exact')
                      .eq('zip_code', zip_code)
                      .eq('mode', 'harvester')
                      .execute())

    return {
        "zip_code":                    zip_code,
        "parcels_in_zip":              len(pins),
        "raw_signals_total":           all_raw.count or 0,
        "raw_signals_by_source":       by_source,
        "matches_for_zip_parcels":     matched_count,
        "harvester_investigations":    harvester_invs.count or 0,
    }
