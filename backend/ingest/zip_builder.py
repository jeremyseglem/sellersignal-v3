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

    parcels_res = (supa.table('parcels_v3')
                   .select('pin, owner_name, owner_type, tenure_years, '
                           'total_value, is_absentee, is_out_of_state')
                   .eq('zip_code', zip_code)
                   .execute())
    parcels = parcels_res.data or []

    if not parcels:
        print(f"No parcels found for ZIP {zip_code}. Run 'ingest' first.")
        return 1

    print(f"\nClassifying archetypes for {len(parcels)} parcels in ZIP {zip_code}...")

    from collections import Counter
    archetype_counts = Counter()
    updates = []
    for p in parcels:
        arch = classify_archetype(p)
        archetype_counts[arch] += 1
        updates.append({'pin': p['pin'], 'signal_family': arch})

    # Batch upsert (1000 at a time to avoid payload limits)
    for i in range(0, len(updates), 1000):
        batch = updates[i:i + 1000]
        supa.table('parcels_v3').upsert(batch, on_conflict='pin').execute()

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

def cmd_investigate(zip_code: str, dry_run: bool = False) -> int:
    """
    Run Option A investigation for the ZIP.
      8 Band 3 + 12 Band 2.5 + 30 Band 2 = up to 50 parcels screened
      Top 15 → deep investigation
      Expected cost ~$10 at SerpAPI pricing

    Dry-run first shows projected cost without spending.
    """
    supa = get_supabase_client()
    if not supa:
        print("ERROR: Supabase not configured")
        return 1

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

    # publish
    s = sub.add_parser('publish', help='Flip status to live')
    s.add_argument('zip_code')
    s.add_argument('--force', action='store_true',
                   help='Skip prerequisite checks (not recommended)')

    # pause
    s = sub.add_parser('pause', help='Pause a live ZIP')
    s.add_argument('zip_code')
    s.add_argument('--note', default=None)

    args = p.parse_args()

    if args.command == 'status':       return cmd_status(args.zip_code)
    if args.command == 'register':     return cmd_register(
        args.zip_code, args.market, args.city, args.state, args.source_url)
    if args.command == 'ingest':       return cmd_ingest(args.zip_code)
    if args.command == 'geocode':      return cmd_geocode(args.zip_code)
    if args.command == 'classify':     return cmd_classify(args.zip_code)
    if args.command == 'band':         return cmd_band(args.zip_code)
    if args.command == 'investigate':  return cmd_investigate(args.zip_code, args.dry_run)
    if args.command == 'publish':      return cmd_publish(args.zip_code, args.force)
    if args.command == 'pause':        return cmd_pause(args.zip_code, args.note)

    return 1


if __name__ == '__main__':
    sys.exit(main())
