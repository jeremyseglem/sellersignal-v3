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


def backfill_zip(zip_code: str, dry_run: bool = False,
                 limit: Optional[int] = None, force: bool = False,
                 sleep_ms: int = 50, verbose: bool = True) -> dict:
    """
    Programmatic entry point for canonicalize backfill.

    Returns a dict with stats suitable for JSON response:
      {
        "zip_code":    str,
        "dry_run":     bool,
        "eligible":    int,     # parcels with owner_name
        "already_done": int,    # skipped because canonical row exists
        "processed":   int,     # API calls actually made
        "low_conf":    int,     # confidence < 0.5
        "errors":      list[{"pin": str, "msg": str}],
        "low_conf_rows": list[{"pin": str, "raw": str, "confidence": float}],
        "tokens_in":   int,
        "tokens_out":  int,
        "cost_usd":    float,
        "wall_time_s": float,
        "est_cost_usd": float,  # only populated on dry_run
      }
    """
    def log(msg: str):
        if verbose:
            print(msg, flush=True)

    stats = {
        'zip_code': zip_code, 'dry_run': dry_run,
        'eligible': 0, 'already_done': 0, 'processed': 0,
        'low_conf': 0, 'errors': [], 'low_conf_rows': [],
        'tokens_in': 0, 'tokens_out': 0,
        'cost_usd': 0.0, 'wall_time_s': 0.0, 'est_cost_usd': 0.0,
    }

    log(f"[backfill] target ZIP: {zip_code}")
    log(f"[backfill] model:      {MODEL}")

    supa = get_supabase_client()

    parcels = _fetch_all_parcels(supa, zip_code)
    stats['eligible'] = len(parcels)
    log(f"[backfill] parcels with owner_name: {len(parcels)}")
    if not parcels:
        log("[backfill] nothing to do")
        return stats

    if not force:
        existing = _fetch_existing_pins(supa, zip_code)
        before = len(parcels)
        parcels = [p for p in parcels if p['pin'] not in existing]
        stats['already_done'] = before - len(parcels)
        log(f"[backfill] already canonicalized: {stats['already_done']}")
        log(f"[backfill] remaining to process:  {len(parcels)}")

    if limit:
        parcels = parcels[:limit]
        log(f"[backfill] --limit {limit} applied, processing: {len(parcels)}")

    if dry_run:
        log("[backfill] DRY RUN — sample of what would be processed:")
        for p in parcels[:5]:
            log(f"  {p['pin']}  {p['owner_name']!r}")
        stats['est_cost_usd'] = round(len(parcels) * 0.0005, 4)
        log(f"[backfill] estimated cost: ${stats['est_cost_usd']:.4f}")
        return stats

    if not parcels:
        log("[backfill] nothing to process")
        return stats

    total_tokens_in = 0
    total_tokens_out = 0
    low_conf: list[dict] = []
    errors: list[dict] = []
    start = time.time()
    sleep_s = max(0, sleep_ms) / 1000.0

    for i, p in enumerate(parcels, 1):
        pin = p['pin']
        raw = p['owner_name'] or ''
        result = canonicalize_owner_name(raw)

        total_tokens_in += result.get('_tokens_in', 0) or 0
        total_tokens_out += result.get('_tokens_out', 0) or 0
        if '_error' in result:
            errors.append({'pin': pin, 'msg': result['_error']})

        if result.get('confidence', 0) < 0.5:
            low_conf.append({'pin': pin, 'raw': raw,
                             'confidence': result.get('confidence', 0)})

        try:
            upsert_canonical(supa, pin, result)
        except Exception as e:
            errors.append({'pin': pin, 'msg': f'upsert: {e}'})

        if i % 50 == 0 or i == len(parcels):
            elapsed = time.time() - start
            rate = i / max(elapsed, 0.001)
            eta = (len(parcels) - i) / max(rate, 0.001)
            cost = (total_tokens_in * HAIKU_COST_IN_PER_MTOK +
                    total_tokens_out * HAIKU_COST_OUT_PER_MTOK) / 1_000_000
            log(f"  [{i}/{len(parcels)}] rate={rate:.1f}/s "
                f"eta={eta:.0f}s cost=${cost:.4f} "
                f"low_conf={len(low_conf)} err={len(errors)}")

        if sleep_s:
            time.sleep(sleep_s)

    elapsed = time.time() - start
    cost = (total_tokens_in * HAIKU_COST_IN_PER_MTOK +
            total_tokens_out * HAIKU_COST_OUT_PER_MTOK) / 1_000_000

    stats.update({
        'processed': len(parcels),
        'wall_time_s': round(elapsed, 2),
        'tokens_in': total_tokens_in,
        'tokens_out': total_tokens_out,
        'cost_usd': round(cost, 4),
        'low_conf': len(low_conf),
        'low_conf_rows': low_conf[:50],   # cap response payload
        'errors': errors[:50],
    })

    log("")
    log(f"[backfill] DONE")
    log(f"  processed:    {stats['processed']}")
    log(f"  wall time:    {elapsed:.1f}s ({elapsed/60:.1f} min)")
    log(f"  total cost:   ${cost:.4f}")
    log(f"  low_conf:     {len(low_conf)} (<0.5)")
    log(f"  errors:       {len(errors)}")
    return stats


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

    stats = backfill_zip(
        zip_code=args.zip_code,
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
        sleep_ms=args.sleep_ms,
        verbose=True,
    )

    if stats.get('errors'):
        print()
        print("[backfill] ERRORS:")
        for e in stats['errors'][:20]:
            print(f"  {e['pin']}: {e['msg']}")

    if stats.get('low_conf_rows'):
        print()
        print("[backfill] LOW CONFIDENCE (<0.5) — review these:")
        for r in stats['low_conf_rows'][:20]:
            print(f"  {r['pin']} conf={r['confidence']:.2f}  {r['raw']!r}")

    return 0 if not stats.get('errors') else 1


if __name__ == '__main__':
    sys.exit(main())
