"""
SellerSignal v2 — Candidate Search.

Per signal family, search the parcel universe for candidate properties.

Design principle: candidate search is PERMISSIVE (over-include).
Candidate review is STRICT (most die there).

Each search function returns a list of (parcel_id, trigger_hint) tuples.
The trigger_hint carries whatever information the search used so review can
reconstruct the evidence.
"""
from __future__ import annotations
import json, csv, re
from datetime import datetime
from collections import defaultdict
from typing import Optional

from evidence_resolution import is_entity_owner, is_business_entity, is_family_trust


# ═══════════════════════════════════════════════════════════════════════
# INDEXING HELPERS
# ═══════════════════════════════════════════════════════════════════════
def build_person_index(owners_db: dict) -> dict:
    """
    For each parcel, build a token set for each person on title.
    A parcel with "DU JAMES+LINDA LEE" → two persons: {DU, JAMES} and {LINDA, LEE}.
    Returns: {parcel_id: [set_of_tokens_per_person, ...]}
    """
    out = {}
    for pin, info in owners_db.items():
        raw = info.get("owner_name", "")
        if not raw or is_entity_owner(raw):
            continue
        persons = [p.strip() for p in re.split(r'[+&,]', raw) if p.strip()]
        person_token_sets = []
        for person in persons:
            tokens = [t.upper() for t in person.split()
                      if t.isalpha() and len(t) >= 2]
            if len(tokens) >= 2:
                person_token_sets.append(set(tokens))
        if person_token_sets:
            out[pin] = person_token_sets
    return out


def load_deed_chain_by_pin(csv_path: str) -> dict[str, list[dict]]:
    """Build {pin: [deed_row, ...]} from the KC sales CSV."""
    by_pin = defaultdict(list)
    with open(csv_path, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            pin = (row.get("Major", "") or "") + (row.get("Minor", "") or "")
            try:
                dt = datetime.strptime(row.get("DocumentDate", "").split(" ")[0], "%m/%d/%Y")
            except (ValueError, TypeError):
                continue
            try:
                price = int(row.get("SalePrice", "0") or 0)
            except ValueError:
                price = 0
            by_pin[pin].append({
                "date": dt,
                "price": price,
                "seller": (row.get("SellerName", "") or "").strip(),
                "buyer": (row.get("BuyerName", "") or "").strip(),
                "instr": (row.get("SaleInstrument", "") or "").strip(),
                "reason": (row.get("SaleReason", "") or "").strip(),
            })
    return by_pin


# ═══════════════════════════════════════════════════════════════════════
# DEATH / INHERITANCE — candidate search
# ═══════════════════════════════════════════════════════════════════════
def search_death_inheritance_candidates(
    obituary_signals: list[dict],
    person_index: dict[str, list[set[str]]],
    owners_db: dict,
    use_codes: dict[str, dict],
) -> list[dict]:
    """
    For each obit, find residential parcels where token overlap ≥ 2 including the surname.

    Returns list of candidate dicts:
      {parcel_id, signal_family, trigger_hint: {obit, overlap, person_idx}}
    """
    # Junk surnames that commonly false-positive
    JUNK = {"OBITUARY", "CHURCH", "SERVICE", "MEMORIAL", "BURIAL", "FUNERAL"}
    candidates: list[dict] = []

    for obit in obituary_signals:
        name = obit.get("name", "")
        tokens = [t.upper() for t in re.sub(r"['\"]", "", name).split()
                  if t.isalpha() and len(t) >= 2]
        tokens = [t for t in tokens if t not in ("JR", "SR", "II", "III", "IV", "MR", "MRS", "DR")]
        if len(tokens) < 2:
            continue
        surname = tokens[-1]
        if surname in JUNK:
            continue
        obit_tokens = set(tokens)

        for pin, person_sets in person_index.items():
            # Residential-only filter
            if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
                continue
            for idx, ptokens in enumerate(person_sets):
                overlap = obit_tokens & ptokens
                # Require: surname match + at least one other token
                non_surname = overlap - {surname}
                if surname in overlap and len(non_surname) >= 1:
                    candidates.append({
                        "parcel_id": pin,
                        "signal_family": "death_inheritance",
                        "trigger_hint": {
                            "obit": obit,
                            "obit_tokens": sorted(obit_tokens),
                            "overlap_tokens": sorted(overlap),
                            "person_idx": idx,
                        },
                    })

    return candidates


# ═══════════════════════════════════════════════════════════════════════
# INVESTOR DISPOSITION — candidate search
# Real signal: rapid-turnover pattern (2+ arms-length sales within 5 years).
# Entity ownership alone is descriptive, not a signal. That was the v1 mistake.
# ═══════════════════════════════════════════════════════════════════════
def search_investor_disposition_candidates(
    owners_db: dict,
    deed_chain_by_pin: dict[str, list[dict]],
    use_codes: dict[str, dict],
    min_value: int = 1_000_000,
    max_value: int = 30_000_000,
) -> list[dict]:
    """
    Residential-only. Single trigger pattern: ESTATE-TO-INVESTOR.

    The prior arms-length seller held 20+ years as an individual, and the most
    recent acquirer is an entity, within the last 3 years.

    Rationale: this is the one deed pattern where there's a real human seller
    event embedded — the 20+yr individual holder exited (death / retirement /
    estate), AND a professional buyer took it, AND they're approaching the
    rotation window. That IS a signal, not just deed state.

    "Rapid turnover" alone (2 arms-length sales in 5y on residential) is
    normal house-flipping activity and is NOT a seller signal — it's just a
    description of flip inventory. Per the v2 directive, deed events alone
    never originate leads.
    """
    from datetime import datetime as _dt
    candidates: list[dict] = []
    now = _dt.utcnow()

    for pin, info in owners_db.items():
        if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
            continue
        value = info.get("value") or 0
        if not (min_value <= value <= max_value):
            continue

        deeds = deed_chain_by_pin.get(pin, [])
        arms_length = sorted(
            [d for d in deeds if (d.get("price") or 0) > 100_000],
            key=lambda d: d["date"],
        )
        if len(arms_length) < 2:
            continue

        most_recent = arms_length[-1]
        prior = arms_length[-2]

        # Current owner is a BUSINESS entity (flipper-style), not a family trust
        current_owner = info.get("owner_name", "")
        if not is_business_entity(current_owner):
            continue
        if is_family_trust(current_owner):
            continue

        # Entity acquired in the last 3 years (rotation window)
        yrs_since = (now - most_recent["date"]).days / 365.25
        if not (1.0 <= yrs_since <= 3.0):
            continue

        # Most recent buyer is a business entity (not a family trust)
        buyer = most_recent.get("buyer", "")
        if not is_business_entity(buyer) or is_family_trust(buyer):
            continue

        # Prior seller was an individual (not entity, not trust)
        prior_seller = prior.get("seller", "")
        if is_entity_owner(prior_seller):
            continue

        # Prior holder had 20+ years tenure
        if len(arms_length) >= 3:
            prior_held = (prior["date"] - arms_length[-3]["date"]).days / 365.25
        else:
            prior_held = 999  # unknown = assume very long
        if prior_held < 20:
            continue

        candidates.append({
            "parcel_id": pin,
            "signal_family": "investor_disposition",
            "trigger_hint": {
                "pattern": "estate_to_investor",
                "yrs_since_recent_sale": yrs_since,
                "prior_held_years": prior_held,
                "prior_seller": prior.get("seller", ""),
                "most_recent_deed": {k: str(v) for k, v in most_recent.items()},
            },
        })
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# RETIREMENT — candidate search (requires a retirement signal, not just tenure)
# ═══════════════════════════════════════════════════════════════════════
def search_retirement_candidates(
    retirement_signals: list[dict],
    person_index: dict[str, list[set[str]]],
    owners_db: dict,
    use_codes: dict[str, dict],
) -> list[dict]:
    """
    Only produces candidates when we have an actual retirement-announcement signal
    (SERP hit naming an individual) that matches a name on title of a residential parcel.

    Long tenure alone is NOT a trigger — that was a v1 mistake.
    """
    JUNK = {"CORP", "COMPANY", "SERVICE", "GROUP", "LLC"}
    candidates: list[dict] = []

    for signal in retirement_signals:
        name = signal.get("name", "")
        tokens = [t.upper() for t in re.sub(r"['\"]", "", name).split()
                  if t.isalpha() and len(t) >= 2]
        if len(tokens) < 2:
            continue
        surname = tokens[-1]
        if surname in JUNK:
            continue
        sig_tokens = set(tokens)

        for pin, person_sets in person_index.items():
            if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
                continue
            for idx, ptokens in enumerate(person_sets):
                overlap = sig_tokens & ptokens
                non_surname = overlap - {surname}
                if surname in overlap and len(non_surname) >= 1:
                    candidates.append({
                        "parcel_id": pin,
                        "signal_family": "retirement_downsize",
                        "trigger_hint": {"retirement": signal, "overlap": sorted(overlap)},
                    })
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# PRE-LISTING STRUCTURING — candidate search (TRIGGER ONLY, not a lead alone)
# ═══════════════════════════════════════════════════════════════════════
def search_pre_listing_structuring_candidates(
    owners_db: dict,
    deed_chain_by_pin: dict[str, list[dict]],
    use_codes: dict[str, dict],
    max_age_years: float = 1.0,
) -> list[dict]:
    """
    Recent indiv→LLC transfers on residential parcels. Produces candidates for
    review, but these CANNOT become leads on their own — they require
    corroboration from another signal family.
    """
    candidates: list[dict] = []
    now = datetime.utcnow()

    for pin, deeds in deed_chain_by_pin.items():
        if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
            continue
        for row in deeds:
            seller = row.get("seller", "")
            buyer = row.get("buyer", "")
            price = row.get("price", 0) or 0
            row_date = row.get("date")
            if not row_date: continue
            age_years = (now - row_date).days / 365.25
            if age_years > max_age_years:
                continue
            if not is_entity_owner(seller) and is_entity_owner(buyer) and price < 100_000:
                candidates.append({
                    "parcel_id": pin,
                    "signal_family": "pre_listing_structuring",
                    "trigger_hint": {
                        "deed_row": {k: str(v) for k, v in row.items()},
                        "age_years": age_years,
                    },
                })
                break
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# DIVORCE / RELOCATION / FINANCIAL STRESS — not searchable today
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# FAILED SALE ATTEMPT — candidate search
# Reads from a pre-scraped cache of Zillow listing events per parcel.
# Production: the scraper runs as a separate daily job; this module just
# reads the cache. For this session the cache is seeded with 3 real fetches
# + synthetic examples.
# ═══════════════════════════════════════════════════════════════════════
def search_failed_sale_attempt_candidates(
    owners_db: dict,
    use_codes: dict[str, dict],
    zillow_events_by_pin: dict[str, list[dict]],
    lookback_years: float = 2.0,
) -> list[dict]:
    """
    Residential parcels where Zillow shows a listing-removed-no-sale pattern,
    OR a price-struggle pattern with no completed sale.
    """
    from zillow_listings import (
        ListingEvent, detect_failed_sale_attempt, detect_price_decrease_struggle,
    )
    from datetime import datetime

    candidates: list[dict] = []
    for pin, events_dicts in zillow_events_by_pin.items():
        if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
            continue
        if pin not in owners_db:
            continue

        events = []
        for ev in events_dicts:
            try:
                dt = datetime.strptime(ev["date"], "%Y-%m-%d")
                events.append(ListingEvent(
                    date=dt, event_type=ev["event_type"],
                    price=ev.get("price"), source=ev.get("source", "zillow"),
                ))
            except (KeyError, ValueError):
                continue

        failed = detect_failed_sale_attempt(events, lookback_years=lookback_years)
        struggle = detect_price_decrease_struggle(events, lookback_years=lookback_years)

        if failed or struggle:
            candidates.append({
                "parcel_id": pin,
                "signal_family": "failed_sale_attempt",
                "trigger_hint": {
                    "failed_pattern": failed,
                    "struggle_pattern": struggle,
                    "events": [str(e) for e in events],
                },
            })
    return candidates
    """Requires KC Superior Court divorce dockets (ToS-restricted). Returns []."""
    return []


def search_relocation_candidates(*args, **kwargs) -> list[dict]:
    """Requires historical mail-address delta feed (not wired). Returns []."""
    return []


def search_divorce_candidates(*args, **kwargs) -> list[dict]:
    """Requires KC Superior Court divorce dockets (ToS-restricted scrape). Returns []."""
    return []


def search_financial_stress_candidates(*args, **kwargs) -> list[dict]:
    """
    Requires KC Recorder NOD/lis pendens data. KC LandmarkWeb ToS prohibits
    automated queries, so this requires ATTOM / DataTree / PropertyRadar /
    TitleTools subscription. Returns [].
    """
    return []


# ═══════════════════════════════════════════════════════════════════════
# ABSENTEE OUT-OF-STATE — candidate search (new)
# ═══════════════════════════════════════════════════════════════════════
def search_absentee_oos_candidates(
    owners_db: dict,
    mailing_addresses: dict[str, dict],
    use_codes: dict[str, dict],
    min_tenure_years: float = 10.0,
    min_value: int = 1_500_000,
    max_value: int = 30_000_000,
) -> list[dict]:
    """
    Residential parcels where the owner's mailing address is out of WA state
    AND tenure is 10+ years (proved-up ownership, not a recent acquisition).

    The tenure filter rules out recent out-of-state buyers (2nd-home purchasers).
    Long OOS hold = the property has become administratively distant.

    This is a CANDIDATE search only — decision activation still required downstream.
    """
    candidates: list[dict] = []
    for pin, info in owners_db.items():
        if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
            continue
        if is_entity_owner(info.get("owner_name", "")):
            continue  # individuals only for relocation signal
        tenure = info.get("tenure_years") or 0
        if tenure < min_tenure_years:
            continue
        value = info.get("value") or 0
        if not (min_value <= value <= max_value):
            continue

        mail_info = mailing_addresses.get(pin, {})
        mail_city = (mail_info.get("mail_city") or "").upper()
        if not mail_city or "WA" in mail_city:
            continue  # in-state or unknown — not an OOS signal

        candidates.append({
            "parcel_id": pin,
            "signal_family": "absentee_oos_disposition",
            "trigger_hint": {
                "mail_city": mail_city,
                "mail_zip": mail_info.get("mail_zip", ""),
                "tenure_years": tenure,
            },
        })
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# HIGH-EQUITY LONG-TENURE — candidate search (new)
# ═══════════════════════════════════════════════════════════════════════
def search_high_equity_long_tenure_candidates(
    owners_db: dict,
    deed_chain_by_pin: dict,
    use_codes: dict[str, dict],
    min_tenure_years: float = 20.0,
    min_equity_multiple: float = 3.0,
    min_value: int = 2_000_000,
    max_value: int = 30_000_000,
) -> list[dict]:
    """
    Residential parcels where owner (individual) has 20+ year tenure AND
    current AV is 3x+ their purchase price. These owners face a tax-timing
    decision: Sec 121 exclusion caps at $500k joint, so multi-million equity
    owners have already maxed the benefit.

    Combined with a life-event trigger (death, retirement, relocation), this
    is a strong motivator. Without a life-event trigger, it's a watchlist
    not a lead — enforced by `can_promote_to_lead` semantics at review time.
    """
    candidates: list[dict] = []
    for pin, info in owners_db.items():
        if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
            continue
        if is_entity_owner(info.get("owner_name", "")):
            continue
        tenure = info.get("tenure_years") or 0
        if tenure < min_tenure_years:
            continue

        value = info.get("value") or 0
        try:
            purchase_price = int(info.get("sale_price") or 0)
        except (TypeError, ValueError):
            purchase_price = 0
        if not (min_value <= value <= max_value):
            continue
        if purchase_price < 100_000:
            continue  # can't compute equity ratio

        multiple = value / purchase_price
        if multiple < min_equity_multiple:
            continue

        candidates.append({
            "parcel_id": pin,
            "signal_family": "high_equity_long_tenure",
            "trigger_hint": {
                "tenure_years": tenure,
                "purchase_price": purchase_price,
                "current_value": value,
                "equity_multiple": multiple,
            },
        })
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════
def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    """
    A parcel can appear multiple times under the same signal family
    (e.g., two obituaries both matched it). Keep the first occurrence per
    (signal_family, parcel_id) — review will handle evidence aggregation.
    """
    seen: set = set()
    out = []
    for c in candidates:
        key = (c["signal_family"], c["parcel_id"])
        if key in seen: continue
        seen.add(key)
        out.append(c)
    return out
