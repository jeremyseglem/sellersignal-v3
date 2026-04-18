"""
weekly_selector.py — Deterministic weekly playbook generation.

Inputs:
  banded-inventory-verified.json   — the scored + banded inventory
  playbook-history.json            — prior weeks' picks (for dedup)

Output:
  this-weeks-picks.json            — 10 picks with section, copy, and metadata
  this-weeks-plays-auto.pdf        — rendered operator playbook

Rules (per critic spec):
  CALL NOW         = top 5 Band 3 by rank_score (no mixing, no overrides)
  BUILD NOW        = 3 Band 2 leads with tier mix (1 ultra + 1 luxury + 1 mid, then fill)
  STRATEGIC HOLDS  = top 2 remaining Band 2 by (timeline DESC, inevitability DESC)

Filters applied before selection:
  - Skip if pin was in any of the last 4 weeks' picks (unless band upgraded)
  - Skip if owner base key already used in THIS week
"""
import json, os, re
from datetime import datetime
from collections import OrderedDict

INV_PATH = '/home/claude/sellersignal_v2/out/banded-inventory-verified.json'
HIST_PATH = '/home/claude/sellersignal_v2/out/playbook-history.json'
PICKS_PATH = '/home/claude/sellersignal_v2/out/this-weeks-picks.json'

# Value tier bands (per critic spec)
TIER_ULTRA  = (15_000_000, 10**12)
TIER_LUXURY = (6_000_000, 15_000_000)
TIER_MID    = (2_000_000, 6_000_000)

# Copy templates by signal family
# Each template generates 3 lines: happening / why / action
COPY_TEMPLATES = {
    # Band 3 — observed events
    ('financial_stress', 'trustee_sale'): {
        'happening': "Trustee sale scheduled. Time pressure is real.",
        'why':       "Owner likely needs a clean exit before auction.",
        'action':    "Call this week. Position as pre-auction solution.",
    },
    ('financial_stress', 'nod'): {
        'happening': "Notice of Default filed. Still inside cure window.",
        'why':       "Seller has time, but pressure is building.",
        'action':    "Reach out this week. Offer pre-foreclosure sale path.",
    },
    ('investor_disposition', 'overdue'): {
        'happening': "Investor holding past typical exit window.",
        'why':       "Numbers-driven decision, not emotional.",
        'action':    "Contact with comps and exit scenarios. Keep it analytical.",
    },
    ('investor_disposition', None): {
        'happening': "Investor-held asset approaching disposition window.",
        'why':       "Likely rational exit decision inbound.",
        'action':    "Direct outreach with cap-rate framing.",
    },
    ('failed_sale_attempt', 'caution'): {
        'happening': "Listing expired after long market time.",
        'why':       "Seller didn't fail — timing and strategy did.",
        'action':    "Offer relaunch strategy, not price cuts.",
    },
    ('failed_sale_attempt', None): {
        'happening': "Expired listing with professional LLC owner.",
        'why':       "Rational seller, likely open to a different approach.",
        'action':    "Direct outreach with alternative buyer strategy.",
    },

    # Band 2 — inference
    ('trust_aging', None): {
        'happening': "Trust-held asset, grantor in late-life stage.",
        'why':       "Decision window is biological, not market-driven.",
        'action':    "Identify connector within 2 weeks; map estate attorneys; do not cold call.",
    },
    ('silent_transition', None): {
        'happening': "Long individual tenure. Quiet ownership pattern.",
        'why':       "Transition likely private, not MLS-driven.",
        'action':    "Work neighbor intros within 30 days; no mass mail; target one connection per quarter.",
    },
    ('dormant_absentee', None): {
        'happening': "Dormant ownership with out-of-area mailing.",
        'why':       "Owner disengaged from local market. Rational sell probable.",
        'action':    "Find the local property manager or family attorney; route through them in 30 days.",
    },
    ('family_event_cluster', None): {
        'happening': "Multi-property family cluster pending obit verification.",
        'why':       "If confirmed, represents a portfolio-level event.",
        'action':    "30-min verification task: confirm obit survivor names match owners.",
    },
}

# Section-specific overlay for STRATEGIC HOLDS — different voice than active cultivation.
# Long-cycle, low-urgency framing.
STRATEGIC_HOLDS_TEMPLATES = {
    'trust_aging': {
        'happening': "Trust-held asset with multi-year horizon.",
        'why':       "Predictable long-term disposition.",
        'action':    "Annual touchpoint via estate-planning community; no direct contact this cycle.",
    },
    'silent_transition': {
        'happening': "Stable long-tenure ownership.",
        'why':       "No immediate signal, but strong long-term likelihood.",
        'action':    "Quarterly neighborhood presence; target one referral network introduction per year.",
    },
    'dormant_absentee': {
        'happening': "Dormant ownership pattern with long tenure.",
        'why':       "Not urgent, but highly predictable over time.",
        'action':    "Annual touchpoint via estate-planning community; no direct contact this cycle.",
    },
}

# Property-specific overrides (preserves hand-crafted copy for famous parcels)
PROPERTY_OVERRIDES = {
    '923 EVERGREEN POINT RD': {
        'happening': "Ultra-high-value estate with long tenure and professional handling.",
        'why':       "Will transact privately through attorneys, not publicly.",
        'action':    "Build top-3 estate attorney relationships this quarter; target portfolio-level intros.",
    },
    '101 84TH AVE NE': {
        'happening': "Long-term wealth asset tied to structured planning.",
        'why':       "Disposition will be rational and controlled.",
        'action':    "Engage via Bellevue philanthropic boards within 60 days; no direct outreach.",
    },
    '3614 HUNTS POINT RD': {
        'happening': "Trust-held asset, grantor in late-life stage.",
        'why':       "Decision window is biological, not market-driven.",
        'action':    "Identify connector within 2 weeks; map estate attorneys; do not cold call.",
    },
    '647 EVERGREEN POINT RD': {
        'happening': "Dormant ownership pattern with long tenure.",
        'why':       "Not urgent, but highly predictable over time.",
        'action':    "Annual touchpoint via estate-planning community; no direct contact this cycle.",
    },
    '7737 OVERLAKE DR W': {
        'happening': "Stable ownership, approaching typical transition window.",
        'why':       "No immediate signal, but strong long-term likelihood.",
        'action':    "Quarterly neighborhood presence; target one referral network introduction per year.",
    },
}


# ──────────────────────────────────────────────────────────────────────
#  HISTORY + DEDUP
# ──────────────────────────────────────────────────────────────────────
def load_history():
    if not os.path.exists(HIST_PATH):
        return {'weeks': []}
    return json.load(open(HIST_PATH))


def get_recent_pins(history, n_weeks=4, exclude_week=None):
    """Pins from the last N weeks' picks — to avoid resurfacing.
    If exclude_week is provided, skip that week (for idempotent same-week re-runs)."""
    weeks = [w for w in history['weeks'] if w.get('week_of') != exclude_week]
    recent = weeks[-n_weeks:] if weeks else []
    pins = {}
    for w in recent:
        for pick in w.get('picks', []):
            pins[pick['pin']] = pick.get('section')
    return pins


def save_history(history, week_of, picks):
    # Idempotent: remove any existing entry for this week_of
    history['weeks'] = [w for w in history['weeks'] if w.get('week_of') != week_of]
    history['weeks'].append({
        'week_of': week_of,
        'generated_at': datetime.now().isoformat(),
        'picks': [
            {'pin': p['pin'], 'address': p.get('address'),
             'section': p['_section'], 'band': p['band']}
            for p in picks
        ]
    })
    # Keep only last 12 weeks of history to prevent unbounded growth
    history['weeks'] = history['weeks'][-12:]
    with open(HIST_PATH, 'w') as f:
        json.dump(history, f, indent=2)


# ──────────────────────────────────────────────────────────────────────
#  NORMALIZATION
# ──────────────────────────────────────────────────────────────────────
def owner_base_key(L):
    """Strip LLC/Trust suffixes so we can detect same-entity clustering."""
    owner = (L.get('owner') or '').upper()
    for suffix in [' LLC', ' INC', ' L.L.C.', ' LP', ' L.P.', ' LTD',
                   ' CORP', ' CORPORATION', ' CO.',
                   ' REVOCABLE TRUST', ' IRREVOCABLE TRUST',
                   ' LIVING TRUST', ' FAMILY TRUST', ' SPENDTHRIFT TRUST',
                   ' TRUST', ' TRUSTEE', ' TRS', ' TR',
                   ' ET AL', ' ET UX', '(SPOUSES)']:
        owner = owner.replace(suffix, '')
    owner = re.sub(r'\s+', ' ', owner).strip()
    return owner[:40]


def resolve_copy(L, section=None):
    """Get the 3-line copy for a lead: overrides → signal template → generic.

    Investigation override: if a deep investigation produced a concrete
    recommended_action, its next_step overrides the 'action' line.
    The 'happening' and 'why' lines still come from templates/overrides
    because they provide parcel-specific context the investigation doesn't.
    """
    addr = (L.get('address') or '').upper().strip()
    if addr in PROPERTY_OVERRIDES:
        base = dict(PROPERTY_OVERRIDES[addr])
    else:
        sig = L.get('signal_family')
        sub = L.get('sub_signal')
        if section == 'STRATEGIC HOLDS' and sig in STRATEGIC_HOLDS_TEMPLATES:
            base = dict(STRATEGIC_HOLDS_TEMPLATES[sig])
        else:
            key = (sig, sub)
            if key in COPY_TEMPLATES: base = dict(COPY_TEMPLATES[key])
            else:
                key = (sig, None)
                if key in COPY_TEMPLATES: base = dict(COPY_TEMPLATES[key])
                else:
                    base = {
                        'happening': "Transition signal observed on this parcel.",
                        'why':       "Pattern matches historical pre-seller cohort.",
                        'action':    "Add to cultivation pipeline; appropriate approach per signal type.",
                    }

    # Investigation override — only for deep-mode results that produced
    # a real action recommendation (not the default 'hold' fallback)
    inv = L.get('investigation') or {}
    if inv.get('mode') == 'deep':
        rec = inv.get('recommended_action') or {}
        cat = rec.get('category')
        step = rec.get('next_step')
        reason = rec.get('reason')
        # Only override if investigation found something actionable
        if cat in ('call_now', 'build_now', 'avoid') and step:
            base['action'] = step
            # Enrich 'why' with the investigation reason when it adds context
            if reason and reason not in base.get('why', ''):
                base['why'] = f"{base.get('why', '')} {reason}".strip()
    return base


# ──────────────────────────────────────────────────────────────────────
#  SELECTION
# ──────────────────────────────────────────────────────────────────────
def _score(L):
    """Prefer calibrated_rank_score when available, fallback to rank_score.

    Investigation-aware adjustments:
      - has_blocker:         exclude entirely (handled in filter, not score)
      - has_life_event:      +10% boost
      - has_financial:       +15% boost (stronger - forced-sale signal)
      - deep investigation:  +5% (signal we know more about this lead)
    """
    base = L.get('calibrated_rank_score') or L.get('rank_score') or 0
    inv = L.get('investigation')
    if not inv:
        return base
    # Blockers are filtered upstream, but guard here too
    if inv.get('has_blocker'):
        return 0
    boost = 1.0
    if inv.get('has_life_event'):  boost *= 1.10
    if inv.get('has_financial'):   boost *= 1.15
    if inv.get('mode') == 'deep':  boost *= 1.05
    return base * boost


def _has_blocker(L):
    """Investigation blocker check — exclude if has_blocker was set."""
    inv = L.get('investigation') or {}
    return bool(inv.get('has_blocker'))


def _investigation_demotes_from_call_now(L):
    """If investigation ran deep mode and recommended anything other than
    call_now, respect that over the default Band 3 inclusion. This lets
    investor_disposition and expired-listing Band 3 leads drop to BUILD NOW
    when investigation found no hard-pressure signals."""
    i = L.get('investigation') or {}
    if i.get('mode') != 'deep': return False
    rec = i.get('recommended_action') or {}
    cat = rec.get('category')
    # Only demote if investigation explicitly said build_now or hold
    # (avoid is handled by blocker filter)
    return cat in ('build_now', 'hold')


def _investigation_promotes_to_call_now(L):
    """A lead promotes to CALL NOW if investigation returned pressure=3 (hard).
    This lets Band 2 leads with court-verified probate, divorce, obituary, or
    high-trust financial signals jump into the weekly CALL NOW list."""
    i = L.get('investigation') or {}
    rec = i.get('recommended_action') or {}
    return rec.get('category') == 'call_now' and (rec.get('pressure') or 0) >= 3


def select_call_now(leads, exclude_pins, used_owner_keys):
    """5 CALL NOW picks with slot reservations:

      Slots 1-2 reserved for Band 3 financial_stress (trustee sale, NOD,
         lis pendens) — these always lead the week
      Remaining slots: highest-scoring eligible leads, drawn from
         - Band 3 leads NOT demoted by investigation
         - Band 2 leads promoted by investigation pressure=3

    Investigation demotion rule: any Band 3 lead whose deep investigation
    recommended build_now/hold/avoid gets dropped from CALL NOW eligibility.
    """
    def base_filter(L):
        return (L['pin'] not in exclude_pins
                and owner_base_key(L) not in used_owner_keys
                and not _has_blocker(L))

    picks = []

    # Slots 1-2: Band 3 financial_stress (NOD, trustee sale, lis pendens)
    fin_stress = sorted(
        [L for L in leads
         if L['band'] == 3 and L.get('signal_family') == 'financial_stress'
         and base_filter(L)],
        key=lambda x: -_score(x),
    )
    for L in fin_stress[:2]:
        ok = owner_base_key(L)
        if ok in used_owner_keys: continue
        picks.append(L); used_owner_keys.add(ok)

    # Remaining slots: Band 3 NOT demoted, plus Band 2 promoted
    already_picked = {p['pin'] for p in picks}
    remaining = sorted(
        [L for L in leads
         if L['pin'] not in already_picked
         and (
             (L['band'] == 3 and not _investigation_demotes_from_call_now(L))
             or _investigation_promotes_to_call_now(L)
         )
         and base_filter(L)],
        key=lambda x: -_score(x),
    )
    for L in remaining:
        ok = owner_base_key(L)
        if ok in used_owner_keys: continue
        picks.append(L); used_owner_keys.add(ok)
        if len(picks) == 5: break
    return picks


def select_build_now(leads, exclude_pins, used_owner_keys, n=3):
    """3 Band 2 with tier mix: prefer 1 ultra + 1 luxury + 1 mid."""
    def pool_for(lo, hi):
        return sorted(
            [L for L in leads
             if L['band'] == 2
             and lo <= (L.get('value') or 0) < hi
             and L['pin'] not in exclude_pins
             and owner_base_key(L) not in used_owner_keys
             and not _has_blocker(L)],
            key=lambda x: -_score(x),
        )

    tier_pools = OrderedDict([
        ('ultra',  pool_for(*TIER_ULTRA)),
        ('luxury', pool_for(*TIER_LUXURY)),
        ('mid',    pool_for(*TIER_MID)),
    ])

    picks = []
    # Round 1: one from each tier (guarantees mix)
    for tier_name, pool in tier_pools.items():
        if len(picks) >= n: break
        for L in pool:
            if owner_base_key(L) in used_owner_keys: continue
            picks.append(L)
            used_owner_keys.add(owner_base_key(L))
            break

    # Round 2: fill remaining slots by highest-ranked across all tiers
    if len(picks) < n:
        remaining = []
        for pool in tier_pools.values(): remaining.extend(pool)
        remaining.sort(key=lambda x: -_score(x))
        for L in remaining:
            if len(picks) >= n: break
            if owner_base_key(L) in used_owner_keys: continue
            if L['pin'] in {p['pin'] for p in picks}: continue
            picks.append(L)
            used_owner_keys.add(owner_base_key(L))
    return picks


def select_strategic_holds(leads, exclude_pins, used_owner_keys, n=2):
    """
    Top remaining Band 2 by (timeline_months DESC, inevitability DESC).
    These are long-cycle positioning plays, not urgent.
    """
    b2 = sorted(
        [L for L in leads
         if L['band'] == 2
         and L['pin'] not in exclude_pins
         and owner_base_key(L) not in used_owner_keys
         and not _has_blocker(L)
         # "No urgency signals" — exclude anything with financial stress
         and L.get('signal_family') not in ('financial_stress', 'investor_disposition')],
        key=lambda x: (-(x.get('timeline_months') or 0), -(x.get('inevitability') or 0)),
    )
    picks = []
    for L in b2:
        ok = owner_base_key(L)
        if ok in used_owner_keys: continue
        picks.append(L)
        used_owner_keys.add(ok)
        if len(picks) == n: break
    return picks


# ──────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────
def generate_weekly_playbook(week_of=None):
    from outcomes import load_outcomes, register_surfaced, save_outcomes, get_excluded_pins

    inv = json.load(open(INV_PATH))
    leads = inv['leads']
    history = load_history()
    wk = week_of or datetime.now().strftime('%Y-%m-%d')
    recent_pins_map = get_recent_pins(history, n_weeks=4, exclude_week=wk)

    # Load outcomes and get pins to permanently/semi-permanently exclude
    outcomes = load_outcomes()
    outcome_excluded = get_excluded_pins(outcomes)

    # Allow a lead to resurface if its band was UPGRADED (e.g., B2→B3)
    exclude_pins = set(outcome_excluded)  # outcome-based exclusions are additive
    for L in leads:
        pin = L['pin']
        if pin not in recent_pins_map: continue
        prev_section = recent_pins_map[pin]
        # If it was in a non-CALL-NOW section and is now B3, allow resurface
        if L['band'] == 3 and prev_section != 'CALL NOW':
            continue  # allow
        exclude_pins.add(pin)

    used_owner_keys = set()

    call_now = select_call_now(leads, exclude_pins, used_owner_keys)
    build_now = select_build_now(leads, exclude_pins, used_owner_keys, n=3)
    strategic_holds = select_strategic_holds(leads, exclude_pins, used_owner_keys, n=2)

    # Tag + resolve copy
    for L in call_now:        L['_section'] = 'CALL NOW'
    for L in build_now:       L['_section'] = 'BUILD NOW'
    for L in strategic_holds: L['_section'] = 'STRATEGIC HOLDS'

    all_picks = call_now + build_now + strategic_holds
    for L in all_picks:
        L['_copy'] = resolve_copy(L, section=L['_section'])

    # Persist picks
    with open(PICKS_PATH, 'w') as f:
        json.dump({
            'week_of': wk,
            'generated_at': datetime.now().isoformat(),
            'call_now': [{'pin': L['pin'], 'address': L.get('address'),
                          'owner': L.get('owner'), 'value': L.get('value'),
                          'zip': L.get('zip'), 'signal_family': L.get('signal_family'),
                          'sub_signal': L.get('sub_signal'),
                          'rank_score': L.get('rank_score'),
                          'copy': L['_copy']}
                         for L in call_now],
            'build_now': [{'pin': L['pin'], 'address': L.get('address'),
                           'owner': L.get('owner'), 'value': L.get('value'),
                           'zip': L.get('zip'), 'signal_family': L.get('signal_family'),
                           'rank_score': L.get('rank_score'),
                           'copy': L['_copy']}
                          for L in build_now],
            'strategic_holds': [{'pin': L['pin'], 'address': L.get('address'),
                                 'owner': L.get('owner'), 'value': L.get('value'),
                                 'zip': L.get('zip'),
                                 'signal_family': L.get('signal_family'),
                                 'timeline_months': L.get('timeline_months'),
                                 'inevitability': L.get('inevitability'),
                                 'copy': L['_copy']}
                                for L in strategic_holds],
            'excluded_for_recency': len(exclude_pins),
        }, f, indent=2, default=str)

    # Update history
    save_history(history, wk, all_picks)

    # Register picks in outcomes state (creates NEW records for first-time picks)
    outcomes = register_surfaced(outcomes, all_picks, wk)
    save_outcomes(outcomes)

    return {
        'call_now': call_now, 'build_now': build_now,
        'strategic_holds': strategic_holds,
        'excluded_for_recency': len(exclude_pins) - len(outcome_excluded),
        'excluded_for_outcome': len(outcome_excluded),
        'shortfalls': {
            'call_now': max(0, 5 - len(call_now)),
            'build_now': max(0, 3 - len(build_now)),
            'strategic_holds': max(0, 2 - len(strategic_holds)),
        },
    }


if __name__ == "__main__":
    result = generate_weekly_playbook()
    print(f"Week of {datetime.now().strftime('%B %-d, %Y')}")
    print(f"Excluded from last 4 weeks: {result['excluded_for_recency']}\n")

    for section in ['call_now', 'build_now', 'strategic_holds']:
        label = section.replace('_', ' ').upper()
        print(f"═══ {label} ═══")
        for i, L in enumerate(result[section], 1):
            city = {'98004': 'Bellevue', '98039': 'Medina', '98040': 'Mercer Island',
                    '98033': 'Kirkland', '98006': 'Newport', '98005': 'Bridle Trails'}.get(L.get('zip'), '')
            val = L.get('value', 0) / 1_000_000
            print(f"  {i}. {L.get('address','—'):35} {city:12} ~${val:.1f}M")
            c = L['_copy']
            print(f"     {c['happening']}")
            print(f"     {c['why']}")
            print(f"     → {c['action']}\n")
