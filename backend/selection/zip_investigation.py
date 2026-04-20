"""
Per-ZIP investigation runner.

Wraps backend/investigation/* for the ZIP build lifecycle. Given a ZIP
that's been ingested + classified + banded, selects the Option A scope
(8 B3 + 12 B2.5 + 30 B2 tier-balanced), screens all, deep-investigates
top finalists, writes results to investigations_v3.

Key differences from the sandbox orchestrator:
  - Reads parcels from Supabase instead of flat-file JSON
  - Writes investigations to Supabase (investigations_v3) instead of
    mutating an inventory JSON
  - Uses persistence.py for cache + budget instead of flat files
  - Respects the pressure-scored recommend_action in investigation module

Cost expectations per fresh ZIP:
  Screen: 50 parcels × 7 searches = 350 searches = ~$5.25
  Deep:   15 finalists × ~22 searches = ~330 searches = ~$4.95
  Total:  ~680 searches = ~$10.20

All budget gates enforced via persistence.estimate_run_cost before spending.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional

from backend.api.db import get_supabase_client
from backend.investigation import persistence


# ============================================================================
# Scope selection
# ============================================================================

def select_option_a_scope(parcels: list[dict]) -> list[dict]:
    """
    Select scope from a ZIP's parcels.

    Philosophy: the app finds sellers, not luxury sellers. Band assignment
    is the pressure filter (structural features: owner type, tenure,
    absentee, archetype). Within the Band 2+ cohort we do NOT filter by
    raw property value — a $400K home with an LLC owner and short tenure
    has the same structural pressure as a $15M home with the same pattern.

    Selection rule:
      - All Band 3 parcels (by value desc)
      - All Band 2.5 parcels (by value desc)
      - All Band 2 parcels (by value desc)
      - Deduplicated by pin

    Rationale for keeping Band 2+ filter:
      - Band 0 / Band 1 parcels are structurally low-pressure (long-term
        owner-occupied with no trust/LLC/absentee markers). Investigating
        them burns SerpAPI budget for rare yield. If beta evidence shows
        we're missing sellers in those bands, we can expand later.
      - Band is NOT a value proxy — a $600K Band-3 parcel (short-tenure
        LLC) beats a $10M Band-0 parcel (30-year individual owner) every
        time on seller likelihood. That's exactly what we want.

    No cap — returns every Band 2+ parcel. Caller controls spending via
    max_finalists for the deep pass and the monthly budget gate.

    For a ZIP like 98004 this typically surfaces 200-500 parcels. For
    broader markets (Charlotte suburbs, Bozeman) it may be more.
    """
    def val(p): return p.get('total_value') or 0

    b3  = sorted([p for p in parcels if p.get('band') == 3],   key=lambda x: -val(x))
    b25 = sorted([p for p in parcels if p.get('band') == 2.5], key=lambda x: -val(x))
    b2  = sorted([p for p in parcels if p.get('band') == 2],   key=lambda x: -val(x))

    scope = b3 + b25 + b2
    seen = set(); uniq = []
    for p in scope:
        pin = p.get('pin')
        if pin and pin not in seen:
            seen.add(pin); uniq.append(p)
    return uniq


# ============================================================================
# Run coordinator
# ============================================================================

def run_investigation_for_zip(
    zip_code: str,
    dry_run: bool = False,
    max_finalists: int = 15,
) -> dict:
    """
    Run investigation for a ZIP.

    Returns summary dict:
        {
          'dry_run': bool,
          'approved': bool,
          'scope_size': int,
          'finalists': int,
          'screen_searches': int,
          'deep_searches': int,
          'total_searches': int,
          'cost_usd': float,
          'actions': {'call_now': N, 'build_now': N, 'hold': N, 'avoid': N},
          'reasons': list[str],     # if not approved
        }
    """
    supa = get_supabase_client()
    if not supa:
        return {'error': 'Supabase not configured', 'approved': False}

    # ── Load parcels for this ZIP ──
    parcels_res = (supa.table('parcels_v3')
                   .select('*')
                   .eq('zip_code', zip_code)
                   .execute())
    parcels = parcels_res.data or []
    if not parcels:
        return {'error': 'No parcels found', 'approved': False, 'zip': zip_code}

    # ── Select scope ──
    scope = select_option_a_scope(parcels)
    if not scope:
        return {
            'error': 'No parcels met Option A criteria (need Band 2/2.5/3 leads)',
            'approved': False,
            'zip': zip_code,
            'parcels_in_zip': len(parcels),
        }

    # Import investigation module here (avoids circular + skips if not ready)
    from backend.investigation import (
        build_screen_queries, build_deep_queries,
        investigate_parcel, recommend_action,
    )

    # ── Dry-run: estimate cost without spending ──
    # Check cache for each parcel to avoid double-counting cached work
    screen_searches_needed = 0
    for p in scope:
        cached = persistence.cache_get(p, 'screen')
        if cached is None:
            screen_searches_needed += len(build_screen_queries(p))

    # Rough deep estimate: top 15 by rank, ~22 searches each if not cached
    # Actual finalist selection happens after screening
    deep_estimate = max_finalists * 22
    total_estimate = screen_searches_needed + deep_estimate

    budget_check = persistence.estimate_run_cost(total_estimate)
    if not budget_check['approved']:
        return {
            'dry_run':             True,
            'approved':            False,
            'scope_size':          len(scope),
            'projected_searches':  total_estimate,
            'projected_cost_usd':  budget_check['projected_cost_usd'],
            'reasons':             budget_check['reasons'],
            'zip':                 zip_code,
        }

    if dry_run:
        return {
            'dry_run':             True,
            'approved':            True,
            'scope_size':          len(scope),
            'projected_searches':  total_estimate,
            'projected_cost_usd':  budget_check['projected_cost_usd'],
            'screen_searches_est': screen_searches_needed,
            'deep_searches_est':   deep_estimate,
            'current_month_usage': budget_check['current_month_usage'],
            'zip':                 zip_code,
        }

    # ── Real run: screen pass ──
    total_live_searches = 0
    screened = []
    for i, parcel in enumerate(scope, 1):
        result = investigate_parcel(parcel, mode='screen', provisional_rank=i,
                                     use_cache=True)
        screened.append((parcel, result))
        if not result.get('from_cache'):
            total_live_searches += result.get('search_count', 0)
        # Write screen result to Supabase via persistence module
        persistence.cache_put(parcel, 'screen', result)

    # ── Rank finalists for deep pass ──
    def _rank_key(p):
        # Prefer Band 3 > Band 2.5 > Band 2 + value tiebreaker
        band = p.get('band') or 0
        val = p.get('total_value') or 0
        return (band, val / 1_000_000)

    finalists = sorted(
        [p for p, _ in screened],
        key=lambda p: _rank_key(p),
        reverse=True,
    )[:max_finalists]

    # ── Deep pass ──
    deep_results = {}
    for parcel in finalists:
        result = investigate_parcel(parcel, mode='deep', use_cache=True)
        deep_results[parcel['pin']] = result
        if not result.get('from_cache'):
            total_live_searches += result.get('search_count', 0)
        persistence.cache_put(parcel, 'deep', result)

    # ── Record spend ──
    persistence.record_searches(total_live_searches)

    # ── Summarize actions ──
    from collections import Counter
    action_counts = Counter()
    for result in deep_results.values():
        rec = result.get('recommended_action') or {}
        action_counts[rec.get('category', 'hold')] += 1

    investigated_count = len(deep_results)
    call_now_count = action_counts.get('call_now', 0)

    # ── Stamp coverage ──
    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        'investigated_count':      investigated_count,
        'current_call_now_count':  call_now_count,
        'updated_at':              now_iso,
    }
    # Only set first_investigation_at if not already set
    cov = (supa.table('zip_coverage_v3')
           .select('first_investigation_at')
           .eq('zip_code', zip_code)
           .maybe_single()
           .execute())
    if not (cov and cov.data and cov.data.get('first_investigation_at')):
        update['first_investigation_at'] = now_iso
    supa.table('zip_coverage_v3').update(update).eq('zip_code', zip_code).execute()

    return {
        'dry_run':            False,
        'approved':           True,
        'scope_size':         len(scope),
        'finalists':          len(finalists),
        'total_searches':     total_live_searches,
        'cost_usd':           round(total_live_searches * 0.015, 2),
        'actions':            dict(action_counts),
        'zip':                zip_code,
    }
