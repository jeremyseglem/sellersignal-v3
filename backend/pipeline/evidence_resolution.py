"""
SellerSignal v2 — Evidence Resolution.

Takes raw observations (deed rows, obit hits, tenure values, mail addresses, etc.)
and tags each as one of:

  trigger       — why this candidate surfaced under this signal family
  support       — makes the signal hypothesis more plausible
  context       — informative, not predictive alone
  contradiction — weakens the hypothesis
  resolution    — proves the opportunity already resolved (fatal)

The same raw fact can map to DIFFERENT evidence roles under DIFFERENT signal families.
Example: indiv→LLC at parcel X
  - trigger under pre_listing_structuring
  - context under death_inheritance (it's just a holding structure, not an event)
  - contradiction under retirement_downsize (owner isn't being careful about simplicity)
"""
from __future__ import annotations
import csv
import re
from datetime import datetime
from typing import Optional

from backend.pipeline.schema import Evidence


# ═══════════════════════════════════════════════════════════════════════
# SHARED: deed-chain resolution check
#   This is used by EVERY signal family to detect "already resolved"
# ═══════════════════════════════════════════════════════════════════════
def detect_resolution_events(
    deed_chain: list[dict],
    trigger_date: Optional[datetime] = None,
) -> list[Evidence]:
    """
    Look at the deed chain for anything that would RESOLVE a candidate:
    - arms-length sale (price > $100k) after the trigger
    - listing sales
    - superseding deed patterns

    If trigger_date is given, only look at events AFTER that date.
    """
    out: list[Evidence] = []
    threshold = trigger_date or datetime(1900, 1, 1)
    for row in deed_chain:
        row_date = row.get("date")
        if not row_date or row_date <= threshold:
            continue
        price = row.get("price", 0) or 0
        if price > 100_000:
            out.append(Evidence(
                role="resolution",
                source="kc_deed_chain",
                description=(f"Arms-length sale recorded {row_date.strftime('%Y-%m-%d')} "
                             f"for ${price:,} (seller: {row.get('seller','?')[:30]} → "
                             f"buyer: {row.get('buyer','?')[:30]})"),
                observed_at=row_date.strftime("%Y-%m-%d"),
                data_ref={"deed_row": {k: str(v) for k, v in row.items()}},
                weight=10.0,  # fatal
            ))
    return out


# ═══════════════════════════════════════════════════════════════════════
# SHARED: ENTITY DETECTION
# Business entities (flippers, investors) vs family estate-planning trusts.
# Word-boundary matching — "LP" as substring was matching "KAMALPREET".
# ═══════════════════════════════════════════════════════════════════════
import re as _re

BUSINESS_ENTITY_TOKENS = ("LLC", "INC", "CORP", "PROPERTIES", "HOLDINGS",
                          "PARTNERS", "ASSOCIATES", "FOUNDATION", "COMPANY",
                          "LP", "LLP", "PSC", "PLLC", "DEVELOPMENT",
                          "CAPITAL", "GROUP", "VENTURES", "ENTERPRISES",
                          "INVESTMENTS")

# Family estate-planning signals — NOT flippers, should not trigger investor_disposition
FAMILY_TRUST_SIGNALS = ("REVOCABLE", "FAMILY TRUST", "LIVING TRUST",
                         "FAMILY REVOCABLE", "IRREVOCABLE")

# Any trust/ttee marker (all trusts, not just family ones)
TRUST_TOKENS = ("TRUST", "TTEE")


def _has_word(name: str, token: str) -> bool:
    """Word-boundary match. 'LP' matches 'ABC LP' but not 'KAMALPREET'."""
    pattern = r"\b" + _re.escape(token) + r"\b"
    return bool(_re.search(pattern, name or "", _re.IGNORECASE))


def is_business_entity(name: str) -> bool:
    """True iff name looks like a business entity (LLC/Inc/Corp/etc.)."""
    up = (name or "").upper()
    return any(_has_word(up, tok) for tok in BUSINESS_ENTITY_TOKENS)


def is_family_trust(name: str) -> bool:
    """True iff name looks like a family estate-planning trust."""
    up = (name or "").upper()
    if any(sig in up for sig in FAMILY_TRUST_SIGNALS):
        return True
    return False


def is_any_trust(name: str) -> bool:
    """True if name contains any trust marker (family or otherwise)."""
    up = (name or "").upper()
    return any(_has_word(up, tok) for tok in TRUST_TOKENS)


def is_entity_owner(name: str) -> bool:
    """
    True iff the name is NOT a natural person.
    A business entity OR any trust qualifies.
    Used by death_inheritance to exclude non-person owners.
    """
    return is_business_entity(name) or is_any_trust(name)


# Retained for backward compatibility with earlier code paths.
ENTITY_TOKENS = BUSINESS_ENTITY_TOKENS + TRUST_TOKENS


# ═══════════════════════════════════════════════════════════════════════
# FAMILY-SPECIFIC EVIDENCE RESOLVERS
# ═══════════════════════════════════════════════════════════════════════
def resolve_death_inheritance_evidence(
    obit_signal: dict,                    # signal from SERP: {name, date, age, source, context}
    owner_record: dict,                   # from owner DB
    deed_chain: list[dict],               # from KC_RPSale, filtered to this parcel
    person_tokens_on_title: list[set[str]],  # token sets per person on title
    obit_tokens: set[str],
    surname: str,                         # explicit surname from the obit's western-format name
) -> list[Evidence]:
    """
    Evidence resolution for death_inheritance signal.
    """
    out: list[Evidence] = []

    # TRIGGER: the obit itself, that we matched a name
    best_overlap: set[str] = set()
    for ptokens in person_tokens_on_title:
        overlap = obit_tokens & ptokens
        if len(overlap) > len(best_overlap):
            best_overlap = overlap

    # Only create a trigger if there's a meaningful name overlap on surname+one other
    non_surname_overlap = best_overlap - {surname}
    if surname in best_overlap and len(non_surname_overlap) >= 1:
        out.append(Evidence(
            role="trigger",
            source=f"serp:{obit_signal.get('source','')}",
            description=(f"Obituary: {obit_signal['name']} died {obit_signal['date']}, "
                         f"context: {obit_signal.get('context','')}. Name tokens match "
                         f"owner: {sorted(best_overlap)}"),
            observed_at=obit_signal["date"],
            data_ref={"obit": obit_signal, "overlap": sorted(best_overlap)},
            weight=3.0,
        ))

    # SUPPORT: owner type is individual (entity cannot die, but trust can hold decedent's estate)
    owner_name = owner_record.get("owner_name", "")
    if is_business_entity(owner_name):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description=f"Owner is business entity ({owner_name[:40]}) — entities cannot die",
            weight=5.0,
        ))
    else:
        # Natural person or trust (trusts commonly hold decedents' properties)
        out.append(Evidence(
            role="support",
            source="owner_db",
            description="Owner is natural person(s) or trust, consistent with a death event",
            weight=1.0,
        ))

    # SUPPORT: long tenure suggests elderly decedent actually owned the property
    tenure = owner_record.get("tenure_years") or 0

    # RESOLUTION CHECK: if current tenure is shorter than time-since-obit, someone
    # acquired AFTER the death — the estate already sold.
    obit_dt = datetime.strptime(obit_signal["date"], "%Y-%m-%d")
    years_since_obit = (datetime.utcnow() - obit_dt).days / 365.25
    if tenure > 0 and tenure < years_since_obit - 0.25:  # 3-month grace for deed-record lag
        out.append(Evidence(
            role="resolution",
            source="owner_db",
            description=(f"Current owner tenure ({tenure:.1f}y) is shorter than time-since-death "
                         f"({years_since_obit:.1f}y) — property acquired AFTER the decedent died. "
                         f"Estate already disposed."),
            weight=10.0,
        ))
    elif tenure >= 15:
        out.append(Evidence(
            role="support",
            source="owner_db",
            description=f"Long ownership tenure ({tenure:.1f} years) consistent with long-term residence",
            weight=1.0,
        ))
    elif tenure < 2:
        # ChatGPT: short-tenure death is much weaker than it looks.
        # Could be heir-triggered refinance, trust formation, etc.
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description=(f"Very short tenure ({tenure:.1f}y) — may reflect recent title "
                         f"event (refinance, trust formation, partial transfer) rather "
                         f"than an active estate in motion"),
            weight=3.0,  # upgraded from 1.5
        ))
    elif tenure < 3:
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description=(f"Short ownership tenure ({tenure:.1f}y) — possible recent "
                         f"title event unrelated to decedent"),
            weight=1.5,
        ))

    # CONTRADICTION: acquisition date AFTER the obit date (impossible)
    for row in deed_chain:
        row_date = row.get("date")
        if not row_date: continue
        price = row.get("price", 0) or 0
        if price > 100_000 and row_date > obit_dt:
            continue  # handled below by shared resolution detector

    # RESOLUTION: shared detector for later arms-length sales
    out.extend(detect_resolution_events(deed_chain, trigger_date=obit_dt))

    return out


# ═══════════════════════════════════════════════════════════════════════
def resolve_investor_disposition_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: Optional[dict] = None,
    activity_index: Optional[dict] = None,
    parcel_id: Optional[str] = None,
) -> list[Evidence]:
    """
    Investor disposition v3 — ASSET-LEVEL EXIT SIGNAL REQUIRED.

    Per ChatGPT's April 17 critique: "Why THIS asset, not just this owner?"

    Portfolio churn proves the entity is an active operator but doesn't
    answer whether THIS parcel is next. The trigger must be asset-specific:
      - Parcel is in or past entity's typical exit window, OR
      - Parcel's hold is significantly overdue relative to entity's pattern

    Portfolio churn → SUPPORT (operator confirmation)
    Active acquisition mode → CONTRADICTION
    Estate-to-investor deed pattern → CONTEXT only
    Entity tenure past LTCG → CONTEXT only
    """
    from backend.pipeline.decision_signals import (
        detect_portfolio_churn, detect_active_acquisition, detect_asset_exit_window,
    )
    out: list[Evidence] = []
    if not deed_chain or not trigger_hint:
        return out

    owner_name = owner_record.get("owner_name", "")
    if not is_business_entity(owner_name):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description=f"Current owner ({owner_name[:40]}) is not a business entity",
            weight=5.0,
        ))
        return out

    current_hold = owner_record.get("tenure_years") or 0

    # ═══ TRIGGER: asset-level exit window ════════════════════════════
    # This is the one thing that says "THIS parcel, now."
    exit_window = None
    if activity_index is not None:
        exit_window = detect_asset_exit_window(
            entity_name=owner_name,
            activity_index=activity_index,
            current_hold_years=current_hold,
        )
        if exit_window:
            # Per ChatGPT critique: overdue is a stronger signal than in-window.
            # In-window = "approaching typical exit" (they might sell, might hold)
            # Overdue   = "past typical exit with no resolution" (something stalled)
            if exit_window["state"] == "overdue":
                weight = 3.5
            else:
                weight = 2.0   # in_exit_window — softer; needs more corroboration
            out.append(Evidence(
                role="trigger",
                source="kc_deed_chain_cross_parcel",
                description=exit_window["description"],
                data_ref={"exit_window": exit_window},
                weight=weight,
            ))

    # ═══ SUPPORT: portfolio churn (entity is an operator) ════════════
    if activity_index is not None and parcel_id:
        churn = detect_portfolio_churn(
            entity_name=owner_name,
            activity_index=activity_index,
            exclude_pin=parcel_id,
            window_years=2.0,
        )
        if churn:
            out.append(Evidence(
                role="support",
                source="kc_deed_chain_cross_parcel",
                description=(f"Portfolio churn: {owner_name[:40]} has sold "
                             f"{churn['count']} other parcel(s) in the last 24 months "
                             f"(most recent: {churn['most_recent_date']}). Confirms "
                             f"entity is an active rotator, not a passive holder."),
                observed_at=churn["most_recent_date"],
                data_ref={"churn": churn},
                weight=1.5,
            ))

    # ═══ CONTRADICTION: active acquisition mode ══════════════════════
    if activity_index is not None:
        acquiring = detect_active_acquisition(
            entity_name=owner_name,
            activity_index=activity_index,
            window_years=1.0,
        )
        if acquiring:
            out.append(Evidence(
                role="contradiction",
                source="kc_deed_chain_cross_parcel",
                description=(f"Entity in active acquisition mode: "
                             f"{acquiring['buy_count']} buys vs {acquiring['sell_count']} sells "
                             f"in last 12 months — not rotating out"),
                weight=5.0,
            ))

    # ═══ CONTEXT: deed pattern ═══════════════════════════════════════
    pattern = trigger_hint.get("pattern")
    recent_deed = trigger_hint.get("most_recent_deed", {})
    if pattern == "estate_to_investor":
        prior_held = trigger_hint.get("prior_held_years", 0)
        out.append(Evidence(
            role="context",
            source="kc_deed_chain",
            description=(f"Estate-to-investor acquisition pattern: prior seller held "
                         f"{prior_held:.0f}+ years; entity acquired in last 3 years."),
            observed_at=recent_deed.get("date", ""),
            weight=0.5,
        ))

    # ═══ CONTEXT: current hold window ════════════════════════════════
    if 1.0 <= current_hold <= 5.0:
        out.append(Evidence(
            role="context",
            source="owner_db",
            description=f"Current hold: {current_hold:.1f} years. Past LTCG threshold.",
            weight=0.3,
        ))

    # ═══ RESOLUTION: later arms-length sale ══════════════════════════
    from datetime import datetime as _dt
    trigger_dt = None
    if recent_deed.get("date"):
        try:
            trigger_dt = _dt.strptime(recent_deed["date"].split()[0], "%Y-%m-%d")
        except (ValueError, TypeError):
            trigger_dt = None
    for row in deed_chain:
        row_date = row.get("date")
        if not row_date or not trigger_dt: continue
        if row_date <= trigger_dt: continue
        price = row.get("price", 0) or 0
        if price > 100_000:
            out.append(Evidence(
                role="resolution",
                source="kc_deed_chain",
                description=(f"Later arms-length sale {row_date.strftime('%Y-%m-%d')} "
                             f"for ${price:,} — investor already disposed"),
                observed_at=row_date.strftime("%Y-%m-%d"),
                weight=10.0,
            ))

    return out


# ═══════════════════════════════════════════════════════════════════════
def resolve_retirement_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    retirement_signal: Optional[dict] = None,   # optional SERP retirement announcement
) -> list[Evidence]:
    """
    Retirement/downsize evidence resolution.

    Trigger: retirement announcement matching owner, OR senior-exemption flag.
    Long tenure alone is NOT sufficient for a trigger (v1 mistake).
    """
    out: list[Evidence] = []
    owner_name = owner_record.get("owner_name", "")
    if is_entity_owner(owner_name):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description="Entity owner — retirement_downsize doesn't apply to entities",
            weight=10.0,
        ))
        return out

    tenure = owner_record.get("tenure_years") or 0

    # TRIGGER: retirement announcement matched
    if retirement_signal:
        out.append(Evidence(
            role="trigger",
            source=f"serp:{retirement_signal.get('source','')}",
            description=f"Retirement announcement: {retirement_signal.get('context','')}",
            observed_at=retirement_signal.get("date"),
            weight=3.0,
        ))

    # Without a trigger source, retirement alone doesn't surface. If we have a trigger,
    # long tenure becomes support; otherwise nothing to evaluate.
    if not retirement_signal:
        return []  # no trigger, no candidate

    # SUPPORT: long tenure consistent with someone now reaching retirement age
    if tenure >= 20:
        out.append(Evidence(
            role="support",
            source="owner_db",
            description=f"Ownership tenure of {tenure:.1f} years consistent with pre-retirement hold",
            weight=1.0,
        ))

    # CONTEXT: mailing address = property address means they live here
    mailing = (owner_record.get("mailing_address", "") or "").strip().upper()
    situs = (owner_record.get("address", "") or "").strip().upper()
    if mailing and situs and mailing in situs:
        out.append(Evidence(
            role="support",
            source="owner_db",
            description="Mail address matches property — owner-occupied primary residence",
            weight=1.0,
        ))

    # RESOLUTION
    ret_dt = None
    if retirement_signal and retirement_signal.get("date"):
        try:
            ret_dt = datetime.strptime(retirement_signal["date"], "%Y-%m-%d")
        except ValueError:
            ret_dt = None
    out.extend(detect_resolution_events(deed_chain, trigger_date=ret_dt))

    return out


# ═══════════════════════════════════════════════════════════════════════
def resolve_absentee_oos_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: dict,
    cross_family_signals: list[str],
) -> list[Evidence]:
    """
    Absentee OOS evidence resolution.

    Being out-of-state with long tenure is a state, not a decision. To confirm,
    we need either:
      - Very long OOS tenure (15+ years — crossing a life-stage boundary), OR
      - A concurrent signal from another family (death, retirement, investor)

    Without one of those, the candidate goes WEAK, not confirmed. This prevents
    the "271 absentee owners = 271 leads" failure mode that ChatGPT warned about.
    """
    out: list[Evidence] = []
    mail_city = trigger_hint.get("mail_city", "")
    tenure = trigger_hint.get("tenure_years") or 0

    # TRIGGER: very long OOS tenure (15+ years — strong state-of-affairs)
    if tenure >= 15:
        out.append(Evidence(
            role="trigger",
            source="kc_mailing_records",
            description=(f"Owner mailing address is out-of-state ({mail_city}) "
                         f"with {tenure:.1f}-year tenure. Administratively distant "
                         f"holding past typical life-transition boundaries."),
            data_ref={"mail_city": mail_city, "tenure": tenure},
            weight=2.0,
        ))
    elif tenure >= 10:
        # Less strong — needs cross-family support to become a lead
        out.append(Evidence(
            role="trigger",
            source="kc_mailing_records",
            description=(f"Owner mailing address is out-of-state ({mail_city}) "
                         f"with {tenure:.1f}-year tenure."),
            weight=1.0,
        ))

    # SUPPORT: cross-family concurrent signal
    for fam in cross_family_signals:
        if fam in ("death_inheritance", "retirement_downsize", "investor_disposition"):
            out.append(Evidence(
                role="support",
                source="cross_family",
                description=f"Concurrent {fam} signal on same parcel — confirms active disposition",
                weight=2.5,
            ))

    # CONTRADICTION: owner is entity
    if is_entity_owner(owner_record.get("owner_name", "")):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description="Current owner is entity — absentee family applies to individuals",
            weight=5.0,
        ))

    # RESOLUTION: later arms-length sale
    out.extend(detect_resolution_events(deed_chain))

    return out


def resolve_high_equity_long_tenure_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: dict,
    cross_family_signals: list[str],
) -> list[Evidence]:
    """
    High-equity long-tenure evidence resolution.

    ON ITS OWN, long-tenure high-equity is a WATCHLIST, not a lead. Most long-tenure
    owners never sell — they keep the property and take the stepped-up basis at
    death. The trigger is the equity position; the decision needs a catalyst.

    CATALYST REQUIRED: concurrent signal from death / retirement / investor /
    pre-listing-structuring / absentee_oos. Without a catalyst, the candidate
    goes WEAK (logged but not shipped).

    This is the right discipline per ChatGPT's earlier critique — ownership
    state ≠ selling decision.
    """
    out: list[Evidence] = []
    tenure = trigger_hint.get("tenure_years") or 0
    multiple = trigger_hint.get("equity_multiple") or 0
    purchase = trigger_hint.get("purchase_price") or 0
    value = trigger_hint.get("current_value") or 0

    # TRIGGER: the equity position — intentionally weak. ChatGPT's point:
    # equity alone is a condition, not a decision. Without a catalyst this
    # won't confirm on its own; the whole family is essentially a watchlist.
    out.append(Evidence(
        role="trigger",
        source="owner_db_plus_deed_chain",
        description=(f"Long tenure ({tenure:.0f}y) with estimated equity "
                     f"{multiple:.1f}x purchase price (${purchase:,} → ${value:,}). "
                     f"Well past Sec 121 exclusion cap — latent tax-timing consideration."),
        data_ref=trigger_hint,
        weight=0.8,   # demoted from 1.5
    ))

    # SUPPORT: cross-family concurrent signal (the catalyst)
    catalyst_fams = ("death_inheritance", "retirement_downsize",
                     "absentee_oos_disposition", "pre_listing_structuring")
    for fam in cross_family_signals:
        if fam in catalyst_fams:
            out.append(Evidence(
                role="support",
                source="cross_family",
                description=f"Catalyst: concurrent {fam} signal — activates equity trigger",
                weight=2.5,
            ))

    # CONTRADICTION: entity owner
    if is_entity_owner(owner_record.get("owner_name", "")):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description="Current owner is entity — high-equity-long-tenure applies to individuals",
            weight=5.0,
        ))

    # RESOLUTION
    out.extend(detect_resolution_events(deed_chain))

    return out


# ═══════════════════════════════════════════════════════════════════════
# FAILED SALE ATTEMPT
# The strongest seller-decision signal: "they tried to sell and failed."
# ═══════════════════════════════════════════════════════════════════════
def resolve_divorce_unwinding_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: dict,
) -> list[Evidence]:
    """
    Divorce filing evidence resolution.

    Both parties on title = strong (marital property being dissolved).
    One party on title = weaker (may be separate property, but still signal).
    Filter by filing recency — window is 18 months from filing.
    """
    out: list[Evidence] = []
    case_no = trigger_hint.get("case_number", "?")
    filing_date = trigger_hint.get("filing_date", "?")
    petitioner = trigger_hint.get("petitioner", "?")
    respondent = trigger_hint.get("respondent", "?")
    strength = trigger_hint.get("match_strength", "weak")

    weight = 4.0 if strength == "strong" else 2.5
    out.append(Evidence(
        role="trigger",
        source="kc_superior_court:case_search",
        description=(
            f"Dissolution filed {filing_date} ({case_no}): "
            f"{petitioner} vs {respondent}. "
            f"{'Both parties on title' if strength=='strong' else 'One party on title'} — "
            f"marital property subject to division."
        ),
        observed_at=filing_date,
        data_ref=trigger_hint,
        weight=weight,
    ))

    # SUPPORT: joint ownership pattern in deed chain
    if deed_chain:
        latest = deed_chain[-1] if deed_chain else {}
        buyer = (latest.get("buyer") or "").upper()
        if "+" in buyer or "AND" in buyer:
            out.append(Evidence(
                role="support",
                source="kc_deed_chain",
                description="Joint ownership on most recent vesting deed — "
                            "consistent with marital community property",
                weight=1.5,
            ))

    # SUPPORT: long tenure suggests established marital home vs. post-marriage rental
    tenure = owner_record.get("tenure_years") or 0
    if tenure >= 5:
        out.append(Evidence(
            role="support",
            source="owner_db",
            description=f"Established residence ({tenure:.0f}y tenure) — "
                        f"likely primary marital home, not an investment property",
            weight=1.0,
        ))

    # CONTRADICTION: owner is entity (LLC, trust) — title not typically split in divorce
    if is_entity_owner(owner_record.get("owner_name", "")):
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description="Entity ownership — marital property division typically "
                        "affects personally-titled assets",
            weight=2.5,
        ))

    # RESOLUTION: any deed transfer AFTER the filing date
    trigger_date = None
    try:
        trigger_date = datetime.strptime(filing_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    out.extend(detect_resolution_events(deed_chain, trigger_date=trigger_date))
    return out


def resolve_financial_stress_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: dict,
) -> list[Evidence]:
    """
    NOD / Lis Pendens / Trustee Sale evidence resolution.

    Document type determines urgency + base weight:
      - Notice of Trustee Sale: imminent forced sale (weight 5.0, highest in system)
      - Notice of Default:      90-day foreclosure clock started (weight 4.5)
      - Lis Pendens:            litigation pending, slower (weight 3.0)

    Days-since-recording matters: a 3-day-old NOD is more urgent than a
    80-day-old one (borrower may have cured or sold).
    """
    out: list[Evidence] = []
    doc_type = trigger_hint.get("document_type", "").upper()
    rec_num = trigger_hint.get("recording_number", "?")
    rec_date = trigger_hint.get("recording_date", "?")
    grantor = trigger_hint.get("grantor", "?")
    grantee = trigger_hint.get("grantee", "?")
    days_since = trigger_hint.get("days_since_recording", 999)

    if "TRUSTEE SALE" in doc_type:
        weight = 5.0
        narrative = ("Notice of Trustee Sale recorded — foreclosure auction "
                     "scheduled. Seller will act within the sale-notice window "
                     "(typically 30-120 days).")
    elif "DEFAULT" in doc_type:
        weight = 4.5
        narrative = ("Notice of Default recorded — 90-day foreclosure clock "
                     "has started. Owner will either cure, sell, or lose the property.")
    elif "LIS PENDENS" in doc_type:
        weight = 3.0
        narrative = ("Lis Pendens recorded — litigation pending on title. "
                     "Case outcome will likely force a transaction.")
    else:
        weight = 2.0
        narrative = f"Adverse document recorded: {doc_type}"

    out.append(Evidence(
        role="trigger",
        source="kc_recorder:record_date_search",
        description=f"{narrative} Recording {rec_num} dated {rec_date}. "
                    f"Grantor: {grantor}. Grantee (lender/plaintiff): {grantee}.",
        observed_at=rec_date,
        data_ref=trigger_hint,
        weight=weight,
    ))

    # Decay: older filings may have been cured or resolved
    if days_since > 120:
        out.append(Evidence(
            role="contradiction",
            source="kc_recorder",
            description=f"Recording is {days_since} days old — "
                        f"may have been cured, dismissed, or already resolved",
            weight=1.5,
        ))

    # SUPPORT: direct PIN match is stronger than name-based fallback
    # (we can tell by whether the grantor name exactly matches owner name)
    owner_name = owner_record.get("owner_name", "")
    if owner_name and grantor and name_match_strong(grantor, owner_name):
        out.append(Evidence(
            role="support",
            source="kc_recorder",
            description="Grantor name directly matches current owner on title",
            weight=1.5,
        ))

    # RESOLUTION: check for curing events — a deed recorded AFTER the NOD
    # that releases the lis pendens, or a trustee's deed / arms-length sale
    trigger_date = None
    try:
        trigger_date = datetime.strptime(rec_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    out.extend(detect_resolution_events(deed_chain, trigger_date=trigger_date))
    return out


def name_match_strong(filing_name: str, owner_name: str) -> bool:
    """Helper — stricter match for support evidence (3+ token overlap)."""
    from backend.pipeline.legal_filings import normalize_name
    return len(normalize_name(filing_name) & normalize_name(owner_name)) >= 3


# ═══════════════════════════════════════════════════════════════════════
# FAILED SALE ATTEMPT — Zillow-scraped listing failures
# ═══════════════════════════════════════════════════════════════════════
def resolve_failed_sale_attempt_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    trigger_hint: dict,
) -> list[Evidence]:
    """
    Failed-sale-attempt evidence resolution.

    Owner listed the property and pulled it without selling. Past the
    "should we sell?" question. On the "why didn't it work?" question.
    """
    out: list[Evidence] = []
    failed = trigger_hint.get("failed_pattern")
    struggle = trigger_hint.get("struggle_pattern")

    if failed:
        pattern = failed.get("pattern")
        dom = failed.get("dom_days", 0)
        listed = failed.get("listed_date", "?")
        removed = failed.get("removed_date") or "still listed"
        price = failed.get("last_price") or 0

        if pattern == "listing_removed_no_sale":
            out.append(Evidence(
                role="trigger",
                source="zillow:price_history",
                description=(f"Listed for sale {listed} at ${price:,}, "
                             f"removed {removed} after {dom} days on market "
                             f"with no completed sale."),
                observed_at=removed,
                data_ref={"failed": failed},
                weight=4.0,
            ))
        elif pattern == "stale_listing_no_movement":
            out.append(Evidence(
                role="trigger",
                source="zillow:price_history",
                description=(f"Listed for sale {listed} at ${price:,}, still "
                             f"active after {dom} days with no price movement."),
                observed_at=listed,
                data_ref={"failed": failed},
                weight=3.0,
            ))

    if struggle:
        drops = struggle.get("price_reductions", 0)
        drop_pct = struggle.get("drop_pct", 0)
        out.append(Evidence(
            role="support",
            source="zillow:price_history",
            description=(f"Price reduced {drops} times from "
                         f"${struggle['initial_price']:,} to "
                         f"${struggle['current_price']:,} ({drop_pct}% total)."),
            data_ref={"struggle": struggle},
            weight=2.0,
        ))

    tenure = owner_record.get("tenure_years") or 0
    if tenure >= 10:
        out.append(Evidence(
            role="support",
            source="owner_db",
            description=f"Long tenure ({tenure:.0f}y) — equity flexibility to re-list",
            weight=0.5,
        ))

    owner_name = owner_record.get("owner_name", "")
    if is_business_entity(owner_name) and tenure < 3:
        out.append(Evidence(
            role="contradiction",
            source="owner_db",
            description=("Short-tenure entity owner — may be builder/flipper "
                         "running market-test rather than failed committed sale"),
            weight=2.5,
        ))

    # RESOLUTION: only sales AFTER the listing attempt count as "resolved"
    # (the pre-listing sale is just the prior acquisition, not a resolution)
    trigger_date = None
    if failed:
        # Use the listing_date if we have it, or removed_date as fallback
        dt_str = failed.get("listed_date") or failed.get("removed_date")
        if dt_str:
            try:
                trigger_date = datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                trigger_date = None
    out.extend(detect_resolution_events(deed_chain, trigger_date=trigger_date))
    return out


# ═══════════════════════════════════════════════════════════════════════
# PRE-LISTING STRUCTURING (TRIGGER-ONLY)
# ═══════════════════════════════════════════════════════════════════════
def resolve_pre_listing_structuring_evidence(
    owner_record: dict,
    deed_chain: list[dict],
    concurrent_signals: list[str],
) -> list[Evidence]:
    """
    Pre-listing structuring — TRIGGER ONLY. This is the critical v1 correction.

    The ONLY way a pre-listing-structuring candidate becomes a lead is if
    ANOTHER signal family has also triggered for the same parcel, and that
    OTHER family promotes the lead. Pre-listing structuring contributes
    `support` evidence to the other family, never its own lead.
    """
    out: list[Evidence] = []
    if not deed_chain:
        return out

    sorted_chain = sorted(deed_chain, key=lambda r: r.get("date", datetime(1900,1,1)))

    # Look for indiv→LLC pattern in recent deed history
    for i, row in enumerate(sorted_chain):
        seller = row.get("seller", "") or ""
        buyer = row.get("buyer", "") or ""
        price = row.get("price", 0) or 0
        reason = (row.get("reason") or "").strip()

        seller_entity = is_entity_owner(seller)
        buyer_entity = is_entity_owner(buyer)

        row_date = row.get("date")
        if not row_date: continue
        age_years = (datetime.utcnow() - row_date).days / 365.25

        # indiv→LLC within last 12 months
        if not seller_entity and buyer_entity and price < 100_000 and age_years < 1.0:

            # CONTRADICTION: post-purchase wrap
            # If the prior deed was an arms-length purchase by the same individual
            if i > 0:
                prior = sorted_chain[i-1]
                prior_price = prior.get("price", 0) or 0
                prior_buyer = prior.get("buyer", "") or ""
                if prior_price > 100_000 and seller in prior_buyer:
                    time_since_purchase = (row_date - prior["date"]).days / 365.25
                    if time_since_purchase < 1.0:
                        out.append(Evidence(
                            role="contradiction",
                            source="kc_deed_chain",
                            description=(f"Recent indiv→LLC transfer is a post-purchase wrap — "
                                         f"individual bought {time_since_purchase:.1f}yr before wrapping into LLC"),
                            observed_at=row_date.strftime("%Y-%m-%d"),
                            weight=5.0,
                        ))
                        continue  # skip the trigger

            # CONTRADICTION: ownership strings look like internal restructuring
            if seller.split()[0].upper() in buyer.upper():
                out.append(Evidence(
                    role="contradiction",
                    source="kc_deed_chain",
                    description=("LLC name reuses owner's name (internal restructuring, "
                                 "not market-facing)"),
                    observed_at=row_date.strftime("%Y-%m-%d"),
                    weight=3.0,
                ))
                continue

            # Otherwise it's a valid TRIGGER — but only in this family
            out.append(Evidence(
                role="trigger",
                source="kc_deed_chain",
                description=(f"Recent indiv→LLC transfer ({seller[:25]} → {buyer[:25]}) "
                             f"on {row_date.strftime('%Y-%m-%d')} — possible pre-listing structuring"),
                observed_at=row_date.strftime("%Y-%m-%d"),
                weight=1.0,
            ))

    # SUPPORT FROM OTHER FAMILIES: check if any other signal triggered for this parcel
    for fam in concurrent_signals:
        if fam != "pre_listing_structuring":
            out.append(Evidence(
                role="support",
                source="cross_family",
                description=f"Concurrent trigger in signal family: {fam}",
                weight=2.0,
            ))

    # RESOLUTION
    out.extend(detect_resolution_events(deed_chain))

    return out


# ═══════════════════════════════════════════════════════════════════════
# CLASSIFY: decide confirmed / weak / rejected
# ═══════════════════════════════════════════════════════════════════════
def classify_candidate(
    evidence: list[Evidence],
    family: str,
    can_promote_to_lead: bool,
) -> tuple[str, str, str]:
    """
    Returns: (candidate_status, confidence, reason)

    Hard rules:
    - pre_listing_structuring never confirms alone (can_promote_to_lead=False)
    - ANY resolution evidence → rejected
    - No trigger → rejected
    - sum(contradiction weights) >= sum(support weights) → weak
    - ZERO support items → confidence capped at LOW (per ChatGPT critique)
    - Otherwise: confidence scales with net weight
    """
    triggers = [e for e in evidence if e.role == "trigger"]
    supports = [e for e in evidence if e.role == "support"]
    contradictions = [e for e in evidence if e.role == "contradiction"]
    resolutions = [e for e in evidence if e.role == "resolution"]

    if resolutions:
        first_res = resolutions[0]
        return ("rejected", "low", f"RESOLVED: {first_res.description}")

    if not triggers:
        return ("rejected", "low",
                f"No trigger evidence for {family} — property events alone don't create leads")

    if not can_promote_to_lead:
        return ("weak", "low",
                "Pre-listing structuring is trigger-only; requires corroborating signal from another family")

    trigger_weight = sum(e.weight for e in triggers)
    support_weight = sum(e.weight for e in supports)
    contradiction_weight = sum(e.weight for e in contradictions)
    net = trigger_weight + support_weight - contradiction_weight

    if contradiction_weight >= (trigger_weight + support_weight):
        return ("weak", "low",
                f"Contradictions ({contradiction_weight:.1f}) "
                f"outweigh support ({trigger_weight + support_weight:.1f})")

    # ─── FAMILY-SPECIFIC CONFIDENCE LADDERS ──────────────────────────
    # financial_stress: the document type IS the signal. A recorded NOD or
    # Trustee Sale is binary fact, not inference — doesn't need support
    # corroboration to be HIGH confidence. (Per ChatGPT: legal pressure is
    # non-optional; confidence should reflect the document's legal weight.)
    if family == "financial_stress":
        strongest_trigger_desc = ""
        strongest_weight = 0.0
        for e in triggers:
            if e.weight > strongest_weight:
                strongest_weight = e.weight
                strongest_trigger_desc = e.description or ""
        desc_up = strongest_trigger_desc.upper()
        if "TRUSTEE SALE" in desc_up:
            return ("confirmed", "high",
                    f"Notice of Trustee Sale — foreclosure auction scheduled, forced sale imminent")
        if "DEFAULT" in desc_up:
            return ("confirmed", "high",
                    f"Notice of Default — 90-day foreclosure clock started, near-certain disposition")
        if "LIS PENDENS" in desc_up:
            return ("confirmed", "medium",
                    f"Lis Pendens — litigation pending, may force transaction")
        # Fallthrough for unrecognized adverse-recording types

    # investor_disposition: ChatGPT critique — in-window is a soft state,
    # only OVERDUE holds should confirm. In-window becomes weak/watchlist.
    if family == "investor_disposition":
        is_overdue = False
        for e in triggers:
            dr = e.data_ref or {}
            ew = dr.get("exit_window") or {}
            if ew.get("state") == "overdue":
                is_overdue = True
                break
        if not is_overdue:
            return ("weak", "low",
                    "Investor in typical exit window — real signal but not decision-strong enough to ship as confirmed lead. Watchlist only.")

    # HARD RULE: zero support items means no corroboration — confidence LOW
    if len(supports) == 0:
        return ("confirmed", "low",
                f"Trigger present but zero corroborating support — capped at LOW confidence (net {net:.1f})")

    # Standard confidence ladder (only when supports > 0)
    if net >= 6.0 and len(supports) >= 2:
        return ("confirmed", "high", f"Strong signal with {len(supports)} corroborating supports; net {net:.1f}")
    if net >= 3.5:
        return ("confirmed", "medium", f"Moderate signal; net evidence weight {net:.1f}")
    if net >= 1.5:
        return ("confirmed", "low", f"Weak-but-positive signal; net evidence weight {net:.1f}")

    return ("weak", "low", f"Net evidence weight too low: {net:.1f}")
