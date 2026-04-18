"""
persistence.py — Supabase-backed replacement for flat-file cache + budget state.

The sandbox investigation module used flat-file storage:
  - out/investigation/cache/*.json   (per-parcel signal cache)
  - out/investigation/budget_state.json  (monthly spend tracker)

Railway containers are ephemeral — flat files are wiped on every redeploy.
This module replaces both with Supabase tables (investigations_v3 and
serpapi_budget_v3) so state persists across deploys and scales across
multiple worker instances.

Drop-in replacement for investigation.cache_* and BudgetGuard.state methods.
"""
from __future__ import annotations
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.api.db import get_supabase_client


# ============================================================================
# CACHE — replaces investigation.cache_get/cache_put/cache_invalidate
# ============================================================================

CACHE_TTL_DAYS = 90


def _cache_key(parcel: dict, mode: str) -> str:
    """
    Deterministic cache key for a parcel + investigation mode.
    Uses pin as the primary identifier — if pin is stable, signals are stable
    (assuming no ownership change, which should trigger invalidation separately).
    """
    pin = parcel.get('pin') or parcel.get('id') or parcel.get('parcel_id')
    if not pin:
        # Fallback: hash of address + owner_name (less stable but usable)
        addr = (parcel.get('address') or '').upper()
        owner = (parcel.get('owner_name') or '').upper()
        pin = hashlib.md5(f"{addr}|{owner}".encode()).hexdigest()[:16]
    return f"{pin}:{mode}"


def cache_get(parcel: dict, mode: str) -> Optional[dict]:
    """
    Retrieve cached investigation result, or None if not cached / expired.

    Args:
        parcel: parcel dict (must have 'pin' or equivalent)
        mode: 'screen' | 'deep'

    Returns:
        Cached investigation result dict, or None.
    """
    supa = get_supabase_client()
    if not supa: return None

    pin = parcel.get('pin') or parcel.get('id') or parcel.get('parcel_id')
    if not pin: return None

    try:
        result = (supa.table('investigations_v3')
                  .select('*')
                  .eq('pin', pin)
                  .eq('mode', mode)
                  .maybe_single()
                  .execute())
        row = result.data if result else None
        if not row: return None

        # Check TTL
        expires = row.get('expires_at')
        if expires:
            exp_dt = datetime.fromisoformat(expires.replace('Z', '+00:00'))
            if exp_dt < datetime.now(timezone.utc):
                return None  # expired

        # Return in the shape investigation.py expects
        return {
            'mode':              row['mode'],
            'signals':           row.get('signals') or [],
            'signal_count':      row.get('signal_count', 0),
            'has_life_event':    row.get('has_life_event', False),
            'has_financial':     row.get('has_financial', False),
            'has_blocker':       row.get('has_blocker', False),
            'identity_resolved': row.get('identity_resolved', False),
            'trust_summary':     row.get('trust_summary') or {'high': 0, 'medium': 0, 'low': 0},
            'recommended_action': {
                'category':  row.get('action_category'),
                'tone':      row.get('action_tone'),
                'pressure':  row.get('action_pressure'),
                'reason':    row.get('action_reason'),
                'next_step': row.get('action_next_step'),
            } if row.get('action_category') else None,
            'search_count':      row.get('searches_used', 0),
            'from_cache':        True,
            'cached_at':         row.get('investigated_at'),
        }
    except Exception as e:
        print(f'[cache_get] error: {e}')
        return None


def cache_put(parcel: dict, mode: str, result: dict) -> bool:
    """
    Store investigation result in Supabase with 90-day TTL.

    Args:
        parcel: parcel dict
        mode: 'screen' | 'deep'
        result: investigation result dict (what investigate_parcel returned)

    Returns:
        True if upsert succeeded.
    """
    supa = get_supabase_client()
    if not supa: return False

    pin = parcel.get('pin') or parcel.get('id') or parcel.get('parcel_id')
    if not pin:
        print('[cache_put] missing pin; skipping')
        return False

    zip_code = parcel.get('zip') or parcel.get('zip_code') or ''
    rec = (result.get('recommended_action') or {})
    flags = result.get('flags') or {}
    # Handle both flat and nested flag shapes
    has_life_event = result.get('has_life_event', flags.get('has_life_event', False))
    has_financial  = result.get('has_financial',  flags.get('has_financial', False))
    has_blocker    = result.get('has_blocker',    flags.get('has_blocker', False))
    identity_resolved = result.get('identity_resolved', flags.get('identity_resolved', False))

    row = {
        'pin':                pin,
        'zip_code':           zip_code,
        'mode':               mode,
        'signals':            result.get('signals', []),
        'signal_count':       result.get('signal_count', len(result.get('signals', []))),
        'has_life_event':     has_life_event,
        'has_financial':      has_financial,
        'has_blocker':        has_blocker,
        'identity_resolved':  identity_resolved,
        'trust_summary':      result.get('trust_summary', {'high': 0, 'medium': 0, 'low': 0}),
        'action_category':    rec.get('category'),
        'action_tone':        rec.get('tone'),
        'action_pressure':    rec.get('pressure'),
        'action_reason':      rec.get('reason'),
        'action_next_step':   rec.get('next_step'),
        'searches_used':      result.get('search_count', 0),
        'cost_usd':           result.get('search_count', 0) * 0.015,
        'investigated_at':    datetime.now(timezone.utc).isoformat(),
        'expires_at':         (datetime.now(timezone.utc) + timedelta(days=CACHE_TTL_DAYS)).isoformat(),
    }

    try:
        supa.table('investigations_v3').upsert(row, on_conflict='pin').execute()
        return True
    except Exception as e:
        print(f'[cache_put] error: {e}')
        return False


def cache_invalidate(pin: str, mode: Optional[str] = None) -> int:
    """
    Invalidate cache entries for a parcel. If mode given, only that mode.
    Used when a new event fires (new NOD, new obit, ownership change) and
    we want the next investigation run to re-fetch signals.

    Returns number of rows deleted.
    """
    supa = get_supabase_client()
    if not supa: return 0

    try:
        q = supa.table('investigations_v3').delete().eq('pin', pin)
        if mode:
            q = q.eq('mode', mode)
        result = q.execute()
        return len(result.data or [])
    except Exception as e:
        print(f'[cache_invalidate] error: {e}')
        return 0


# ============================================================================
# BUDGET STATE — replaces investigation.BudgetGuard flat-file state
# ============================================================================

MAX_SEARCHES_PER_MONTH = int(os.environ.get('MAX_SEARCHES_PER_MONTH', '25000'))
MAX_SEARCHES_PER_RUN   = int(os.environ.get('MAX_SEARCHES_PER_RUN',   '800'))
COST_PER_SEARCH        = 0.015  # SerpAPI Big Data Plan pricing


def _current_month_key() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m')


def get_budget_state() -> dict:
    """
    Read current month's budget state from Supabase.
    Creates a zero row for the current month if none exists.
    """
    supa = get_supabase_client()
    if not supa:
        # Fallback for dev without Supabase
        return {
            'month_key':            _current_month_key(),
            'searches_this_month':  0,
            'cost_this_month_usd':  0.0,
            'monthly_cap':          MAX_SEARCHES_PER_MONTH,
            'remaining_this_month': MAX_SEARCHES_PER_MONTH,
        }

    month_key = _current_month_key()
    try:
        result = (supa.table('serpapi_budget_v3')
                  .select('*')
                  .eq('month_key', month_key)
                  .maybe_single()
                  .execute())
        row = result.data if result else None

        if not row:
            # First use this month — insert zero row
            supa.table('serpapi_budget_v3').insert({
                'month_key': month_key,
                'searches_used': 0,
                'cost_usd': 0,
            }).execute()
            searches_used = 0
            cost_usd = 0.0
        else:
            searches_used = row.get('searches_used', 0)
            cost_usd = float(row.get('cost_usd', 0))

        return {
            'month_key':            month_key,
            'searches_this_month':  searches_used,
            'cost_this_month_usd':  cost_usd,
            'monthly_cap':          MAX_SEARCHES_PER_MONTH,
            'remaining_this_month': max(0, MAX_SEARCHES_PER_MONTH - searches_used),
        }
    except Exception as e:
        print(f'[get_budget_state] error: {e}')
        # Fail open with reasonable defaults, log the error
        return {
            'month_key':            month_key,
            'searches_this_month':  0,
            'cost_this_month_usd':  0.0,
            'monthly_cap':          MAX_SEARCHES_PER_MONTH,
            'remaining_this_month': MAX_SEARCHES_PER_MONTH,
            '_error': str(e),
        }


def record_searches(n: int) -> dict:
    """
    Record n searches against the current month's budget.
    Used by the investigation orchestrator after a run completes.

    Returns the updated budget state.
    """
    supa = get_supabase_client()
    if not supa or n <= 0:
        return get_budget_state()

    month_key = _current_month_key()
    try:
        # Get current state
        current = get_budget_state()
        new_searches = current['searches_this_month'] + n
        new_cost = current['cost_this_month_usd'] + n * COST_PER_SEARCH

        supa.table('serpapi_budget_v3').upsert({
            'month_key':      month_key,
            'searches_used':  new_searches,
            'cost_usd':       round(new_cost, 4),
            'updated_at':     datetime.now(timezone.utc).isoformat(),
        }, on_conflict='month_key').execute()

        return get_budget_state()
    except Exception as e:
        print(f'[record_searches] error: {e}')
        return get_budget_state()


def estimate_run_cost(projected_searches: int) -> dict:
    """
    Dry-run budget check — does this run fit in both per-run and monthly caps?

    Returns:
        {
            'approved': bool,
            'reasons': list[str],    # populated when NOT approved
            'projected_searches': int,
            'projected_cost_usd': float,
            'current_month_usage': int,
            'would_be_month_total': int,
        }
    """
    state = get_budget_state()
    would_be = state['searches_this_month'] + projected_searches

    reasons = []
    if projected_searches > MAX_SEARCHES_PER_RUN:
        reasons.append(
            f'Projected {projected_searches} searches exceeds per-run cap '
            f'of {MAX_SEARCHES_PER_RUN}'
        )
    if would_be > MAX_SEARCHES_PER_MONTH:
        reasons.append(
            f'Projected month total {would_be} would exceed monthly cap '
            f'of {MAX_SEARCHES_PER_MONTH} (current month usage: '
            f'{state["searches_this_month"]})'
        )

    return {
        'approved':              len(reasons) == 0,
        'reasons':               reasons,
        'projected_searches':    projected_searches,
        'projected_cost_usd':    round(projected_searches * COST_PER_SEARCH, 2),
        'current_month_usage':   state['searches_this_month'],
        'would_be_month_total':  would_be,
        'monthly_cap':           MAX_SEARCHES_PER_MONTH,
        'per_run_cap':           MAX_SEARCHES_PER_RUN,
    }


# ============================================================================
# SELF-TEST
# ============================================================================

if __name__ == '__main__':
    # These tests require Supabase env to be set. Without it, methods will
    # return None/defaults (fail-open behavior for dev).
    print("=== Budget state ===")
    state = get_budget_state()
    for k, v in state.items():
        print(f"  {k}: {v}")

    print("\n=== Dry-run cost estimate (500 searches) ===")
    est = estimate_run_cost(500)
    for k, v in est.items():
        print(f"  {k}: {v}")

    print("\n=== Dry-run cost estimate (1000 searches — should fail per-run cap) ===")
    est = estimate_run_cost(1000)
    for k, v in est.items():
        print(f"  {k}: {v}")
