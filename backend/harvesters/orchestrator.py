"""
Harvester orchestrator.

Wires harvester → raw_signals_v3 persistence → matcher into one
runnable unit. API endpoints call this; so can the cron scheduler.

Flow:
  1. Harvester pulls filings from primary source (e.g. WA Courts)
  2. Each RawSignal is upserted into raw_signals_v3 (dedup on
     source_type + document_ref)
  3. Matcher picks up unmatched rows and resolves them to parcels
  4. Match results surface via investigations_v3 → scoring engine

Usage:
    stats = run_harvest(
        source='kc_superior_court',
        since=date(2024, 10, 20),   # 6 months back
        until=date.today(),
        zip_filter='98004',
        dry_run=False,
    )
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from . import matcher
from .base import RawSignal
from .kc_superior_court import KCSuperiorCourtHarvester
from .kc_treasury import KCTreasuryForeclosureHarvester
from .obituary import ObituaryHarvester
from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)


# ─── Harvester registry ────────────────────────────────────────────────

HARVESTERS = {
    "kc_superior_court": lambda case_types: KCSuperiorCourtHarvester(case_types),
    "obituary":          lambda _unused:    ObituaryHarvester(),
    # KC Treasury tax-foreclosure: property-based signal, not party-based.
    # Accepts the case_types arg for interface compatibility but ignores it
    # (the Treasury feed has no sub-types).
    "kc_treasury":       lambda _unused:    KCTreasuryForeclosureHarvester(),
    # Future: "kc_recorder" (captcha-blocked — see kc_treasury.py comments),
    # "wa_sos", "zillow_sitemap"
}


# ─── Public orchestration ──────────────────────────────────────────────

def run_harvest(
    source: str,
    since: date,
    until: Optional[date] = None,
    case_types: Optional[list[str]] = None,
    zip_filter: Optional[str] = "98004",
    dry_run: bool = False,
    match_after: bool = True,
    match_batch_size: int = 100,
) -> dict:
    """
    Run a full harvest + match cycle.

    source:          key into HARVESTERS registry
    since:           earliest filing date to pull
    until:           latest filing date (default: today)
    case_types:      harvester-specific subset (e.g. ['probate'])
    zip_filter:      scope matches to this ZIP (default 98004 for pilot)
    dry_run:         if True, harvest and parse but DON'T write anything
    match_after:     if True, run matcher immediately after harvest
    match_batch_size: batches for matcher

    Returns summary stats dict.
    """
    until = until or date.today()
    stats: dict = {
        "source":           source,
        "since":            since.isoformat(),
        "until":            until.isoformat(),
        "zip_filter":       zip_filter,
        "dry_run":          dry_run,
        "harvested":        0,
        "upserted_new":     0,
        "upserted_dup":     0,
        "errors":           [],
        "match_stats":      None,
    }

    if source not in HARVESTERS:
        stats["errors"].append(f"Unknown source: {source}")
        return stats

    harvester = HARVESTERS[source](case_types)
    supa = _supabase() if not dry_run else None

    # Harvest + upsert
    buffer: list[dict] = []
    BATCH = 50

    try:
        for signal in harvester.harvest(since=since, until=until):
            stats["harvested"] += 1
            if dry_run:
                # Just count; don't write
                continue
            buffer.append(signal.to_row())
            if len(buffer) >= BATCH:
                new, dup = _upsert_batch(supa, buffer)
                stats["upserted_new"] += new
                stats["upserted_dup"] += dup
                buffer = []
    except Exception as e:
        log.exception(f"Harvester {source} failed")
        stats["errors"].append(f"Harvest error: {e}")

    # Flush final partial batch
    if buffer and not dry_run:
        new, dup = _upsert_batch(supa, buffer)
        stats["upserted_new"] += new
        stats["upserted_dup"] += dup

    # Run matcher if requested
    if match_after and not dry_run:
        try:
            stats["match_stats"] = matcher.process_unmatched(
                supa,
                zip_filter=zip_filter,
                batch_size=match_batch_size,
                max_batches=50,
            )
        except Exception as e:
            log.exception("Matcher failed")
            stats["errors"].append(f"Match error: {e}")

    return stats


# ─── Internals ─────────────────────────────────────────────────────────

def _supabase():
    """Shared Supabase client (service-role). Raises if not configured."""
    supa = get_supabase_client()
    if supa is None:
        raise RuntimeError(
            "Supabase client not available — SUPABASE_URL/SUPABASE_SERVICE_KEY "
            "must be set for harvester runs."
        )
    return supa


def _upsert_batch(supa, rows: list[dict]) -> tuple[int, int]:
    """
    Upsert a batch of raw_signal rows. Dedup on (source_type, document_ref).

    Returns (new_count, dup_count).

    Supabase REST client doesn't give us per-row insert status on upsert,
    so we count by checking rows already present with this document_ref
    BEFORE the upsert. Cheap: we're already batching.
    """
    if not rows:
        return 0, 0

    # Dedup WITHIN the batch before upsert. Postgres refuses an ON CONFLICT
    # upsert if the same conflict key appears twice in one statement
    # (error 21000). Collisions can happen from:
    #   - Pagination reshuffling when new filings insert mid-scrape
    #   - Harvester-level duplicates from overlapping date windows
    #   - Multiple parties in a case parsed as multiple rows (shouldn't happen
    #     with current parser but defensive)
    # Keep first occurrence of each (source_type, document_ref) tuple.
    seen: set = set()
    deduped: list[dict] = []
    for r in rows:
        key = (r["source_type"], r["document_ref"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rows = deduped

    # Count how many of these document_refs already exist (for stats)
    refs_by_source: dict = {}
    for r in rows:
        refs_by_source.setdefault(r["source_type"], []).append(r["document_ref"])

    existing = 0
    for src, refs in refs_by_source.items():
        # Supabase .in_ has a practical cap around a few hundred per call
        CHUNK = 200
        for i in range(0, len(refs), CHUNK):
            chunk = refs[i : i + CHUNK]
            res = (supa.table('raw_signals_v3')
                   .select('id', count='exact')
                   .eq('source_type', src)
                   .in_('document_ref', chunk)
                   .execute())
            existing += res.count or 0

    # Now upsert — ON CONFLICT DO UPDATE refreshes raw_data without duplicating
    (supa.table('raw_signals_v3')
     .upsert(rows, on_conflict='source_type,document_ref')
     .execute())

    new = len(rows) - existing
    return max(new, 0), existing
