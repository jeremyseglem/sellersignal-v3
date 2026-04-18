"""
run_investigation.py — orchestrator for Option A first-run scope.

Selects:
  - 8 Band 3 (all)
  - 12 Band 2.5 (all)
  - 10 Band 2 ultra ($15M+)
  - 10 Band 2 luxury ($6-15M)
  - 10 Band 2 mid ($2-6M)

Workflow:
  1. Select scope from banded-inventory-verified.json
  2. Dry-run budget check: compute projected searches, query BudgetGuard
  3. If approved, screen all 50 parcels
  4. Identify finalists (top 15 + any escalated)
  5. Deep-investigate finalists
  6. Write investigation fields back to inventory
  7. Record final spend against budget

Idempotent: re-running against cached parcels uses cache, consumes zero budget.
"""
import os
import json
import sys
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from investigation import (
    BudgetGuard, investigate_parcel,
    build_screen_queries, build_deep_queries,
    cache_get, MOCK_MODE, COST_PER_SEARCH,
    MAX_SEARCHES_PER_RUN, MAX_SEARCHES_PER_MONTH,
)

INVENTORY_PATH = '/home/claude/sellersignal_v2/out/banded-inventory-verified.json'
OUT_PATH       = '/home/claude/sellersignal_v2/out/investigation-run.json'


# ─── SCOPE SELECTION ────────────────────────────────────────────────────
def _rank_key(lead):
    """Prefer calibrated_rank_score when present, else rank_score."""
    return lead.get('calibrated_rank_score') or lead.get('rank_score') or 0


def select_option_a_scope(inventory: dict) -> list[dict]:
    """
    Returns 50 leads in the Option A shape:
      8 Band 3 + 12 Band 2.5 + 10 B2 ultra + 10 B2 luxury + 10 B2 mid
    """
    leads = inventory['leads']

    band3    = sorted([L for L in leads if L.get('band') == 3],    key=lambda x: -_rank_key(x))
    band25   = sorted([L for L in leads if L.get('band') == 2.5],  key=lambda x: -_rank_key(x))

    band2 = [L for L in leads if L.get('band') == 2]
    def val(L): return L.get('value') or 0
    b2_ultra  = sorted([L for L in band2 if val(L) >= 15_000_000],            key=lambda x: -_rank_key(x))
    b2_luxury = sorted([L for L in band2 if 6_000_000 <= val(L) < 15_000_000], key=lambda x: -_rank_key(x))
    b2_mid    = sorted([L for L in band2 if 2_000_000 <= val(L) < 6_000_000],  key=lambda x: -_rank_key(x))

    scope = []
    scope += band3[:8]
    scope += band25[:12]
    scope += b2_ultra[:10]
    scope += b2_luxury[:10]
    scope += b2_mid[:10]

    # Dedupe by pin
    seen = set()
    uniq = []
    for L in scope:
        pin = L.get('pin')
        if pin and pin not in seen:
            seen.add(pin)
            uniq.append(L)
    return uniq


def scope_breakdown(scope: list[dict]) -> dict:
    b = defaultdict(int)
    for L in scope:
        band = L.get('band')
        v = L.get('value') or 0
        if band == 3:      b['band_3'] += 1
        elif band == 2.5:  b['band_2.5'] += 1
        elif band == 2:
            if v >= 15_000_000:      b['band_2_ultra'] += 1
            elif v >= 6_000_000:     b['band_2_luxury'] += 1
            elif v >= 2_000_000:     b['band_2_mid'] += 1
            else:                    b['band_2_other'] += 1
        else:              b[f'band_{band}'] += 1
    return dict(b)


# ─── DRY-RUN ESTIMATE ───────────────────────────────────────────────────
def dry_run_estimate(scope: list[dict], deep_finalist_count: int = 15) -> dict:
    """
    Compute projected search count assuming:
      - all scope gets screened
      - deep_finalist_count get deep-investigated
      - cached results are subtracted
    """
    screen_searches = 0
    deep_searches   = 0
    cached_hits     = 0

    for L in scope:
        if cache_get(L, 'screen') is not None:
            cached_hits += 1
        else:
            screen_searches += len(build_screen_queries(L))

    # Top N by rank_key get deep investigation (the real finalist pick is
    # post-screen, but for dry-run we estimate on pre-screen rank order)
    ranked = sorted(scope, key=lambda x: -_rank_key(x))
    for L in ranked[:deep_finalist_count]:
        if cache_get(L, 'deep') is not None:
            cached_hits += 1
        else:
            deep_searches += len(build_deep_queries(L))

    total = screen_searches + deep_searches
    return {
        'scope_size':          len(scope),
        'deep_finalists':      deep_finalist_count,
        'screen_searches':     screen_searches,
        'deep_searches':       deep_searches,
        'total_searches':      total,
        'total_cost_dollars':  round(total * COST_PER_SEARCH, 2),
        'cached_hits':         cached_hits,
    }


# ─── FINALIST PICKER (post-screen) ──────────────────────────────────────
_ESCALATION_PRIORITY = {
    'high_trust_life_event':       0,   # most actionable - promote to call_now
    'high_trust_financial_signal': 1,   # forced-sale signal
    'blocker_conflict':            2,   # needs verification before dropping
    'playbook_candidate':          3,   # top-ranked, deep dive confirms action
    'high_value_unresolved_identity': 4, # luxury sweep, lower priority
    None:                          9,
}


_AUTO_DEEP_SIGNAL_FAMILIES = {
    'financial_stress',       # NOD / trustee sale — always verify person behind the filing
    'failed_sale_attempt',    # expired listing — deep dive confirms the rationality read
    'family_event_cluster',   # cluster leads need full person-intel before acting
    'death_inheritance',      # obit-matched leads always warrant full verification
}


def _forces_deep_investigation(lead: dict) -> bool:
    """Some signal families are high-stakes enough that a 7-search screen
    isn't sufficient — we always want the full dossier before surfacing."""
    sig = lead.get('signal_family')
    band = lead.get('band')
    if sig in _AUTO_DEEP_SIGNAL_FAMILIES: return True
    # Any Band 3 lead going to CALL NOW deserves full investigation
    if band == 3: return True
    # Band 2.5 family clusters awaiting verification
    if band == 2.5: return True
    return False


def pick_finalists(screened: list[tuple], max_finalists: int = 15) -> list[dict]:
    """
    Hard cap at max_finalists regardless of how many escalation flags fire.

    Priority order:
      1. high-trust life event / financial  (most actionable)
      2. blocker conflict                   (needs verification)
      3. high-value unresolved identity     (luxury parcel without profile data)
      4. playbook candidate (top-rank)      (already going on the list)
    Ties broken by calibrated rank.
    """
    def sort_key(item):
        lead, screen_result = item
        esc_reason = screen_result['escalation'].get('reason')
        # Force-deep families get highest priority regardless of screen outcome
        if _forces_deep_investigation(lead):
            return (-1, -_rank_key(lead))
        esc_priority = _ESCALATION_PRIORITY.get(esc_reason, 9)
        return (esc_priority, -_rank_key(lead))

    ordered = sorted(screened, key=sort_key)
    return [lead for lead, _ in ordered[:max_finalists]]


# ─── WRITE-BACK TO INVENTORY ────────────────────────────────────────────
def apply_investigation_fields(lead: dict, screen_result: dict,
                                deep_result: dict = None):
    """Mutate lead in-place: add investigation fields."""
    primary = deep_result or screen_result
    mode = 'deep' if deep_result else 'screen'

    lead['investigation'] = {
        'mode':                mode,
        'investigated_at':     primary['investigated_at'],
        'search_count':        (screen_result['search_count']
                                + (deep_result['search_count'] if deep_result else 0)),
        'signal_count':        primary['signal_count'],
        'signals':             primary['signals'],
        'trust_summary':       primary['trust_summary'],
        'has_life_event':      primary['flags']['has_life_event'],
        'has_financial':       primary['flags']['has_financial'],
        'has_listing_history': primary['flags']['has_listing_history'],
        'has_blocker':         primary['flags']['has_blocker'],
        'identity_resolved':   primary['flags']['identity_resolved'],
        'from_cache':          primary.get('from_cache', False),
        'recommended_action':  primary['recommended_action'],
        'escalation':          screen_result['escalation'],
    }


# ─── MAIN ───────────────────────────────────────────────────────────────
def main():
    started_at = datetime.now()
    print(f'[{started_at:%H:%M:%S}] run_investigation starting')
    print(f'  Mock mode: {MOCK_MODE}')
    print(f'  Per-run cap:   {MAX_SEARCHES_PER_RUN}')
    print(f'  Monthly cap:   {MAX_SEARCHES_PER_MONTH}')
    print(f'  $/search:      ${COST_PER_SEARCH}')

    # Load inventory
    inventory = json.load(open(INVENTORY_PATH))
    leads = inventory['leads']
    print(f'\n  Inventory: {len(leads):,} total leads')

    # Scope selection
    scope = select_option_a_scope(inventory)
    breakdown = scope_breakdown(scope)
    print(f'\n  Scope (Option A): {len(scope)} leads')
    for k in ('band_3', 'band_2.5', 'band_2_ultra', 'band_2_luxury', 'band_2_mid'):
        print(f'    {k:<18} {breakdown.get(k, 0)}')
    for k in sorted(breakdown.keys()):
        if k not in ('band_3', 'band_2.5', 'band_2_ultra', 'band_2_luxury', 'band_2_mid'):
            print(f'    {k:<18} {breakdown.get(k, 0)}  (unexpected — check inventory)')

    # Dry-run estimate
    est = dry_run_estimate(scope, deep_finalist_count=15)
    print(f'\n  ── Dry-run estimate ──')
    print(f'    Screen searches:  {est["screen_searches"]}')
    print(f'    Deep searches:    {est["deep_searches"]}')
    print(f'    Total searches:   {est["total_searches"]}')
    print(f'    Cached hits:      {est["cached_hits"]}')
    print(f'    Projected cost:   ${est["total_cost_dollars"]}')

    # Budget guard check
    guard = BudgetGuard()
    approval = guard.estimate_run_cost(est['total_searches'])
    print(f'\n  ── Budget approval ──')
    print(f'    Projected searches:         {approval["projected_searches"]}')
    print(f'    Month used before:          {approval["month_used_before"]}')
    print(f'    Month used after (if run):  {approval["month_used_after_if_approved"]}')
    print(f'    Remaining monthly budget:   {approval["month_remaining_budget"]}')
    print(f'    Approved:                   {approval["approved"]}')
    if not approval['approved']:
        print(f'    Reasons for rejection:')
        for r in approval['reasons']:
            print(f'      · {r}')
        print('\n  ABORTED — budget would be exceeded. Exiting without spending.')
        sys.exit(1)

    # ─── Screening pass ──
    print(f'\n[{datetime.now():%H:%M:%S}] Screening {len(scope)} leads...')
    ranked_scope = sorted(scope, key=lambda x: -_rank_key(x))
    screened = []
    live_searches = 0

    for i, lead in enumerate(ranked_scope, 1):
        provisional_rank = i  # cheap rank by score within scope
        result = investigate_parcel(lead, mode='screen', provisional_rank=provisional_rank, use_cache=True)
        screened.append((lead, result))
        if not result['from_cache']:
            live_searches += result['search_count']

    # ─── Finalist selection ──
    finalists = pick_finalists(screened, max_finalists=15)
    print(f'\n[{datetime.now():%H:%M:%S}] Finalists selected: {len(finalists)} (of 15 max)')
    for L in finalists:
        esc = next((r for (l, r) in screened if l.get('pin') == L.get('pin')), None)
        reason = esc['escalation']['reason'] if esc else '?'
        pin = L.get('pin') or ''
        print(f'    {pin:<11} {(L.get("address") or "(no addr)")[:30]:<30} '
              f'${(L.get("value") or 0)/1e6:>5.1f}M  {reason}')

    # ─── Deep investigation pass ──
    # Mid-run budget re-check: now that we know finalist count and each
    # finalist's deep-query size (may differ person vs entity), compute
    # actual deep spend and abort if it pushes us over the per-run or
    # monthly cap.
    projected_deep_spend = 0
    for L in finalists:
        if cache_get(L, 'deep') is None:
            projected_deep_spend += len(build_deep_queries(L))

    projected_total_with_deep = live_searches + projected_deep_spend
    if projected_total_with_deep > MAX_SEARCHES_PER_RUN:
        print(f'\n  MID-RUN BUDGET ABORT')
        print(f'    Screen spend so far:      {live_searches}')
        print(f'    Projected deep spend:     {projected_deep_spend}')
        print(f'    Projected run total:      {projected_total_with_deep}')
        print(f'    Per-run cap:              {MAX_SEARCHES_PER_RUN}')
        print(f'    Deep pass SKIPPED. Write-back will use screen-only results.')
        deep_results = {}
    else:
        mid_run_guard = BudgetGuard()
        mid_run_guard.record_searches(0)  # trigger month rollover check
        month_after = mid_run_guard.state['searches_this_month'] + projected_total_with_deep
        if month_after > MAX_SEARCHES_PER_MONTH:
            print(f'\n  MID-RUN MONTHLY BUDGET ABORT')
            print(f'    Month used so far:        {mid_run_guard.state["searches_this_month"]}')
            print(f'    Projected run total:      {projected_total_with_deep}')
            print(f'    Would land at:            {month_after}')
            print(f'    Monthly cap:              {MAX_SEARCHES_PER_MONTH}')
            print(f'    Deep pass SKIPPED.')
            deep_results = {}
        else:
            print(f'\n[{datetime.now():%H:%M:%S}] Deep-investigating finalists...')
            print(f'    Projected deep spend: {projected_deep_spend} searches')
            deep_results = {}
            for L in finalists:
                result = investigate_parcel(L, mode='deep', use_cache=True)
                deep_results[L.get('pin')] = result
                if not result['from_cache']:
                    live_searches += result['search_count']

    # ─── Write back to inventory ──
    print(f'\n[{datetime.now():%H:%M:%S}] Writing investigation fields back to inventory...')
    pin_to_screen = {L.get('pin'): r for L, r in screened}
    n_updated = 0
    for lead in inventory['leads']:
        pin = lead.get('pin')
        if pin in pin_to_screen:
            apply_investigation_fields(lead, pin_to_screen[pin], deep_results.get(pin))
            n_updated += 1
    with open(INVENTORY_PATH, 'w') as f:
        json.dump(inventory, f, indent=2, default=str)
    print(f'    Updated {n_updated} leads')

    # ─── Record spend ──
    if live_searches > 0:
        guard.record_searches(live_searches)
        print(f'\n[{datetime.now():%H:%M:%S}] Recorded {live_searches} live searches against budget')
    else:
        print(f'\n[{datetime.now():%H:%M:%S}] 0 live searches (all cached)')

    # ─── Summary ──
    by_rec = defaultdict(int)
    by_flag = defaultdict(int)
    for L, r in screened:
        final_r = deep_results.get(L.get('pin'), r)
        by_rec[final_r['recommended_action']['category']] += 1
        for k, v in final_r['flags'].items():
            if v: by_flag[k] += 1

    summary = {
        'started_at':       started_at.isoformat(),
        'finished_at':      datetime.now().isoformat(),
        'mock_mode':        MOCK_MODE,
        'scope_size':       len(scope),
        'scope_breakdown':  breakdown,
        'finalists':        len(finalists),
        'live_searches':    live_searches,
        'estimated_cost':   round(live_searches * COST_PER_SEARCH, 2),
        'budget_after':     BudgetGuard().state,
        'recommendations':  dict(by_rec),
        'flag_counts':      dict(by_flag),
    }

    with open(OUT_PATH, 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f'\n══════════════════════════════════════════════')
    print(f'  RUN COMPLETE')
    print(f'══════════════════════════════════════════════')
    print(f'  Scope:            {len(scope)} leads')
    print(f'  Finalists deep:   {len(finalists)}')
    print(f'  Live searches:    {live_searches}')
    print(f'  Actual cost:      ${live_searches * COST_PER_SEARCH:.2f}')
    print(f'\n  Recommendations:')
    for k, v in sorted(by_rec.items(), key=lambda x: -x[1]):
        print(f'    {k:<12} {v}')
    print(f'\n  Flags fired:')
    for k, v in sorted(by_flag.items(), key=lambda x: -x[1]):
        print(f'    {k:<22} {v}')
    print(f'\n  Output: {OUT_PATH}')


if __name__ == '__main__':
    main()
