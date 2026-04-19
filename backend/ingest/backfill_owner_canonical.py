"""
Backfill owner_canonical_v3 for an entire ZIP.

Idempotent and resumable: skips PINs that already have a canonical row,
unless --force is supplied. Tracks per-call cost and logs rate-limit waits.

Usage:
  python -m backend.ingest.backfill_owner_canonical 98004 --dry-run
  python -m backend.ingest.backfill_owner_canonical 98004 --limit 10   # smoke test
  python -m backend.ingest.backfill_owner_canonical 98004              # full ZIP
  python -m backend.ingest.backfill_owner_canonical 98004 --force      # re-parse all

Haiku 4.5 pricing (as of Apr 2026): $1/MTok in, $5/MTok out
Typical cost: ~$0.0005/name ≈ $3 per 6,000-parcel ZIP.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from backend.api.db import get_supabase_client
from backend.ingest.owner_canonicalizer import (
    canonicalize_owner_name,
    upsert_canonical,
    MODEL,
)


HAIKU_COST_IN_PER_MTOK = 1.0
HAIKU_COST_OUT_PER_MTOK = 5.0


def _fetch_all_parcels(supa, zip_code: str, page: int = 1000) -> list[dict]:
    """Paginate parcels_v3 past Supabase's default 1000-row cap."""
    out = []
    offset = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin, owner_name')
               .eq('zip_code', zip_code)
               .not_.is_('owner_name', 'null')
               .range(offset, offset + page - 1)
               .execute())
        batch = res.data or []
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return out


def _fetch_existing_pins(supa, zip_code: str, page: int = 1000) -> set[str]:
    """Return the set of PINs that already have a canonical row."""
    out: set[str] = set()
    offset = 0
    while True:
        # We don't have zip_code on owner_canonical_v3, so we have to
        # filter by PINs present in parcels_v3 for this ZIP. Simplest:
        # just pull all canonical rows and intersect. For a 6K-parcel
        # ZIP this is trivial.
        res = (supa.table('owner_canonical_v3')
               .select('pin')
               .range(offset, offset + page - 1)
               .execute())
        batch = res.data or []
        out.update(r['pin'] for r in batch)
        if len(batch) < page:
            break
        offset += page
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('zip_code', help="ZIP to backfill, e.g. 98004")
    ap.add_argument('--dry-run', action='store_true',
                    help="Count + show first 5 parcels, don't call API")
    ap.add_argument('--limit', type=int, default=None,
                    help="Only process the first N parcels (smoke test)")
    ap.add_argument('--force', action='store_true',
                    help="Re-parse even if a canonical row already exists")
    ap.add_argument('--sleep-ms', type=int, default=50,
                    help="Polite pause between calls (default 50ms)")
    args = ap.parse_args()

    print(f"[backfill] target ZIP: {args.zip_code}")
    print(f"[backfill] model:      {MODEL}")

    supa = get_supabase_client()

    # Load the full parcel universe for this ZIP
    parcels = _fetch_all_parcels(supa, args.zip_code)
    print(f"[backfill] parcels with owner_name: {len(parcels)}")
    if not parcels:
        print("[backfill] nothing to do")
        return 0

    # Filter by existing canonical rows unless --force
    if not args.force:
        existing = _fetch_existing_pins(supa, args.zip_code)
        before = len(parcels)
        parcels = [p for p in parcels if p['pin'] not in existing]
        print(f"[backfill] already canonicalized: {before - len(parcels)}")
        print(f"[backfill] remaining to process:  {len(parcels)}")

    if args.limit:
        parcels = parcels[: args.limit]
        print(f"[backfill] --limit {args.limit} applied, processing: {len(parcels)}")

    if args.dry_run:
        print("[backfill] DRY RUN — sample of what would be processed:")
        for p in parcels[:5]:
            print(f"  {p['pin']}  {p['owner_name']!r}")
        est_cost = len(parcels) * 0.0005
        print(f"[backfill] estimated cost: ${est_cost:.2f} at ~$0.0005/name")
        return 0

    if not parcels:
        print("[backfill] nothing to process")
        return 0

    # Real run
    total_tokens_in = 0
    total_tokens_out = 0
    low_conf: list[tuple[str, str, float]] = []
    errors: list[tuple[str, str]] = []
    start = time.time()
    sleep_s = max(0, args.sleep_ms) / 1000.0

    for i, p in enumerate(parcels, 1):
        pin = p['pin']
        raw = p['owner_name'] or ''
        result = canonicalize_owner_name(raw)

        # Telemetry (stripped before upsert)
        total_tokens_in += result.get('_tokens_in', 0) or 0
        total_tokens_out += result.get('_tokens_out', 0) or 0
        if '_error' in result:
            errors.append((pin, result['_error']))

        # Record low-confidence for review surfacing
        if result.get('confidence', 0) < 0.5:
            low_conf.append((pin, raw, result.get('confidence', 0)))

        # Write
        try:
            upsert_canonical(supa, pin, result)
        except Exception as e:
            errors.append((pin, f'upsert: {e}'))

        # Progress every 50 or at end
        if i % 50 == 0 or i == len(parcels):
            elapsed = time.time() - start
            rate = i / max(elapsed, 0.001)
            eta = (len(parcels) - i) / max(rate, 0.001)
            cost = (total_tokens_in * HAIKU_COST_IN_PER_MTOK +
                    total_tokens_out * HAIKU_COST_OUT_PER_MTOK) / 1_000_000
            print(f"  [{i}/{len(parcels)}] rate={rate:.1f}/s "
                  f"eta={eta:.0f}s cost=${cost:.4f} "
                  f"low_conf={len(low_conf)} err={len(errors)}")

        if sleep_s:
            time.sleep(sleep_s)

    # Summary
    elapsed = time.time() - start
    cost = (total_tokens_in * HAIKU_COST_IN_PER_MTOK +
            total_tokens_out * HAIKU_COST_OUT_PER_MTOK) / 1_000_000
    print()
    print(f"[backfill] DONE")
    print(f"  processed:    {len(parcels)}")
    print(f"  wall time:    {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  tokens in:    {total_tokens_in}")
    print(f"  tokens out:   {total_tokens_out}")
    print(f"  total cost:   ${cost:.4f}")
    print(f"  per-name:     ${cost/max(len(parcels),1):.6f}")
    print(f"  low_conf:     {len(low_conf)} (<0.5)")
    print(f"  errors:       {len(errors)}")

    if errors:
        print()
        print("[backfill] ERRORS:")
        for pin, msg in errors[:20]:
            print(f"  {pin}: {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    if low_conf:
        print()
        print("[backfill] LOW CONFIDENCE (<0.5) — review these:")
        for pin, raw, c in low_conf[:20]:
            print(f"  {pin} conf={c:.2f}  {raw!r}")
        if len(low_conf) > 20:
            print(f"  ... and {len(low_conf) - 20} more")

    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
