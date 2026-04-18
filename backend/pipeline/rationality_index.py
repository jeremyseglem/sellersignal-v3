"""
SellerSignal — Seller Rationality Index

Scores each failed/expired listing on 7 indicators that together predict whether
the seller is rational enough to actually close a transaction with a new agent.

Score range: 0 (unreasonable, don't call) to 10 (mispriced but reasonable — call)
Threshold: < 4 = REJECT from briefing entirely
Threshold: 4-6 = include but flag caution
Threshold: 7-10 = prime failed-sale lead

Indicators (all computable from KC data):
  1. Price adjustment behavior       (±2)
  2. DOM vs neighborhood median       (±2)
  3. Number of prior listing cycles   (0 to -3)
  4. Time between expire and relist   (±2)
  5. Agent churn across cycles        (0 to -2)
  6. Original price vs comp median    (+1 to -2)
  7. Listing duration                 (±1)

Starting score: 5 (neutral).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Optional


@dataclass
class RationalityScore:
    score: float
    components: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    recommendation: str = ""

    def band(self) -> str:
        if self.score < 4: return "REJECT"
        if self.score < 7: return "CAUTION"
        return "PRIME"


def score_listing_rationality(
    orig_price: int,
    latest_price: int,
    listing_start: datetime,
    listing_end: datetime,
    prior_cycles: list,            # list of {orig, end, price}
    agents_across_cycles: list,    # list of agent names per cycle
    neighborhood_median_dom: int,
    comp_median_price: int,
) -> RationalityScore:
    """
    Given one failed listing + historical context, return rationality score.
    """
    score = 5.0
    components = {}
    flags = []

    # ── 1. Price adjustment behavior ─────────────────────────────────
    if orig_price and latest_price:
        if latest_price > orig_price:
            components['price_adjustment'] = -2
            flags.append("Price BUMPED UP during listing — denial behavior")
        else:
            drop_pct = 100 * (orig_price - latest_price) / orig_price
            if drop_pct == 0:
                components['price_adjustment'] = -1
                flags.append("No price adjustment — seller stuck on original")
            elif drop_pct < 5:
                components['price_adjustment'] = 0
                flags.append("Minimal price adjustment (<5%) — token gesture")
            elif drop_pct < 12:
                components['price_adjustment'] = +2
                flags.append(f"Reasonable price adjustment ({drop_pct:.0f}%) — responding to market")
            elif drop_pct < 25:
                components['price_adjustment'] = +1
                flags.append(f"Large price drop ({drop_pct:.0f}%) — over-priced originally but adjusted")
            else:
                components['price_adjustment'] = -1
                flags.append(f"Extreme price drop ({drop_pct:.0f}%) — original was delusional")

    # ── 2. DOM vs neighborhood median ────────────────────────────────
    dom = (listing_end - listing_start).days if listing_start and listing_end else 0
    if neighborhood_median_dom and dom:
        ratio = dom / neighborhood_median_dom
        if ratio <= 1.5:
            components['dom_ratio'] = +1
        elif ratio <= 2.5:
            components['dom_ratio'] = 0
        elif ratio <= 4.0:
            components['dom_ratio'] = -1
            flags.append(f"DOM {dom}d = {ratio:.1f}x neighborhood median — structural issue")
        else:
            components['dom_ratio'] = -2
            flags.append(f"DOM {dom}d = {ratio:.1f}x neighborhood median — unmarketable at this price")

    # ── 3. Number of prior listing cycles ────────────────────────────
    n_cycles = len(prior_cycles) + 1  # +1 for current
    if n_cycles == 1:
        components['cycle_count'] = 0
    elif n_cycles == 2:
        components['cycle_count'] = -1
        flags.append("2nd listing cycle — prior attempt failed")
    elif n_cycles == 3:
        components['cycle_count'] = -2
        flags.append("3rd listing cycle — chronic unsuccessful seller")
    else:
        components['cycle_count'] = -3
        flags.append(f"{n_cycles}th listing cycle — serial expired — reject")

    # ── 4. Time between expire and relist (gap as reflection) ────────
    if prior_cycles:
        prev_end = prior_cycles[-1].get('end')
        if prev_end and listing_start:
            gap_days = (listing_start - prev_end).days
            if gap_days < 7:
                components['reflection_gap'] = -2
                flags.append("Same-week relist — DOM-reset tactic, no reflection")
            elif gap_days < 60:
                components['reflection_gap'] = -1
                flags.append(f"Quick relist ({gap_days}d) — didn't reset expectations")
            elif gap_days < 180:
                components['reflection_gap'] = +1
                flags.append(f"Moderate reflection gap ({gap_days}d)")
            else:
                components['reflection_gap'] = +2
                flags.append(f"Long reflection gap ({gap_days}d) — reality check happened")

    # ── 5. Agent churn ───────────────────────────────────────────────
    unique_agents = len(set(a for a in agents_across_cycles if a))
    if unique_agents == 0 or unique_agents == 1:
        components['agent_churn'] = 0
    elif unique_agents == 2:
        components['agent_churn'] = -1
        flags.append("2 different agents across cycles — seller fired prior agent")
    else:
        components['agent_churn'] = -2
        flags.append(f"{unique_agents} different agents across cycles — seller is the problem")

    # ── 6. Original price vs comp median ─────────────────────────────
    if orig_price and comp_median_price and comp_median_price > 0:
        premium = (orig_price / comp_median_price) - 1
        if premium <= 0.05:
            components['comp_premium'] = +1
            flags.append(f"Priced within 5% of comp median — realistic")
        elif premium <= 0.15:
            components['comp_premium'] = 0
        elif premium <= 0.25:
            components['comp_premium'] = -1
            flags.append(f"Priced {premium*100:.0f}% above comp median — ambitious")
        else:
            components['comp_premium'] = -2
            flags.append(f"Priced {premium*100:.0f}% above comp median — delusional")

    # ── 7. Listing duration ──────────────────────────────────────────
    if dom > 0:
        if dom < 180:
            components['duration'] = +1
        elif dom < 365:
            components['duration'] = 0
        else:
            components['duration'] = -1
            flags.append(f"Listed {dom}d ({dom/365:.1f}yr) before expiring")

    # Tally
    for v in components.values():
        score += v
    score = max(0, min(10, score))

    # Recommendation
    if score < 4:
        rec = "REJECT — seller patterns indicate chronically unreasonable. Don't contact."
    elif score < 7:
        rec = "CAUTION — contact with specific pricing evidence. Lead with market data, not persuasion."
    else:
        rec = "PRIME — rational seller whose listing failed for addressable reasons. Direct outreach."

    return RationalityScore(
        score=round(score, 1),
        components=components,
        flags=flags,
        recommendation=rec,
    )


def score_rationality_partial(
    orig_price: Optional[int],
    latest_price: Optional[int],
    listing_start: Optional[datetime],
    listing_end: Optional[datetime],
    zip_median_value: Optional[int] = None,
    zip_median_dom: int = 90,
) -> RationalityScore:
    """
    Partial-data scorer for leads where we only have single-cycle info.
    Skips the 3 multi-cycle indicators (prior cycles, agent churn, relist gap).
    Returns a score on a compressed 0-10 scale using only 4 of the 7 signals.
    """
    score = 5.0
    components = {}
    flags = []

    # 1. Price adjustment — did they drop?
    if orig_price and latest_price and orig_price > 0:
        if latest_price < orig_price:
            drop_pct = 100 * (orig_price - latest_price) / orig_price
            if drop_pct >= 10:
                score += 2; components['price_adjusted'] = +2
                flags.append(f"Adjusted price down {drop_pct:.0f}% — seller responsive to market")
            elif drop_pct >= 3:
                score += 1; components['price_adjusted'] = +1
                flags.append(f"Modest price drop {drop_pct:.0f}%")
        else:
            score -= 1; components['no_price_drop'] = -1
            flags.append("No price adjustment despite failing to sell")

    # 2. DOM vs neighborhood median
    if listing_start and listing_end:
        dom = (listing_end - listing_start).days
        if dom >= zip_median_dom * 2.5:
            score -= 2; components['dom_excessive'] = -2
            flags.append(f"DOM {dom}d vs neighborhood {zip_median_dom}d median — 2.5x over")
        elif dom >= zip_median_dom * 1.5:
            score -= 1; components['dom_long'] = -1
            flags.append(f"DOM {dom}d — notably above median")
        elif dom < zip_median_dom * 0.6:
            score += 1; components['dom_short'] = +1
            flags.append(f"DOM {dom}d — pulled quickly, possible non-market reason for cancel")

    # 3. Original price vs ZIP median value
    if orig_price and zip_median_value and zip_median_value > 0:
        ratio = orig_price / zip_median_value
        if ratio > 2.5:
            score -= 2; components['priced_above_market'] = -2
            flags.append(f"Listed at {ratio:.1f}x ZIP median — significantly above market")
        elif ratio > 1.8:
            score -= 1; components['priced_high'] = -1
            flags.append(f"Listed at {ratio:.1f}x ZIP median")

    # Clamp 0-10
    score = max(0.0, min(10.0, score))

    if score < 4:
        rec = "REJECT — seller behavior suggests low conversion probability"
    elif score < 7:
        rec = "CAUTION — include but flag; get a condition read before investing outreach"
    else:
        rec = "PRIME — rational seller, mispriced or poorly marketed by prior agent"

    return RationalityScore(
        score=round(score, 1),
        components=components,
        flags=flags,
        recommendation=rec,
    )


# ─── Example self-test ───────────────────────────────────────────────
if __name__ == "__main__":
    # Hypothetical: 415 Shoreland scenario (relisted multiple times)
    from datetime import datetime as dt
    s = score_listing_rationality(
        orig_price=24_985_000,
        latest_price=21_500_000,
        listing_start=dt(2025, 10, 16),
        listing_end=dt(2026, 4, 15),
        prior_cycles=[
            {'orig': dt(2025, 4, 15), 'end': dt(2025, 10, 1),
             'price_start': 24_985_000, 'price_end': 24_985_000}
        ],
        agents_across_cycles=['Terry Allen', 'Terry Allen'],  # same agent both cycles
        neighborhood_median_dom=80,  # luxury 98004 median
        comp_median_price=17_500_000,  # 5BR 9K sqft waterfront comps
    )
    print(f"Score: {s.score}  Band: {s.band()}")
    print(f"Components: {s.components}")
    print("Flags:")
    for f in s.flags: print(f"  - {f}")
    print(f"Rec: {s.recommendation}")
