"""
ZIP build lifecycle CLI — the operator tool for adding a ZIP to SellerSignal.

Every ZIP goes through discrete, re-runnable build steps. This tool
drives that process. Each step is idempotent: running ingest twice
doesn't duplicate parcels, running classify twice produces the same
archetypes, etc.

Usage:
    python -m backend.ingest.zip_builder status 98004
    python -m backend.ingest.zip_builder register 98004 --market WA_KING --city Bellevue --state WA
    python -m backend.ingest.zip_builder ingest 98004
    python -m backend.ingest.zip_builder geocode 98004
    python -m backend.ingest.zip_builder classify 98004
    python -m backend.ingest.zip_builder band 98004
    python -m backend.ingest.zip_builder investigate 98004 --dry-run
    python -m backend.ingest.zip_builder investigate 98004
    python -m backend.ingest.zip_builder publish 98004
    python -m backend.ingest.zip_builder pause 98004 --note "data refresh in progress"

Stage order (each must complete before next):
    register  -> adds row to zip_coverage_v3 (in_development)
    ingest    -> pulls parcels from ArcGIS into parcels_v3
    geocode   -> fills lat/lng on parcels missing geometry
    classify  -> runs why_not_selling archetype classifier on every parcel
    band      -> assigns Band 0/1/2/2.5/3/4 based on value + ownership + tenure
    investigate -> runs Option A SerpAPI investigation (8 B3 + 12 B2.5 + 30 B2)
    publish   -> flips coverage status to 'live'

Status command shows where the ZIP currently is in the lifecycle.
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone
from typing import Optional

from backend.api.db import get_supabase_client


# ============================================================================
# Status reporter
# ============================================================================

def cmd_status(zip_code: str) -> int:
    """Show current build lifecycle progress for a ZIP."""
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    result = (supa.table('zip_coverage_v3')
              .select('*')
              .eq('zip_code', zip_code)
              .maybe_single()
              .execute())
    row = result.data if result else None

    if not row:
        print(f"\nZIP {zip_code} is NOT in coverage. Run 'register' first.")
        return 0

    print(f"\n═══ ZIP {zip_code} — {row.get('city', '?')}, {row.get('state', '?')} ({row.get('market_key')}) ═══")
    print(f"  Status:              {row['status']}")
    print(f"  Parcels ingested:    {row.get('parcel_count', 0):,}")
    print(f"  Investigated:        {row.get('investigated_count', 0):,}")
    print(f"  Current CALL NOW:    {row.get('current_call_now_count', 0)}")
    print()
    print("  Build progress:")
    stages = [
        ('Registered',           'created_at'),
        ('Parcels ingested',     'parcels_ingested_at'),
        ('Parcels geocoded',     'parcels_geocoded_at'),
        ('Archetypes classified','archetypes_classified_at'),
        ('Bands assigned',       'bands_assigned_at'),
        ('First investigation',  'first_investigation_at'),
        ('Went live',            'went_live_at'),
    ]
    for label, field in stages:
        ts = row.get(field)
        mark = '✓' if ts else ' '
        ts_str = ts[:19] if ts else '—'
        print(f"    [{mark}] {label:<26} {ts_str}")

    if row.get('admin_notes'):
        print(f"\n  Notes: {row['admin_notes']}")

    return 0


# ============================================================================
# Register
# ============================================================================

def cmd_register(zip_code: str, market_key: str, city: str, state: str,
                 source_url: Optional[str] = None) -> int:
    """Register a new ZIP as in_development. Idempotent."""
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    existing = (supa.table('zip_coverage_v3')
                .select('zip_code, status')
                .eq('zip_code', zip_code)
                .maybe_single()
                .execute())
    if existing and existing.data:
        print(f"ZIP {zip_code} already registered (status: {existing.data['status']})")
        return 0

    supa.table('zip_coverage_v3').insert({
        'zip_code':          zip_code,
        'market_key':        market_key,
        'city':              city,
        'state':             state,
        'status':            'in_development',
        'source_arcgis_url': source_url,
    }).execute()
    print(f"Registered ZIP {zip_code} ({city}, {state} — {market_key}) as in_development")
    return 0


# ============================================================================
# Ingest
# ============================================================================

def cmd_ingest(zip_code: str) -> int:
    """
    Pull parcels from the market's ArcGIS source into parcels_v3.
    Paginates, parses, upserts. Idempotent.
    """
    import asyncio
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    cov = (supa.table('zip_coverage_v3')
           .select('market_key, status, source_arcgis_url')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered. Run 'register' first.")
        return 1

    market_key = cov.data['market_key']
    print(f"\nIngest for ZIP {zip_code} (market: {market_key})")
    print(f"  Fetching from ArcGIS...")

    from backend.ingest.arcgis import fetch_parcels_for_zip, upsert_parcels, stamp_ingest_complete, MARKET_CONFIGS

    if market_key not in MARKET_CONFIGS:
        print(f"  ERROR: Market {market_key} not configured in arcgis.py")
        print(f"         Supported markets: {list(MARKET_CONFIGS.keys())}")
        return 1

    try:
        parcels = asyncio.run(fetch_parcels_for_zip(zip_code, market_key))
    except Exception as e:
        print(f"  ERROR during fetch: {e}")
        return 1

    print(f"  Fetched {len(parcels)} parcels from ArcGIS")
    if not parcels:
        print("  No parcels returned. Check ZIP and market_key are correct.")
        return 1

    print(f"  Upserting into parcels_v3...")
    stats = upsert_parcels(parcels)
    print(f"  ✓ Upserted: {stats['inserted_or_updated']} in {stats['batches']} batch(es)")
    if stats['failed']:
        print(f"  ⚠ Failed:   {stats['failed']}")

    # Quick quality check: how many have lat/lng, owner_name, value?
    with_geom = sum(1 for p in parcels if p.get('lat') and p.get('lng'))
    with_owner = sum(1 for p in parcels if p.get('owner_name'))
    with_value = sum(1 for p in parcels if p.get('total_value'))
    print(f"  Quality: {with_geom}/{len(parcels)} geocoded, "
          f"{with_owner}/{len(parcels)} named, "
          f"{with_value}/{len(parcels)} valued")

    stamp_ingest_complete(zip_code, len(parcels))
    print(f"  ✓ Stage complete for ZIP {zip_code}")
    return 0


# ============================================================================
# Geocode
# ============================================================================

def cmd_geocode(zip_code: str) -> int:
    """
    Fill lat/lng on parcels missing geometry.

    Most ArcGIS sources include geometry natively. This step handles edge
    cases (parcels imported without coords, or from sources without geometry).
    Uses Google Maps Geocoding API or Nominatim as fallback.

    NOT YET IMPLEMENTED.
    """
    print(f"\nGeocode for ZIP {zip_code}")
    print("  STATUS: NOT YET IMPLEMENTED")
    print("  Most parcels should already have geometry from ArcGIS.")
    print("  This step will only be needed for edge cases.")
    return 2


# ============================================================================
# Classify (archetypes)
# ============================================================================

def cmd_classify(zip_code: str) -> int:
    """
    Run why_not_selling archetype classification on every parcel in ZIP.

    This is the zero-API forensic classifier. It reads structural features
    (owner_type, tenure, value, flags) and assigns an archetype to every
    parcel. Archetypes power the map-click experience.

    Idempotent — running twice produces identical results.
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    from backend.scoring.why_not_selling import classify_archetype

    # Paginated read — Supabase caps results at 1000 per request
    parcels = []
    offset = 0
    page_size = 1000
    while True:
        page = (supa.table('parcels_v3')
                .select('pin, owner_name, owner_type, tenure_years, '
                        'total_value, is_absentee, is_out_of_state')
                .eq('zip_code', zip_code)
                .range(offset, offset + page_size - 1)
                .execute())
        rows = page.data or []
        parcels.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    if not parcels:
        print(f"No parcels found for ZIP {zip_code}. Run 'ingest' first.")
        return 1

    print(f"\nClassifying archetypes for {len(parcels)} parcels in ZIP {zip_code}...")

    from collections import Counter, defaultdict
    archetype_counts = Counter()
    by_archetype = defaultdict(list)
    for p in parcels:
        arch = classify_archetype(p)
        archetype_counts[arch] += 1
        by_archetype[arch].append(p['pin'])

    # Bulk update by archetype — one UPDATE per archetype group (vs 6000+ individual)
    # Use .in_() filter on the pin list so each archetype's pins update in one round-trip
    for arch, pins in by_archetype.items():
        # PostgREST has a URL length cap, so chunk large pin lists
        for i in range(0, len(pins), 200):
            chunk = pins[i:i + 200]
            (supa.table('parcels_v3')
             .update({'signal_family': arch})
             .in_('pin', chunk)
             .execute())

    print(f"  Classified. Distribution:")
    for arch, n in sorted(archetype_counts.items(), key=lambda t: -t[1]):
        print(f"    {arch:<28} {n:>6}")

    # Stamp completion
    supa.table('zip_coverage_v3').update({
        'archetypes_classified_at': datetime.now(timezone.utc).isoformat(),
        'parcel_count': len(parcels),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }).eq('zip_code', zip_code).execute()

    print(f"  ✓ Stage complete for ZIP {zip_code}")
    return 0


# ============================================================================
# Band
# ============================================================================

def cmd_band(zip_code: str) -> int:
    """
    Assign Band 0-4 to every parcel based on value, ownership, tenure, archetype.
    Idempotent — re-running produces identical assignments.
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    cov = (supa.table('zip_coverage_v3')
           .select('archetypes_classified_at, parcel_count')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered.")
        return 1
    if not cov.data.get('archetypes_classified_at'):
        print(f"ZIP {zip_code} has not been classified yet. Run 'classify' first.")
        return 1

    print(f"\nAssigning bands for ZIP {zip_code}...")
    from backend.scoring.banding_v3 import apply_banding_to_zip
    stats = apply_banding_to_zip(zip_code)

    if stats['total'] == 0:
        print(f"  No parcels found. Run 'ingest' first.")
        return 1

    print(f"  Processed {stats['total']} parcels. Distribution:")
    band_labels = {
        0: 'Band 0 (excluded)',
        1: 'Band 1 (weak signal)',
        2: 'Band 2 (monitoring)',
        2.5: 'Band 2.5 (elevated)',
        3: 'Band 3 (active prospect)',
        4: 'Band 4 (post-transaction)',
    }
    for band, count in stats['by_band'].items():
        label = band_labels.get(band, f'Band {band}')
        print(f"    {label:<32} {count:>6}")

    print(f"  ✓ Stage complete for ZIP {zip_code}")
    return 0


# ============================================================================
# Investigate
# ============================================================================

def cmd_investigate(zip_code: str, dry_run: bool = False, fresh: bool = False) -> int:
    """
    Run Option A investigation for the ZIP.
      8 Band 3 + 12 Band 2.5 + 30 Band 2 = up to 50 parcels screened
      Top 15 → deep investigation
      Expected cost ~$10 at SerpAPI pricing

    Dry-run first shows projected cost without spending.
    Use --fresh to clear the investigation cache before running (forces
    re-fetch from SerpAPI; use after upgrading the signal extractor).
    """
    import os as _os
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    # ── Preflight: confirm the mode explicitly ─────────────────────────
    serpapi_key_set = bool(_os.environ.get('SERPAPI_KEY'))
    mock_mode       = _os.environ.get('SELLERSIGNAL_MOCK') == '1'

    if dry_run:
        # Dry-run only computes cost estimates, doesn't call SerpAPI.
        # Mode still matters for display.
        pass
    else:
        if not serpapi_key_set and not mock_mode:
            print("\n╔═══════════════════════════════════════════════════════════╗")
            print("║  ERROR: SERPAPI_KEY is not set.                           ║")
            print("║                                                           ║")
            print("║  A real investigation requires a valid SerpAPI key.       ║")
            print("║  Two options:                                             ║")
            print("║                                                           ║")
            print("║  1. Set your key (for a real run, ~$7-10 per ZIP):        ║")
            print("║       export SERPAPI_KEY='your-key-here'                  ║")
            print("║                                                           ║")
            print("║  2. Explicitly run in mock mode (fixture data, $0 cost):  ║")
            print("║       export SELLERSIGNAL_MOCK=1                          ║")
            print("║                                                           ║")
            print("║  This check exists because silent mock-mode fallback      ║")
            print("║  previously caused synthetic test data to appear as real  ║")
            print("║  investigation results. Never again.                      ║")
            print("╚═══════════════════════════════════════════════════════════╝")
            return 1

        if mock_mode:
            print("\n╔═══════════════════════════════════════════════════════════╗")
            print("║  ⚠  MOCK MODE (SELLERSIGNAL_MOCK=1)                       ║")
            print("║                                                           ║")
            print("║  Investigations will use synthetic test fixtures.         ║")
            print("║  NO SerpAPI calls will be made. Cost: $0.                 ║")
            print("║  Results will NOT reflect real-world data.                ║")
            print("║  This is for pipeline validation only.                    ║")
            print("╚═══════════════════════════════════════════════════════════╝")
        else:
            print("\n═══ LIVE MODE — real SerpAPI calls will be made ═══")

    if fresh and not dry_run:
        print(f"\n⚠ --fresh flag: clearing investigation cache for ZIP {zip_code}...")
        deleted = (supa.table('investigations_v3')
                   .delete()
                   .eq('zip_code', zip_code)
                   .execute())
        n_deleted = len(deleted.data or [])
        print(f"  Deleted {n_deleted} cached investigation records")

    cov = (supa.table('zip_coverage_v3')
           .select('bands_assigned_at, status')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered.")
        return 1
    if not cov.data.get('bands_assigned_at'):
        print(f"ZIP {zip_code} has not been banded yet. Run 'band' first.")
        return 1

    from backend.selection.zip_investigation import run_investigation_for_zip

    if dry_run:
        print(f"\n═══ Dry-run investigation estimate for ZIP {zip_code} ═══")
        result = run_investigation_for_zip(zip_code, dry_run=True)

        if result.get('error'):
            print(f"  ERROR: {result['error']}")
            return 1

        print(f"  Scope size:          {result['scope_size']} parcels")
        print(f"  Est. screen searches: {result.get('screen_searches_est', 0)}")
        print(f"  Est. deep searches:   {result.get('deep_searches_est', 0)}")
        print(f"  Total searches:       {result['projected_searches']}")
        print(f"  Projected cost:       ${result['projected_cost_usd']}")
        print(f"  Current month usage:  {result.get('current_month_usage', 0)}")
        print(f"  Approved:             {result['approved']}")

        if not result['approved']:
            for r in result.get('reasons', []):
                print(f"    · {r}")
            return 1
        return 0

    # Real run
    print(f"\n═══ Running Option A investigation for ZIP {zip_code} ═══")
    print(f"  (This will spend real SerpAPI credits. Use --dry-run to estimate first.)")

    result = run_investigation_for_zip(zip_code, dry_run=False)

    if result.get('error'):
        print(f"  ERROR: {result['error']}")
        return 1

    if not result.get('approved'):
        print(f"  Not approved:")
        for r in result.get('reasons', []):
            print(f"    · {r}")
        return 1

    print(f"\n  ✓ Run complete")
    print(f"  Scope size:       {result['scope_size']}")
    print(f"  Finalists:        {result['finalists']}")
    print(f"  Live searches:    {result['total_searches']}")
    print(f"  Actual cost:      ${result['cost_usd']}")
    print(f"  Actions:")
    for k, v in sorted(result.get('actions', {}).items()):
        print(f"    {k:<12} {v}")

    print(f"  ✓ Stage complete for ZIP {zip_code}")
    return 0


# ============================================================================
# Publish
# ============================================================================

def cmd_publish(zip_code: str, force: bool = False) -> int:
    """
    Flip coverage status from 'in_development' to 'live'.

    Safety checks (unless --force):
      - All prior stages must have completed (parcels_ingested, classified,
        banded, first_investigation stamps all present)
      - parcel_count must be > 0
      - investigated_count must be > 0
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    result = (supa.table('zip_coverage_v3')
              .select('*')
              .eq('zip_code', zip_code)
              .maybe_single()
              .execute())
    row = result.data if result else None
    if not row:
        print(f"ZIP {zip_code} not in coverage.")
        return 1

    if row['status'] == 'live':
        print(f"ZIP {zip_code} is already live.")
        return 0

    # Safety checks
    if not force:
        missing = []
        if not row.get('parcels_ingested_at'):      missing.append('ingest')
        if not row.get('archetypes_classified_at'): missing.append('classify')
        if not row.get('bands_assigned_at'):        missing.append('band')
        if not row.get('first_investigation_at'):   missing.append('investigate')
        if (row.get('parcel_count') or 0) == 0:     missing.append('parcels present')
        if (row.get('investigated_count') or 0) == 0: missing.append('investigations present')

        if missing:
            print(f"Cannot publish — missing prerequisites:")
            for m in missing:
                print(f"    - {m}")
            print("\nRun prior stages first, or use --force to override (not recommended).")
            return 1

    supa.table('zip_coverage_v3').update({
        'status':       'live',
        'went_live_at': datetime.now(timezone.utc).isoformat(),
        'updated_at':   datetime.now(timezone.utc).isoformat(),
    }).eq('zip_code', zip_code).execute()

    # Invalidate the cache so live status propagates immediately
    try:
        from backend.api.zip_gate import invalidate_zip_cache
        invalidate_zip_cache(zip_code)
    except Exception:
        pass

    print(f"✓ ZIP {zip_code} is now LIVE. Agents can subscribe and briefings will generate.")
    return 0


# ============================================================================
# Pause
# ============================================================================

def cmd_pause(zip_code: str, note: Optional[str] = None) -> int:
    """Pause a live ZIP — briefings won't generate, API returns 404."""
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    update = {
        'status':     'paused',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if note:
        update['admin_notes'] = note

    supa.table('zip_coverage_v3').update(update).eq('zip_code', zip_code).execute()

    try:
        from backend.api.zip_gate import invalidate_zip_cache
        invalidate_zip_cache(zip_code)
    except Exception:
        pass

    print(f"✓ ZIP {zip_code} paused.")
    if note:
        print(f"  Note: {note}")
    return 0


def cmd_seed(zip_code: str, json_path: str) -> int:
    """
    Load parcels from a pre-built JSON file into parcels_v3.

    This is the "offline ingest" path — used when we have a known-good
    snapshot of a ZIP's parcels and don't want to re-fetch from live ArcGIS.
    The bundled seeds live under data/seeds/.
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    cov = (supa.table('zip_coverage_v3')
           .select('market_key, status')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered. Run 'register' first.")
        return 1

    market_key = cov.data['market_key']
    print(f"\nSeed ingest for ZIP {zip_code} (market: {market_key})")
    print(f"  Loading from {json_path}...")

    from backend.ingest.seed_from_json import (
        load_parcels_from_json, upsert_parcels, stamp_ingest_complete,
    )

    try:
        rows = load_parcels_from_json(json_path, zip_code, market_key)
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return 1
    except Exception as e:
        print(f"  ERROR loading JSON: {e}")
        return 1

    print(f"  Loaded {len(rows)} parcels from JSON")
    if not rows:
        print("  No parcels in file.")
        return 1

    print(f"  Upserting into parcels_v3...")
    stats = upsert_parcels(rows)
    print(f"  ✓ Upserted: {stats['inserted_or_updated']} in {stats['batches']} batch(es)")
    if stats['failed']:
        print(f"  ⚠ Failed:   {stats['failed']}")

    # Quality check
    with_owner = sum(1 for r in rows if r.get('owner_name'))
    with_value = sum(1 for r in rows if r.get('total_value'))
    with_tenure = sum(1 for r in rows if r.get('tenure_years') is not None)
    print(f"  Quality: {with_owner}/{len(rows)} named, "
          f"{with_value}/{len(rows)} valued, "
          f"{with_tenure}/{len(rows)} with tenure")
    print(f"  Note: lat/lng not in seed data — run 'geocode' separately if needed")

    stamp_ingest_complete(zip_code, len(rows))
    print(f"  ✓ Stage complete for ZIP {zip_code}")
    return 0


# ============================================================================
# Apply legal filings
# ============================================================================

def cmd_apply_filings(zip_code: str, csv_path: str, kind: str,
                      uploaded_by: str = 'cli', apply_signals: bool = True) -> int:
    """
    Ingest a legal-filings CSV and match it against this ZIP's parcels.

    Sources:
      - 'divorce'  : CSV export from KC Superior Court Family Law search
                     (dja-prd-ecexap1.kingcounty.gov/node/411?caseType=211110)
      - 'recorder' : CSV export from KC LandmarkWeb Record Date Search
                     (recordsearch.kingcounty.gov/LandmarkWeb)

    Writes:
      - legal_filings_v3       (one row per unique filing)
      - legal_filing_matches_v3 (one row per filing-to-parcel match)
      - parcels_v3.signal_family updated on STRONG matches (if apply_signals)
        · financial_stress   for NOD/trustee sale/lis pendens
        · divorce_unwinding  for dissolution filings

    ToS note: this path consumes CSVs that were manually exported by a
    human. It does not scrape. KC Recorder explicitly permits targeted
    manual searches and exports.
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    cov = (supa.table('zip_coverage_v3')
           .select('parcel_count, status')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered.")
        return 1
    if (cov.data.get('parcel_count') or 0) == 0:
        print(f"ZIP {zip_code} has no parcels. Run 'ingest' first.")
        return 1

    print(f"\n═══ Applying legal filings to ZIP {zip_code} ═══")
    print(f"  CSV:    {csv_path}")
    print(f"  Kind:   {kind}")
    print(f"  Apply:  {apply_signals}")

    from backend.ingest.legal_filings_ingest import ingest_csv

    try:
        result = ingest_csv(
            csv_path=csv_path,
            filing_kind=kind,
            zip_code=zip_code,
            uploaded_by=uploaded_by,
            apply_signals=apply_signals,
        )
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    if result.get('error'):
        print(f"  ERROR: {result['error']}")
        return 1

    print(f"\n  Filings parsed:     {result['filings_parsed']}")
    print(f"  Filings stored:     {result['filings_stored']}")
    print(f"  Matches written:    {result['matches_written']}")
    if apply_signals:
        print(f"  Signals promoted:   {result['signals_promoted']}")
        if result['affected_pins']:
            print(f"  Affected pins:      {', '.join(result['affected_pins'][:10])}"
                  f"{'...' if len(result['affected_pins']) > 10 else ''}")
            print(f"\n  Next step: re-run 'band' and 'investigate' on this ZIP to")
            print(f"            propagate the new signal_family values through the")
            print(f"            pipeline. Matched parcels will now surface as")
            print(f"            pressure-3 CALL NOWs in the briefing.")
    else:
        print(f"\n  (--no-apply was set; parcels_v3.signal_family was not modified.)")

    print(f"\n  ✓ Legal filings ingest complete for ZIP {zip_code}")
    return 0


def cmd_canonicalize(zip_code: str, dry_run: bool = False,
                     limit: Optional[int] = None, force: bool = False) -> int:
    """
    Canonicalize owner_name for every parcel in this ZIP via Haiku 4.5.

    Writes structured parses into owner_canonical_v3. Required before legal-
    filings matching produces clean results — the raw-string matcher produces
    false positives (e.g. 'ROBERT LEE HARRIS' decedent matched 'Robert Lee
    Steil' owner pressure=3 CALL NOW incorrectly in the Apr 18 test run).

    Idempotent: skips PINs that already have a canonical row unless --force.

    Cost: ~$0.0005 per parcel (~$3 for a 6,000-parcel ZIP).
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

    cov = (supa.table('zip_coverage_v3')
           .select('parcel_count, status')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not cov or not cov.data:
        print(f"ZIP {zip_code} not registered.")
        return 1
    if (cov.data.get('parcel_count') or 0) == 0:
        print(f"ZIP {zip_code} has no parcels. Run 'ingest' first.")
        return 1

    print(f"\n═══ Canonicalizing owner names for ZIP {zip_code} ═══")
    print(f"  dry_run: {dry_run}")
    print(f"  limit:   {limit or 'all'}")
    print(f"  force:   {force}")

    # Delegate to the backfill module — it has the real logic.
    import sys as _sys
    argv_save = _sys.argv[:]
    _sys.argv = ['backfill_owner_canonical', zip_code]
    if dry_run:
        _sys.argv.append('--dry-run')
    if limit:
        _sys.argv.extend(['--limit', str(limit)])
    if force:
        _sys.argv.append('--force')
    try:
        from backend.ingest.backfill_owner_canonical import main as backfill_main
        return backfill_main()
    finally:
        _sys.argv = argv_save


# ============================================================================
# CLI entry
# ============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="SellerSignal ZIP build lifecycle tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest='command', required=True)

    # status
    s = sub.add_parser('status', help='Show ZIP build progress')
    s.add_argument('zip_code')

    # register
    s = sub.add_parser('register', help='Add ZIP to coverage (in_development)')
    s.add_argument('zip_code')
    s.add_argument('--market', required=True, help='e.g. WA_KING, FL_MD, AZ_MARICOPA')
    s.add_argument('--city',   required=True)
    s.add_argument('--state',  required=True)
    s.add_argument('--source-url', default=None, help='ArcGIS endpoint URL')

    # ingest, geocode, classify, band, investigate
    for cmd_name, help_text in [
        ('ingest',    'Pull parcels from ArcGIS'),
        ('geocode',   'Fill lat/lng on parcels missing geometry'),
        ('classify',  'Assign why-not-selling archetypes'),
        ('band',      'Assign Band 0-4 to every parcel'),
        ('investigate', 'Run Option A SerpAPI investigation'),
    ]:
        s = sub.add_parser(cmd_name, help=help_text)
        s.add_argument('zip_code')
        if cmd_name == 'investigate':
            s.add_argument('--dry-run', action='store_true',
                           help='Estimate cost only, do not spend')
            s.add_argument('--fresh', action='store_true',
                           help='Clear investigation cache first (force re-fetch)')

    # publish
    s = sub.add_parser('publish', help='Flip status to live')
    s.add_argument('zip_code')
    s.add_argument('--force', action='store_true',
                   help='Skip prerequisite checks (not recommended)')

    # pause
    s = sub.add_parser('pause', help='Pause a live ZIP')
    s.add_argument('zip_code')
    s.add_argument('--note', default=None)

    # seed (offline ingest from JSON file)
    s = sub.add_parser('seed',
                       help='Offline ingest from a pre-built JSON file (data/seeds/*.json)')
    s.add_argument('zip_code')
    s.add_argument('--file', required=True,
                   help='Path to seed JSON (e.g. data/seeds/wa-king-98004.json)')

    # apply_filings (legal filings CSV ingest)
    s = sub.add_parser('apply_filings',
                       help='Ingest a legal-filings CSV (court dissolution or recorder NOD/trustee sale/lis pendens) and promote matched parcels')
    s.add_argument('zip_code')
    s.add_argument('--csv', required=True,
                   help='Path to CSV export (from KC Superior Court or LandmarkWeb)')
    s.add_argument('--kind', required=True, choices=['divorce', 'recorder'],
                   help="'divorce' for dissolution filings, 'recorder' for NOD/trustee/lis pendens")
    s.add_argument('--uploaded-by', default='cli',
                   help="Identifier for provenance (default: 'cli')")
    s.add_argument('--no-apply', action='store_true',
                   help="Parse and match only; don't update parcels_v3.signal_family")

    # canonicalize (owner-name LLM parsing into owner_canonical_v3)
    s = sub.add_parser('canonicalize',
                       help='Parse owner_name for every parcel in the ZIP (Haiku 4.5, ~$3/ZIP)')
    s.add_argument('zip_code')
    s.add_argument('--dry-run', action='store_true',
                   help='Show what would be processed, do not call API')
    s.add_argument('--limit', type=int, default=None,
                   help='Process only first N parcels (smoke test)')
    s.add_argument('--force', action='store_true',
                   help='Re-canonicalize even when a row already exists')

    args = p.parse_args()

    if args.command == 'status':       return cmd_status(args.zip_code)
    if args.command == 'register':     return cmd_register(
        args.zip_code, args.market, args.city, args.state, args.source_url)
    if args.command == 'ingest':       return cmd_ingest(args.zip_code)
    if args.command == 'geocode':      return cmd_geocode(args.zip_code)
    if args.command == 'classify':     return cmd_classify(args.zip_code)
    if args.command == 'band':         return cmd_band(args.zip_code)
    if args.command == 'investigate':  return cmd_investigate(args.zip_code, args.dry_run, args.fresh)
    if args.command == 'publish':      return cmd_publish(args.zip_code, args.force)
    if args.command == 'pause':        return cmd_pause(args.zip_code, args.note)
    if args.command == 'seed':         return cmd_seed(args.zip_code, args.file)
    if args.command == 'apply_filings': return cmd_apply_filings(
        args.zip_code, args.csv, args.kind, args.uploaded_by, not args.no_apply)
    if args.command == 'canonicalize': return cmd_canonicalize(
        args.zip_code, args.dry_run, args.limit, args.force)

    return 1


if __name__ == '__main__':
    sys.exit(main())
