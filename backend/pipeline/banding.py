"""
SellerSignal — Inevitability × Timeline Banding Reranker

Replaces the old lead_tier system (act_this_week / active_window / long_horizon)
with 4 bands organized by PROBABILITY OF SALE × TIMELINE TO SALE.

This is the correct axis. Old tiers sorted by signal type, which mixed escapable
behavioral events (divorce, NOD) with inevitable biological events (trust-aging
grantor 80+). Those are NOT the same urgency tier.

Bands:
  Band 1: Imminent + Inevitable  — 0-12mo,   inevitability > 0.70
  Band 2: Probable + Inevitable  — 12-36mo,  inevitability > 0.50
  Band 3: Imminent + Escapable   — 0-12mo,   inevitability 0.20-0.70
  Band 4: Long-Cycle (Six Letters) — 24mo+,   inevitability < 0.50
  REJECTED: rationality < 4 OR inevitability < 0.15

Inevitability = P(transition within expected timeline)
Timeline = expected months to transition
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class BandedLead:
    pin: str
    address: str
    zip: str
    owner: str
    value: int
    signal_family: str
    sub_signal: str = ""
    inevitability: float = 0.0
    timeline_months: int = 0
    rationality: Optional[float] = None
    band: int = 4
    band_label: str = ""
    rank_score: float = 0.0
    narrative: str = ""
    evidence: list = None


# ─── BASELINE PROFILES PER SIGNAL FAMILY ────────────────────────────
# inevitability_base = P(actually transitions within baseline timeline)
# timeline_base_months = expected months to transition
#
# Source: NAR conversion data, ATTOM foreclosure outcomes, industry priors

SIGNAL_PROFILES = {
    # — Tier-1 observed events (behavioral, mostly escapable) —
    'financial_stress::trustee_sale': {
        'inev': 0.55, 'timeline': 3,
        'note': 'Past cure window — forced disposition imminent'
    },
    'financial_stress::nod': {
        'inev': 0.40, 'timeline': 9,
        'note': '~40-50% proceed to sale per ATTOM foreclosure data; rest cure/refi/modify'
    },
    'financial_stress::lis_pendens': {
        'inev': 0.25, 'timeline': 15,
        'note': 'Litigation pending; many resolve via settlement without forced sale'
    },
    'divorce_unwinding::new_filing': {
        'inev': 0.30, 'timeline': 18,
        'note': 'NAR: ~30% of divorces result in home sale; 70% reconcile/refi/buyout'
    },
    'divorce_unwinding::dissolution_final': {
        'inev': 0.55, 'timeline': 12,
        'note': 'Final dissolution issued; property disposition typically 6-18mo after'
    },
    'death_inheritance::probate_filed': {
        'inev': 0.95, 'timeline': 9,
        'note': 'Probate-court-supervised disposition; estate MUST sell or distribute'
    },
    'death_inheritance::obit_matched_no_probate': {
        'inev': 0.55, 'timeline': 14,
        'note': 'Recent obit matched to owner; estate status unknown'
    },
    'failed_sale_attempt::prime': {
        'inev': 0.60, 'timeline': 6,
        'note': 'Rational seller whose listing failed for addressable reasons'
    },
    'failed_sale_attempt::caution': {
        'inev': 0.30, 'timeline': 10,
        'note': 'Rationality concerns — lead with market data, not persuasion'
    },
    'investor_disposition::overdue': {
        'inev': 0.60, 'timeline': 9,
        'note': 'Hold cycle past typical exit — disposition imminent'
    },
    'investor_disposition::in_window': {
        'inev': 0.25, 'timeline': 15,
        'note': 'Within typical hold window — may or may not exit'
    },

    # — Tier-2 inferred pre-sellers (biological, mostly inevitable) —
    'trust_aging::grantor_80plus': {
        'inev': 0.90, 'timeline': 24,
        'note': 'Trust grantor age 80+ — mortality + estate planning in terminal window'
    },
    'trust_aging::grantor_75_79': {
        'inev': 0.70, 'timeline': 36,
        'note': 'Trust grantor age 75-79 — high estate-planning activity window'
    },
    'trust_aging::grantor_65_74': {
        'inev': 0.45, 'timeline': 60,
        'note': 'Trust grantor age 65-74 — cultivation cohort'
    },
    'silent_transition::age_80plus': {
        'inev': 0.75, 'timeline': 24,
        'note': 'Individual owner 80+, long tenure — biological transition window'
    },
    'silent_transition::age_75_79': {
        'inev': 0.55, 'timeline': 36,
        'note': 'Individual owner 75-79, long tenure — high-probability cohort'
    },
    'silent_transition::age_70_74': {
        'inev': 0.35, 'timeline': 48,
        'note': 'Individual owner 70-74 — long-cycle cultivation'
    },
    'silent_transition::age_65_69': {
        'inev': 0.20, 'timeline': 72,
        'note': 'Individual owner 65-69 — deep cultivation cohort'
    },
    'dormant_absentee::oos_aging': {
        'inev': 0.45, 'timeline': 24,
        'note': 'Out-of-state mail + aging owner — disengagement signal strong'
    },
    'dormant_absentee::local_aging': {
        'inev': 0.30, 'timeline': 36,
        'note': 'Local non-residence address + aging owner — estate planning routing'
    },
    'absentee_oos_disposition': {
        'inev': 0.30, 'timeline': 36,
        'note': 'Out-of-state owner — disposition within typical hold cycle'
    },
    'high_equity_long_tenure': {
        'inev': 0.25, 'timeline': 48,
        'note': 'Long tenure + high equity — cultivation cohort without age info'
    },
}


def assign_band(inev: float, timeline_months: int, rationality: Optional[float]) -> tuple[int, str]:
    """
    Assign a lead to one of 4 bands based on inevitability × timeline.
    Returns (band_number, band_label).
    """
    if rationality is not None and rationality < 4.0:
        return (0, "REJECTED (rationality)")
    if inev < 0.15:
        return (0, "REJECTED (low probability)")

    if timeline_months <= 12:
        # Imminent
        if inev >= 0.70:
            return (1, "Band 1 — Imminent + Inevitable")
        else:
            return (3, "Band 3 — Imminent + Escapable")
    elif timeline_months <= 36:
        if inev >= 0.50:
            return (2, "Band 2 — Probable + Inevitable")
        else:
            return (4, "Band 4 — Long-Cycle Cultivation")
    else:
        if inev >= 0.60:
            return (2, "Band 2 — Probable + Inevitable")
        return (4, "Band 4 — Long-Cycle Cultivation")


def classify_lead(
    signal_family: str,
    sub_signal: str = "",
    rationality: Optional[float] = None,
    convergent_signals: list = None,
    owner_age: Optional[int] = None,
) -> tuple[float, int, int, str]:
    """
    Return (inevitability, timeline_months, band, band_label)
    """
    convergent_signals = convergent_signals or []
    key = f"{signal_family}::{sub_signal}" if sub_signal else signal_family
    profile = SIGNAL_PROFILES.get(key) or SIGNAL_PROFILES.get(signal_family)
    if not profile:
        profile = {'inev': 0.25, 'timeline': 36}

    inev = profile['inev']
    timeline = profile['timeline']

    # Convergence boost — multiple signals agreeing tighten the probability
    if len(convergent_signals) >= 2:
        inev = min(inev * 1.25, 0.95)
        timeline = int(timeline * 0.75)
    if len(convergent_signals) >= 3:
        inev = min(inev * 1.15, 0.95)
        timeline = int(timeline * 0.70)

    band, label = assign_band(inev, timeline, rationality)
    return (round(inev, 3), timeline, band, label)


def rank_score(inev: float, timeline_months: int, value: int) -> float:
    """
    Cross-band ranking score — prioritizes high inevitability, short timeline, high value.
    score = (inev × value) / sqrt(timeline_months)
    """
    import math
    return (inev * value / 1_000_000) / math.sqrt(max(timeline_months, 3))


# ─── Self-test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ('financial_stress', 'trustee_sale', None, [], None, 'GOLDEN IVY trustee sale'),
        ('financial_stress', 'nod', None, [], 45, 'NOD, owner 45 refinanced 3mo ago'),
        ('death_inheritance', 'probate_filed', None, [], None, 'Probate filed on estate'),
        ('failed_sale_attempt', 'prime', 8.0, [], None, 'Rational expired'),
        ('failed_sale_attempt', 'caution', 5.5, [], None, 'Caution expired'),
        ('failed_sale_attempt', 'caution', 2.0, [], None, '415 Shoreland (score 2.0)'),
        ('trust_aging', 'grantor_80plus', None, [], 82, 'HP4 Trust Hunts Point age 82'),
        ('trust_aging', 'grantor_75_79', None, ['silent'], 77, 'Simonyi trust, convergent'),
        ('silent_transition', 'age_75_79', None, ['dormant'], 81, 'Kristina Clapp, S+D'),
        ('silent_transition', 'age_65_69', None, [], 68, 'Young silent cohort'),
        ('divorce_unwinding', 'new_filing', None, [], None, 'Fresh divorce'),
    ]
    print(f"{'Case':50} {'Inev':>5} {'Tmln':>5} {'Band':>3} {'Label'}")
    print("-" * 130)
    for sf, sub, rat, conv, age, label in cases:
        inev, timeline, band, band_label = classify_lead(sf, sub, rat, conv, age)
        print(f"{label:50} {inev:>5.2f} {timeline:>4}mo {band:>3} {band_label}")
