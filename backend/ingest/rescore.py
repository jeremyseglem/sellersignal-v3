"""
Rescore — re-run recommend_action on existing investigations using cached signals.

When the pressure-engine logic changes (e.g., new archetype→family mapping,
loosened trust tiers), existing investigations in Supabase still carry the
action_category/action_pressure/action_reason from the PREVIOUS scoring
pass. This CLI re-runs recommend_action on every investigation in a ZIP
using the stored signals, and updates the action_* fields in place.

Zero SerpAPI cost. Reads investigations_v3.signals (JSONB), pulls the
matching parcel row for signal_family + band context, calls the current
recommend_action, writes back.

Usage:
  python -m backend.ingest.rescore 98004
  python -m backend.ingest.rescore 98004 --dry-run   # show deltas, don't write
"""
from __future__ import annotations
import argparse
import sys
import json
from collections import Counter
from typing import Optional

from backend.api.db import get_supabase_client
from backend.investigation import recommend_action


def _fetch_all(supa, table: str, zip_code: str, page: int = 1000) -> list[dict]:
    out = []
    offset = 0
    while True:
        res = (supa.table(table)
               .select('*')
               .eq('zip_code', zip_code)
               .range(offset, offset + page - 1)
               .execute())
        batch = res.data or []
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if offset > 100000:
            break
    return out


def rescore_zip(zip_code: str, dry_run: bool = False) -> dict:
    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured")

    print(f"\n═══ Rescoring ZIP {zip_code} ═══")
    print(f"  dry_run: {dry_run}")

    parcels = _fetch_all(supa, 'parcels_v3', zip_code)
    parcel_by_pin = {p['pin']: p for p in parcels}
    print(f"  Parcels loaded: {len(parcel_by_pin)}")

    invs = _fetch_all(supa, 'investigations_v3', zip_code)
    print(f"  Investigations to rescore: {len(invs)}")
    if not invs:
        return {'rescored': 0, 'changed': 0, 'deltas': []}

    before_counter = Counter()
    after_counter  = Counter()
    deltas = []
    changed = 0

    for inv in invs:
        pin = inv['pin']
        parcel = parcel_by_pin.get(pin)
        if not parcel:
            # Investigation without a parcel — shouldn't happen with FK
            continue

        before_counter[(inv.get('action_category'), inv.get('action_pressure'))] += 1

        signals = inv.get('signals') or []
        # Pass only the fields recommend_action reads
        parcel_ctx = {
            'signal_family': parcel.get('signal_family'),
            'band':          parcel.get('band'),
        }
        rec = recommend_action(parcel_ctx, signals)

        new_cat  = rec.get('category')
        new_pres = rec.get('pressure')
        old_cat  = inv.get('action_category')
        old_pres = inv.get('action_pressure')

        after_counter[(new_cat, new_pres)] += 1

        if (new_cat, new_pres) != (old_cat, old_pres) or rec.get('reason') != inv.get('action_reason'):
            changed += 1
            deltas.append({
                'pin':     pin,
                'address': parcel.get('address'),
                'band':    parcel.get('band'),
                'family':  parcel.get('signal_family'),
                'before':  {'cat': old_cat, 'pressure': old_pres, 'reason': inv.get('action_reason')},
                'after':   {'cat': new_cat, 'pressure': new_pres, 'reason': rec.get('reason')},
            })

            if not dry_run:
                (supa.table('investigations_v3')
                 .update({
                     'action_category':  new_cat,
                     'action_tone':      rec.get('tone'),
                     'action_pressure':  new_pres,
                     'action_reason':    rec.get('reason'),
                     'action_next_step': rec.get('next_step'),
                 })
                 .eq('pin', pin)
                 .execute())

    print(f"\n  Before distribution:")
    for (cat, pres), n in sorted(before_counter.items(), key=lambda x: (-(x[0][1] or 0), -x[1])):
        print(f"    {str(cat):<12} pressure={pres}  n={n}")
    print(f"\n  After distribution:")
    for (cat, pres), n in sorted(after_counter.items(), key=lambda x: (-(x[0][1] or 0), -x[1])):
        print(f"    {str(cat):<12} pressure={pres}  n={n}")

    print(f"\n  Changed: {changed} / {len(invs)}")

    # Show promotions (hold -> something actionable)
    promos = [d for d in deltas
              if (d['before']['cat'] == 'hold' and d['after']['cat'] != 'hold')]
    if promos:
        print(f"\n  Promotions (hold -> actionable):")
        for d in promos[:20]:
            print(f"    {d['address']:30} band={d['band']} "
                  f"family={d['family']:22} -> {d['after']['cat']} "
                  f"pressure={d['after']['pressure']} ({d['after']['reason']})")
        if len(promos) > 20:
            print(f"    ... and {len(promos) - 20} more")

    # Show demotions (actionable -> hold)
    demos = [d for d in deltas
             if (d['before']['cat'] != 'hold' and d['after']['cat'] == 'hold')]
    if demos:
        print(f"\n  ⚠ Demotions (actionable -> hold):")
        for d in demos:
            print(f"    {d['address']:30} {d['before']['cat']} pressure={d['before']['pressure']} -> hold")

    return {
        'rescored': len(invs),
        'changed':  changed,
        'promotions': len(promos),
        'demotions':  len(demos),
    }


def main():
    p = argparse.ArgumentParser(description="Re-run recommend_action on cached investigations")
    p.add_argument('zip_code')
    p.add_argument('--dry-run', action='store_true',
                   help="Show deltas without writing back")
    args = p.parse_args()

    try:
        result = rescore_zip(args.zip_code, dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"\n  Summary:")
    print(f"    Rescored:   {result['rescored']}")
    print(f"    Changed:    {result['changed']}")
    print(f"    Promotions: {result.get('promotions', 0)}")
    print(f"    Demotions:  {result.get('demotions', 0)}")
    if args.dry_run:
        print(f"\n  (dry-run — no rows were modified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
