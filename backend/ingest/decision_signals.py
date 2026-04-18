"""
SellerSignal v2 — Decision Signals.

The "decision activation test" — per ChatGPT's April 17 critique:

  A candidate cannot be confirmed unless there is evidence of ACTIVE
  DECISION-MAKING BEHAVIOR.

Without decision evidence, ownership patterns describe state, not action.
"Entity held 1.3 years past LTCG" describes thousands of parcels that are
not selling. It's context, not a trigger.

This module builds behavioral indices that can actually detect decisions:

  1. Portfolio churn — same entity has sold OTHER parcels recently
  2. Flip cycle match — hold-time matches the entity's own historical pattern
  3. Cross-parcel acquisition mode — entity is actively BUYING (contradiction
     for disposition; active acquirers aren't rotating out)

What's NOT here (but would strengthen the test further if data existed):
  - Building permits opened/closed (KC permit data — not wired)
  - Real-estate listing activity (MLS — not wired / out of scope)
  - Staging / photography activity
  - Refinance / capital event patterns
  - WA SOS principal cross-reference (to link related LLCs)

These are the data sources Jeremy would need to plug in to make
investor_disposition actually strong.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Optional

from evidence_resolution import is_business_entity


# ═══════════════════════════════════════════════════════════════════════
# ENTITY ACTIVITY INDEX
# ═══════════════════════════════════════════════════════════════════════
def build_entity_activity_index(
    deed_chain_by_pin: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """
    For each business-entity name, list all their deed activity across
    ALL parcels in the index.

    Returns: {entity_name_upper: [{pin, date, role, price}, ...]}
    """
    idx: dict[str, list[dict]] = defaultdict(list)
    for pin, deeds in deed_chain_by_pin.items():
        for row in deeds:
            price = row.get("price") or 0
            if price < 100_000:
                continue  # skip non-arms-length
            seller = (row.get("seller") or "").upper().strip()
            buyer = (row.get("buyer") or "").upper().strip()
            if is_business_entity(seller):
                idx[seller].append({
                    "pin": pin, "date": row["date"],
                    "role": "seller", "price": price,
                })
            if is_business_entity(buyer):
                idx[buyer].append({
                    "pin": pin, "date": row["date"],
                    "role": "buyer", "price": price,
                })
    return dict(idx)


# ═══════════════════════════════════════════════════════════════════════
# DECISION SIGNAL: portfolio churn
# ═══════════════════════════════════════════════════════════════════════
def detect_portfolio_churn(
    entity_name: str,
    activity_index: dict[str, list[dict]],
    exclude_pin: str,
    window_years: float = 2.0,
) -> Optional[dict]:
    """
    Has this entity sold other parcels in the last `window_years`?

    If yes, this is a REAL behavioral signal — the principals behind this
    entity are actively rotating inventory.

    If no, the entity is just holding — not a disposition candidate.
    """
    now = datetime.utcnow()
    up = (entity_name or "").upper().strip()
    activity = activity_index.get(up, [])

    recent_sales = [
        a for a in activity
        if a["role"] == "seller"
        and a["pin"] != exclude_pin
        and (now - a["date"]).days / 365.25 < window_years
    ]
    if not recent_sales:
        return None

    return {
        "count": len(recent_sales),
        "most_recent_date": max(a["date"] for a in recent_sales).strftime("%Y-%m-%d"),
        "total_volume": sum(a["price"] for a in recent_sales),
        "sample_pins": [a["pin"] for a in recent_sales[:3]],
    }


# ═══════════════════════════════════════════════════════════════════════
# COUNTER-SIGNAL: active acquisition mode
# ═══════════════════════════════════════════════════════════════════════
def detect_active_acquisition(
    entity_name: str,
    activity_index: dict[str, list[dict]],
    window_years: float = 1.0,
) -> Optional[dict]:
    """
    Has this entity BOUGHT more than it's sold in the last window?

    If yes, they're in acquisition mode — not rotating out.
    This is a CONTRADICTION for investor_disposition.
    """
    now = datetime.utcnow()
    up = (entity_name or "").upper().strip()
    activity = activity_index.get(up, [])

    recent_buys = [a for a in activity
                   if a["role"] == "buyer"
                   and (now - a["date"]).days / 365.25 < window_years]
    recent_sells = [a for a in activity
                    if a["role"] == "seller"
                    and (now - a["date"]).days / 365.25 < window_years]

    if len(recent_buys) >= 2 and len(recent_buys) > len(recent_sells):
        return {
            "buy_count": len(recent_buys),
            "sell_count": len(recent_sells),
            "net_mode": "acquiring",
        }
    return None


# ═══════════════════════════════════════════════════════════════════════
# HOLD-CYCLE MATCH (flipper timing)
# ═══════════════════════════════════════════════════════════════════════
def detect_hold_cycle_match(
    entity_name: str,
    activity_index: dict[str, list[dict]],
    current_hold_years: float,
    tolerance: float = 0.5,
) -> Optional[dict]:
    """
    Does the entity have a historical hold pattern, and does this parcel match it?

    Returns cycle stats if the entity has 2+ completed buy→sell cycles,
    regardless of whether THIS parcel currently matches. The caller decides
    what counts as "in window" via detect_asset_exit_window.
    """
    up = (entity_name or "").upper().strip()
    activity = sorted(activity_index.get(up, []), key=lambda a: a["date"])
    if len(activity) < 4:
        return None

    cycles = []
    by_pin = defaultdict(list)
    for a in activity:
        by_pin[a["pin"]].append(a)
    for pin, events in by_pin.items():
        events_sorted = sorted(events, key=lambda a: a["date"])
        buys = [e for e in events_sorted if e["role"] == "buyer"]
        sells = [e for e in events_sorted if e["role"] == "seller"]
        if buys and sells:
            buy_date = buys[0]["date"]
            sell_date = sells[-1]["date"]
            if sell_date > buy_date:
                cycles.append((sell_date - buy_date).days / 365.25)

    if len(cycles) < 2:
        return None

    typical = sum(cycles) / len(cycles)
    if abs(current_hold_years - typical) <= tolerance:
        return {
            "typical_hold_years": round(typical, 1),
            "current_hold_years": round(current_hold_years, 1),
            "prior_cycles": len(cycles),
        }
    return None


# ═══════════════════════════════════════════════════════════════════════
# ASSET-LEVEL EXIT SIGNAL
# Per ChatGPT's critique: portfolio churn proves the entity is an operator,
# but doesn't prove THIS asset is the next one to go. Require evidence that
# THIS specific parcel is in or past the entity's typical exit window.
# ═══════════════════════════════════════════════════════════════════════
def detect_asset_exit_window(
    entity_name: str,
    activity_index: dict[str, list[dict]],
    current_hold_years: float,
) -> Optional[dict]:
    """
    Is THIS specific parcel at or past the entity's typical exit window?

    Requires the entity to have 2+ completed buy→sell cycles. Computes the
    typical hold mean and population std. Returns a signal IFF:
      - current_hold >= max(typical - 0.25, typical * 0.85)  (in window)
      - AND current_hold <= typical + 2 * std                (not abandoned)
      - OR current_hold > typical + 2 * std                  (overdue)

    Parcels still deep in renovation (current_hold << typical) do NOT fire —
    that's construction, not decision.
    """
    up = (entity_name or "").upper().strip()
    activity = sorted(activity_index.get(up, []), key=lambda a: a["date"])
    if len(activity) < 4:
        return None

    cycles: list[float] = []
    by_pin: dict[str, list[dict]] = defaultdict(list)
    for a in activity:
        by_pin[a["pin"]].append(a)
    for pin, events in by_pin.items():
        events_sorted = sorted(events, key=lambda a: a["date"])
        buys = [e for e in events_sorted if e["role"] == "buyer"]
        sells = [e for e in events_sorted if e["role"] == "seller"]
        if buys and sells:
            bd = buys[0]["date"]; sd = sells[-1]["date"]
            if sd > bd:
                cycles.append((sd - bd).days / 365.25)

    if len(cycles) < 2:
        return None

    n = len(cycles)
    typical = sum(cycles) / n
    variance = sum((c - typical) ** 2 for c in cycles) / n
    std = variance ** 0.5

    # Entry to exit window: either 3 months before typical, or 85% of typical
    in_window_floor = max(typical - 0.25, typical * 0.85)
    overdue_ceiling = typical + 2 * std

    if current_hold_years < in_window_floor:
        return None  # still in renovation, not a decision

    if current_hold_years <= overdue_ceiling:
        state = "in_exit_window"
        description = (f"At {current_hold_years:.1f}y, this parcel is in the entity's "
                       f"typical exit window (mean {typical:.1f}y, σ={std:.1f}y across "
                       f"{n} prior cycles)")
    else:
        state = "overdue"
        description = (f"At {current_hold_years:.1f}y, this parcel is OVERDUE relative "
                       f"to the entity's typical hold (mean {typical:.1f}y, σ={std:.1f}y). "
                       f"Renovation or listing attempt may have stalled")

    return {
        "state": state,
        "typical_hold_years": round(typical, 1),
        "std_years": round(std, 2),
        "current_hold_years": round(current_hold_years, 1),
        "prior_cycles": n,
        "description": description,
    }
