"""
Raw signal matcher.

Reads unmatched rows from raw_signals_v3, resolves party_names against
owner_canonical_v3, and writes matches to raw_signal_matches_v3.

This is the FINAL stage of the harvester pipeline:
    harvester -> raw_signals_v3 -> [matcher] -> raw_signal_matches_v3
                                                         │
                                                         └─> served via
                                                             /api/harvest/
                                                             matches/{zip}

Design (Path B):
- raw_signal_matches_v3 is the authoritative source of truth for
  harvester-lineage matches. We do NOT write to investigations_v3 —
  that table is the SerpAPI-era signal store and has different schema
  assumptions (rollup flags, action categories, TTL, single-row-per-pin).
  Mixing lineages risks blasting SerpAPI state on upsert.
- Loops raw_signals with matched_at IS NULL
- For each signal, dispatches to a type-specific matcher based on signal_type
- Reuses the existing ingest/legal_filings.py matchers so the name-match
  logic doesn't diverge between SerpAPI-era and harvester-era code
- Writes raw_signal_matches_v3 rows for each match
- Updates raw_signals_v3 matched_at + match_count
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from backend.ingest.legal_filings import (
    DivorceFiling,
    RecorderDocument,
    match_divorce_to_parcels,
    match_recorder_to_parcels,
)

log = logging.getLogger(__name__)


# ─── Top-level entry point ─────────────────────────────────────────────

def process_unmatched(
    supa,
    zip_filter: Optional[str] = None,
    batch_size: int = 100,
    max_batches: int = 50,
) -> dict:
    """
    Process up to (batch_size * max_batches) unmatched raw_signals.

    zip_filter: if set (e.g. '98004'), only write matches for parcels in
                that ZIP. Harvester runs KC-wide but the pilot scopes
                to 98004.

    Returns summary stats.
    """
    stats = {
        "processed":    0,
        "matched":      0,
        "signals_none": 0,
        "by_type":      {},
        "errors":       [],
    }

    # Pre-load owners_db for the zip filter (or the whole KC coverage)
    owners_db, use_codes = _load_owners_db(supa, zip_filter)
    if not owners_db:
        log.warning("No owners loaded — check canonicalization status")
        stats["errors"].append("No owners in owners_db")
        return stats

    log.info(f"Loaded {len(owners_db)} canonicalized owners for matching")

    batch_n = 0
    while batch_n < max_batches:
        rows = _fetch_unmatched_batch(supa, batch_size)
        if not rows:
            log.info("No more unmatched raw_signals")
            break

        for row in rows:
            try:
                n_matched = _process_one(
                    supa, row, owners_db, use_codes, zip_filter
                )
                stats["processed"] += 1
                if n_matched > 0:
                    stats["matched"] += 1
                    stats["by_type"][row["signal_type"]] = (
                        stats["by_type"].get(row["signal_type"], 0) + 1
                    )
                else:
                    stats["signals_none"] += 1
            except Exception as e:
                log.exception(f"Match failed for raw_signal {row['id']}")
                stats["errors"].append({
                    "raw_signal_id": row["id"],
                    "error":         str(e),
                })

        batch_n += 1

    return stats


# ─── Internals ─────────────────────────────────────────────────────────

def _load_owners_db(supa, zip_filter: Optional[str]) -> tuple[dict, dict]:
    """
    Load canonicalized owners into the shape the legacy matchers expect.

    Returns (owners_db, use_codes) where:
      owners_db[pin] = {owner_name, co_owner_name, canonicalized, ...}
      use_codes[pin] = {prop_type: 'R'|'C'|..., ...}

    For the pilot we scope to a single ZIP. Full matcher runs would load
    all covered ZIPs, or process per-ZIP in a loop.

    Fix 2: Exclude government-owned parcels. These parcels can't be sold
    and lead to false-positive matches when court filings name
    "STATE OF WASHINGTON" or similar as a party (e.g. state-initiated
    child support enforcement). Filter applies to:
      - owner_type='gov' as stamped by the canonicalizer
      - owner_name containing government patterns (WSDOT, State of,
        City of, County of, etc.)
    """
    # Parcels (filtered to ZIP if provided) — we need prop_type/use_code
    # for the divorce matcher's residential filter
    PAGE = 1000
    offset = 0
    parcels: list[dict] = []
    while True:
        q = supa.table('parcels_v3').select(
            'pin, owner_name, owner_type, prop_type, zip_code'
        )
        if zip_filter:
            q = q.eq('zip_code', zip_filter)
        batch = q.range(offset, offset + PAGE - 1).execute().data or []
        parcels.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 200000:
            break

    # Filter out gov-owned parcels — they can't be seller signals
    parcels = [p for p in parcels if not _is_government_parcel(p)]

    # owner_canonical (for each pin, the parsed owner entities)
    pins = [p['pin'] for p in parcels]
    canonical_by_pin = _load_canonical_for_pins(supa, pins)

    owners_db: dict = {}
    use_codes: dict = {}
    for p in parcels:
        pin = p['pin']
        owners_db[pin] = {
            'owner_name':     (p.get('owner_name') or '').upper(),
            'co_owner_name':  '',  # parcels_v3 doesn't split co-owner separately
            'canonicalized':  canonical_by_pin.get(pin),
        }
        use_codes[pin] = {
            'prop_type': p.get('prop_type') or 'R',  # default to residential
        }

    return owners_db, use_codes


def _is_government_parcel(parcel: dict) -> bool:
    """
    True if this parcel is owned by a government entity and should be
    excluded from matching.

    Checks:
      1. owner_type='gov' (preferred — comes from canonicalizer)
      2. owner_name patterns: WSDOT, State of, City of, County of,
         Of Washington State, State Dot, US of America, King County,
         Port of, Public Utility, Sound Transit, Metro, School District
    """
    if (parcel.get('owner_type') or '').lower() == 'gov':
        return True

    name = (parcel.get('owner_name') or '').upper()
    if not name:
        return False

    gov_patterns = (
        "WSDOT",
        "STATE OF",
        "CITY OF",
        "COUNTY OF",
        "OF WASHINGTON STATE",
        "STATE DOT",
        "US OF AMERICA",
        "UNITED STATES",
        "KING COUNTY",
        "PORT OF",
        "PUBLIC UTILITY",
        "SOUND TRANSIT",
        "SCHOOL DISTRICT",
        "METRO TRANSIT",
        "FEDERAL HIGHWAY",
        "DEPT OF TRANSPORT",
        "DEPT OF ECOLOGY",
        "WA STATE",
        "BELLEVUE CITY",
        "SEATTLE CITY",
    )
    return any(p in name for p in gov_patterns)


def _load_canonical_for_pins(supa, pins: list[str]) -> dict:
    """
    Batch-fetch owner_canonical_v3 rows for a set of pins.
    Returns {pin: canonical_row}.
    """
    out: dict = {}
    CHUNK = 500
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i : i + CHUNK]
        rows = (supa.table('owner_canonical_v3')
                .select('*')
                .in_('pin', chunk)
                .execute().data) or []
        for r in rows:
            out[r['pin']] = r
    return out


def _fetch_unmatched_batch(supa, batch_size: int) -> list[dict]:
    """Pull next batch of raw_signals with matched_at IS NULL."""
    rows = (supa.table('raw_signals_v3')
            .select('*')
            .is_('matched_at', 'null')
            .order('harvested_at', desc=False)
            .limit(batch_size)
            .execute()).data or []
    return rows


def _process_one(
    supa,
    row: dict,
    owners_db: dict,
    use_codes: dict,
    zip_filter: Optional[str],
) -> int:
    """
    Match a single raw_signal to parcels. Write match rows to
    raw_signal_matches_v3. Returns number of parcels matched.

    Architecture note (Path B): harvester matches are NOT promoted to
    investigations_v3. That table is the SerpAPI-era signal store; its
    schema is tightly coupled to that lineage (rollup flags, action
    categories, TTL, etc). Mixing harvester and SerpAPI signals into the
    same row would require a merge strategy and risk blasting SerpAPI
    state. Instead, raw_signal_matches_v3 is the source of truth for
    harvester lineage, exposed via /api/harvest/matches/{zip}.
    """
    signal_type = row["signal_type"]
    dispatcher = _DISPATCH.get(signal_type)
    if not dispatcher:
        # Unknown signal type — mark processed, no match
        _mark_matched(supa, row["id"], match_count=0)
        return 0

    candidates = dispatcher(row, owners_db, use_codes)
    # Filter to zip if provided (paranoia — owners_db was already zip-filtered)
    if zip_filter:
        candidates = [c for c in candidates if c.get("parcel_id") in owners_db]

    # Surname-required post-filter. The legacy name_match() uses
    # token-overlap with min_overlap=2 which is too permissive: it matches
    # "Robert Lee Harris" to "Robert Lee Steil" (overlap={Robert,Lee})
    # and "Sandra Lee Westling" to "Sandra Lee Stark" (overlap={Sandra,Lee})
    # because common first+middle names share 2 tokens.
    #
    # This filter enforces the basic genealogical requirement: the surname
    # of a signal party MUST match the surname of the parcel owner. For
    # individuals, this is the last token of each name. For trusts/LLCs,
    # we check if the decedent's surname appears anywhere in the entity name
    # (handles "Chen Family Trust" matching "Howard Tzu-Hao Chen").
    #
    # The gate now returns a STRENGTH ("strict" / "weak") rather than a
    # bool. Common-surname-only matches with no distinctive token overlap
    # get downgraded to "weak" so they survive for agent review via
    # include_weak=true but don't pollute the default strict list.
    #
    # Exclude parties marked as predeceased (from obituary "preceded in
    # death by X" sentences). They're already dead — surname-matching them
    # to a living parcel owner would create noise, not leads.
    parties = [
        p for p in (row.get('party_names') or [])
        if not (isinstance(p, dict)
                and str(p.get('role', '')).startswith('predeceased_'))
    ]
    gate_strengths: dict = {}
    filtered_candidates = []
    for c in candidates:
        strength = _surname_gate(c["parcel_id"], owners_db, parties)
        if strength is None:
            continue
        gate_strengths[c["parcel_id"]] = strength
        filtered_candidates.append(c)
    candidates = filtered_candidates

    if not candidates:
        _mark_matched(supa, row["id"], match_count=0)
        return 0

    # Write raw_signal_matches_v3 rows. The effective strength is the
    # WEAKER of (dispatcher's initial strength) and (surname gate's
    # strength). So a probate with strict dispatch + weak gate = weak.
    def _combine(dispatcher_strength: str, gate_strength: str) -> str:
        if dispatcher_strength == "weak" or gate_strength == "weak":
            return "weak"
        return "strict"

    match_rows = [
        {
            "raw_signal_id":  row["id"],
            "pin":            c["parcel_id"],
            "match_strength": _combine(
                c.get("trigger_hint", {}).get("match_strength", "strict"),
                gate_strengths[c["parcel_id"]],
            ),
            "match_method":   f"legacy::{signal_type}",
        }
        for c in candidates
    ]
    (supa.table('raw_signal_matches_v3')
     .upsert(match_rows, on_conflict='raw_signal_id,pin')
     .execute())

    # Mark raw_signal processed. Note: this must happen AFTER the match
    # rows are written, so if match-write fails we don't falsely mark
    # the signal as processed.
    _mark_matched(supa, row["id"], match_count=len(match_rows))

    return len(match_rows)


def _mark_matched(supa, raw_signal_id: int, match_count: int):
    (supa.table('raw_signals_v3')
     .update({
         'matched_at':  datetime.utcnow().isoformat(),
         'match_count': match_count,
     })
     .eq('id', raw_signal_id)
     .execute())


# ─── Dispatch table ────────────────────────────────────────────────────

def _dispatch_divorce(row, owners_db, use_codes):
    """Adapt a divorce RawSignal to DivorceFiling for the legacy matcher."""
    parties = row.get('party_names') or []
    if len(parties) < 2:
        return []

    # Build DivorceFiling expected by legacy matcher
    event_date = row.get('event_date')
    if isinstance(event_date, str):
        event_date = datetime.fromisoformat(event_date).date()
    filing = DivorceFiling(
        case_number=row.get('document_ref') or "",
        filing_date=datetime.combine(event_date, datetime.min.time())
                    if event_date else datetime.utcnow(),
        case_type="Dissolution",   # we assume dissolution; harvester pre-filtered
        petitioner_name=parties[0].get('raw', ''),
        respondent_name=parties[1].get('raw', ''),
    )
    return match_divorce_to_parcels([filing], owners_db, use_codes)


def _dispatch_probate(row, owners_db, use_codes):
    """
    Probate / obituary matching.

    Two match layers:

    1) DECEDENT vs all parcel owners — the primary signal. Finds the
       parcel the decedent owned. Labeled signal_family="probate_pending".
       Match strength: strict (full name match).

    2) SURVIVORS vs all parcel owners — secondary. Heirs who already
       own property in the target zip are high-signal contacts even
       before the estate is settled. E.g. a decedent's son who already
       owns a Bellevue condo is the likeliest ultimate seller of both
       the inherited home and potentially his own.

       Labeled signal_family="probate_heir". Match strength is
       explicitly weak — surname-inferred survivor names are noisier
       than full-name decedent matches. Downstream filters can decide
       whether to surface these.
    """
    from backend.ingest.legal_filings import name_match

    parties = row.get('party_names') or []
    if not parties:
        return []

    decedent_raw = parties[0].get('raw', '')
    if not decedent_raw:
        return []

    candidates = []

    # Layer 1: decedent match
    for pin, info in owners_db.items():
        if use_codes.get(pin, {}).get('prop_type', '') != 'R':
            continue
        owner_name = info.get('owner_name', '')
        if not owner_name:
            continue

        if name_match(decedent_raw, owner_name):
            candidates.append({
                "parcel_id":     pin,
                "signal_family": "probate_pending",
                "trigger_hint": {
                    "case_number":    row.get('document_ref'),
                    "filing_date":    (row.get('event_date') or ''),
                    "decedent":       decedent_raw,
                    "match_strength": "strict",
                },
            })

    # Layer 2: survivor matches
    # Only applies when survivors were extracted (obituary signals — probate
    # court signals rarely have survivor_* roles since we don't harvest them).
    #
    # Dedupe note: the matches table is unique on (raw_signal_id, pin). If a
    # decedent AND a survivor both match the same pin, upsert would overwrite
    # the stronger decedent match with the weaker survivor match. So we skip
    # survivor candidates for any pin the decedent already matched — the
    # useful case is survivors matching OTHER pins.
    decedent_matched_pins = {c["parcel_id"] for c in candidates}

    survivor_parties = [
        p for p in parties
        if (p.get('role') or '').startswith('survivor_')
    ]
    for sp in survivor_parties:
        survivor_raw = sp.get('raw', '')
        if not survivor_raw:
            continue
        # Skip single-token names. If _extract_survivor_names couldn't infer
        # a surname for this party, it's too ambiguous to match (e.g. "Liz"
        # alone would collide with every Elizabeth in King County).
        if len(survivor_raw.split()) < 2:
            continue

        for pin, info in owners_db.items():
            if pin in decedent_matched_pins:
                continue  # decedent already owns this — don't shadow
            if use_codes.get(pin, {}).get('prop_type', '') != 'R':
                continue
            owner_name = info.get('owner_name', '')
            if not owner_name:
                continue
            if name_match(survivor_raw, owner_name):
                candidates.append({
                    "parcel_id":     pin,
                    "signal_family": "probate_heir",
                    "trigger_hint": {
                        "case_number":    row.get('document_ref'),
                        "filing_date":    (row.get('event_date') or ''),
                        "decedent":       decedent_raw,
                        "survivor":       survivor_raw,
                        "survivor_role":  sp.get('role'),
                        # Heir-on-parcel matches are surname-inferred → weak.
                        # Elevate only when the name tokens are unusually rare.
                        "match_strength": "weak",
                    },
                })

    return candidates


_DISPATCH = {
    "divorce":      _dispatch_divorce,
    "probate":      _dispatch_probate,
    # Obituary matches the same way as probate: single decedent party
    # vs all parcel owners. Surname gate applies equally. The difference
    # between the two is purely signal-source provenance, handled via
    # source_type tagging in raw_signals_v3 (signal_source="obituary_rss"
    # vs "kc_superior_court") — scoring can weight them differently.
    "obituary":     _dispatch_probate,
    # Future: nod, lis_pendens, trustee_sale (via match_recorder_to_parcels),
    # llc_officer_change
}


# ─── Surname gate ──────────────────────────────────────────────────────

# Trust/LLC/company owner-name noise tokens to strip before surname lookup
_ENTITY_NOISE = {
    # Entity-type words
    "TRUST", "TRUSTS", "FAMILY", "REVOCABLE", "IRREVOCABLE", "LIVING",
    "TESTAMENTARY", "BYPASS", "CREDIT", "MARITAL", "DISCLAIMER", "BENEFICIARY",
    "SURVIVOR", "SURVIVORS", "RESIDUE", "RESIDUARY", "DECLARATION", "AGREEMENT",
    "SPECIAL", "NEEDS", "SUPPLEMENTAL", "CHARITABLE", "REMAINDER", "EDUCATION",
    "DESCENDANTS", "GENERATION", "SKIPPING", "GRAT", "CLAT", "CRUT", "CRAT",
    # Trust-document boilerplate (new — kills Kramer-style cascades)
    "UNDER", "WILL", "WILLS", "LAST", "TESTAMENT", "FBO", "BENEFIT", "BENEFITS",
    "DECEDENT", "DECEASED", "LATE", "BEHALF", "DULY", "OTHER", "USE",
    "REV", "TST", "LWT", "REVOCABEL",  # LWT = "last will and testament", REVOCABEL = common misspelling
    # Corp forms
    "LLC", "L.L.C.", "LP", "LLP", "INC", "INCORPORATED", "CORP", "CORPORATION",
    "CO", "COMPANY", "HOLDINGS", "GROUP", "PARTNERS", "PARTNERSHIP",
    "ASSOCIATES", "ASSOCIATION", "PROPERTIES", "PROPERTY", "REALTY", "REAL",
    "ESTATE", "ESTATES", "INVESTMENTS", "INVESTMENT", "VENTURES", "ENTERPRISES",
    # Common entity modifiers
    "OF", "THE", "AND", "&", "FOR", "BY",
    "ET", "AL", "ANO", "JR", "SR", "II", "III", "IV",
    "DTD", "DATED", "UTD", "UDT", "UTA", "U/W",
    "TTEE", "TRUSTEE", "CO-TRUSTEE", "SUCCESSOR", "CY", "TTE",  # TTE = trustee variant
}

# Common US surnames (top ~60 by census frequency) + common Asian-American
# surnames with heavy KC presence. When a match between owner and party
# ONLY shares a common surname, we require additional distinctive-token
# overlap to prevent cascades like "Bradford Lee Smith" → "Jason Lee Smith".
COMMON_SURNAMES = {
    # Top 50 US surnames
    "SMITH", "JOHNSON", "WILLIAMS", "BROWN", "JONES", "GARCIA", "MILLER",
    "DAVIS", "RODRIGUEZ", "MARTINEZ", "HERNANDEZ", "LOPEZ", "GONZALEZ",
    "WILSON", "ANDERSON", "THOMAS", "TAYLOR", "MOORE", "JACKSON", "MARTIN",
    "LEE", "PEREZ", "THOMPSON", "WHITE", "HARRIS", "SANCHEZ", "CLARK",
    "RAMIREZ", "LEWIS", "ROBINSON", "WALKER", "YOUNG", "ALLEN", "KING",
    "WRIGHT", "SCOTT", "TORRES", "NGUYEN", "HILL", "FLORES", "GREEN",
    "ADAMS", "NELSON", "BAKER", "HALL", "RIVERA", "CAMPBELL", "MITCHELL",
    "CARTER", "ROBERTS",
    # Top 51-100 US surnames (important Bellevue/KC presence: Parker,
    # Peterson, Howard, Morgan, Bailey, Reed, Edwards, Phillips, Evans,
    # Turner, Cook, Rogers, Morgan, Ross, Foster, James, Bennett)
    "GOMEZ", "PHILLIPS", "EVANS", "TURNER", "DIAZ", "PARKER", "CRUZ",
    "EDWARDS", "COLLINS", "REYES", "STEWART", "MORRIS", "MORALES",
    "MURPHY", "COOK", "ROGERS", "GUTIERREZ", "ORTIZ", "MORGAN", "COOPER",
    "PETERSON", "BAILEY", "REED", "KELLY", "HOWARD", "RAMOS", "COX",
    "WARD", "RICHARDSON", "WATSON", "BROOKS", "CHAVEZ", "WOOD", "JAMES",
    "BENNETT", "GRAY", "MENDOZA", "RUIZ", "HUGHES", "PRICE", "ALVAREZ",
    "CASTILLO", "SANDERS", "PATEL", "MYERS", "LONG", "ROSS", "FOSTER",
    "JIMENEZ",
    # Heavy Asian-American presence in KC (Bellevue/Redmond/Sammamish).
    # NOTE: HAN intentionally excluded — it's more commonly a given-name
    # fragment (Wei-Han, Po-Han) than a surname in Chinese contexts.
    "CHEN", "KIM", "WANG", "LI", "LIN", "ZHANG", "WU", "CHANG", "LIU",
    "HUANG", "YANG", "CHO", "PARK", "CHOI", "JUNG", "KANG",
    # Common Vietnamese
    "TRAN", "PHAM", "HUYNH", "HOANG", "PHAN",
}

# Common given (first) names — when both owner and party tokens overlap
# only on first-name tokens (no surname), that's not a real match. E.g.
# Donald Carlson Trust matching Donald Esfeld probate via shared "Donald".
COMMON_FIRST_NAMES = {
    # Top male given names
    "JAMES", "JOHN", "ROBERT", "MICHAEL", "WILLIAM", "DAVID", "RICHARD",
    "JOSEPH", "THOMAS", "CHARLES", "CHRISTOPHER", "DANIEL", "MATTHEW",
    "ANTHONY", "DONALD", "MARK", "PAUL", "STEVEN", "ANDREW", "KENNETH",
    "GEORGE", "JOSHUA", "KEVIN", "BRIAN", "EDWARD", "RONALD", "TIMOTHY",
    "JASON", "JEFFREY", "RYAN", "GARY", "NICHOLAS", "ERIC", "JONATHAN",
    "STEPHEN", "LARRY", "JUSTIN", "SCOTT", "BRANDON", "FRANK", "BENJAMIN",
    "GREGORY", "SAMUEL", "RAYMOND", "PATRICK", "ALEXANDER", "JACK", "DENNIS",
    "JERRY", "TYLER", "AARON", "JOSE", "HENRY", "ADAM", "DOUGLAS", "NATHAN",
    "PETER", "ZACHARY", "KYLE", "NOAH", "ALAN", "ETHAN", "JEREMY", "WAYNE",
    "KEITH", "CHRISTIAN", "ROGER", "TERRY", "ARTHUR", "SEAN", "LAWRENCE",
    "JESSE", "AUSTIN", "JOE", "HAROLD", "JORDAN", "BRYAN", "BILLY", "BRUCE",
    "ALBERT", "WILLIE", "GABRIEL", "LOGAN", "ALAN", "JUAN", "CARL", "RALPH",
    "HOWARD",
    # Top female given names
    "MARY", "PATRICIA", "JENNIFER", "LINDA", "ELIZABETH", "BARBARA", "SUSAN",
    "JESSICA", "SARAH", "KAREN", "LISA", "NANCY", "BETTY", "SANDRA",
    "MARGARET", "ASHLEY", "KIMBERLY", "EMILY", "DONNA", "MICHELLE", "CAROL",
    "AMANDA", "MELISSA", "DEBORAH", "STEPHANIE", "DOROTHY", "REBECCA",
    "SHARON", "LAURA", "CYNTHIA", "AMY", "KATHLEEN", "ANGELA", "SHIRLEY",
    "BRENDA", "PAMELA", "NICOLE", "ANNA", "SAMANTHA", "KATHERINE", "CHRISTINE",
    "HELEN", "DEBRA", "RACHEL", "CAROLYN", "JANET", "MARIA", "CATHERINE",
    "HEATHER", "DIANE", "OLIVIA", "JULIE", "JOYCE", "VICTORIA", "RUTH",
    "VIRGINIA", "LAUREN", "KELLY", "CHRISTINA", "JOAN", "EVELYN", "JUDITH",
    "ANDREA", "HANNAH", "JACQUELINE", "GLORIA", "JEAN", "KATHRYN", "ALICE",
    "TERESA", "DORIS", "SARA", "JANICE", "MARILYN", "MARIE", "LESLEY",
    "MARTHA", "LOIS", "JEANNE", "JANE", "SUZAN", "SUZANNE",
    # Middle-name fragments commonly appearing
    "LEE", "ANN", "ANNE", "MAY", "JO", "KAY", "SUE",
}


def _distinctive_tokens(raw: str) -> set:
    """
    Extract tokens that are NOT in our common-surname OR common-first-name
    OR entity-noise sets. These are the "distinctive" tokens — names,
    words, or identifiers that are unlikely to coincidentally overlap
    between unrelated people.

    Splits on whitespace AND hyphens so that hyphenated Korean/Chinese
    given names align correctly:
      "Chia Tzu Chen"     → {"CHIA", "TZU", "CHEN"}
      "Howard Tzu-Hao Chen" → {"HOWARD", "TZU", "HAO", "CHEN"}

    Then filters out common-first-name, common-surname, and entity-noise
    tokens to leave only distinctive ones:
      {"CHIA", "TZU", "CHEN"}            → {"CHIA", "TZU"}         (CHEN common)
      {"HOWARD", "TZU", "HAO", "CHEN"}   → {"TZU", "HAO"}          (HOWARD common, CHEN common)
      {"DAVID", "PARKER"}                → {}                       (both common)
      {"BRADFORD", "LEE", "SMITH"}       → {"BRADFORD"}             (LEE common, SMITH common)

    The distinctive-overlap check then asks: do both names share at
    least one distinctive token? If not, surname-only overlap is
    insufficient evidence.
    """
    if not raw:
        return set()
    import re
    # Split on whitespace, hyphens, punctuation — all as word separators
    tokens = re.split(r"[\s+,./()\-']+", raw.upper())
    tokens = [t for t in tokens if t and len(t) > 1 and t.isalpha()]
    return {
        t for t in tokens
        if t not in COMMON_SURNAMES
        and t not in COMMON_FIRST_NAMES
        and t not in _ENTITY_NOISE
    }


def _extract_surnames(raw: str) -> set:
    """
    Best-effort surname extraction. Returns a set of uppercase candidate
    surnames from a name string.

    For "HOWARD TZU-HAO CHEN"           → {"CHEN"}
    For "SMITH, JOHN"                   → {"SMITH"}
    For "Chen Family Trust +Wei Tzu+"   → {"CHEN", "TZU"}  (trust with names)
    For "ABC Holdings LLC"              → {"ABC"}          (LLC words stripped)
    For "John K Anderson"               → {"ANDERSON"}
    For "Donald And Lesley Carlson Trust +Conrad Jeannie+"
                                         → {"CARLSON", "CONRAD"}  (first names filtered)

    For entity names (Trust/LLC/etc.), we return ALL non-noise non-first-name
    tokens as candidate surnames. Filtering common first names prevents
    false-positive matches where only a shared Donald or Jeannie causes
    a match between unrelated trusts.
    """
    if not raw:
        return set()

    raw_upper = raw.upper()

    # "LAST, FIRST" form — surname is before the comma
    if "," in raw_upper:
        surname = raw_upper.split(",", 1)[0].strip()
        if surname:
            return {surname}

    # Extract alphabetic tokens, drop entity noise
    import re
    tokens = re.findall(r"[A-Z][A-Z'\-]+", raw_upper)
    tokens = [t for t in tokens if t not in _ENTITY_NOISE and len(t) > 1]

    if not tokens:
        return set()

    had_entity_noise = any(
        word in raw_upper.split()
        for word in ("TRUST", "LLC", "INC", "CORP", "FAMILY", "ESTATE")
    )

    if had_entity_noise:
        # For entities: return all non-noise tokens as surname candidates,
        # but exclude obvious first names so that a shared "Donald" between
        # unrelated trusts doesn't cause a false match.
        surname_candidates = {t for t in tokens if t not in COMMON_FIRST_NAMES}
        # If first-name filter would leave us with nothing, fall back to
        # all tokens (some names ARE common first names, e.g. "James Trust")
        return surname_candidates if surname_candidates else set(tokens)

    # Individual: last token is surname
    return {tokens[-1]}


def _surname_gate(pin: str, owners_db: dict, signal_parties: list) -> "str | None":
    """
    Returns the match strength based on surname + distinctive token overlap:
      - "strict": overlap includes an uncommon surname, OR overlap is on a
                  common surname but distinctive-token corroboration exists
      - "weak":   overlap is only on a common surname with no distinctive
                  token corroboration (e.g. Bradford Lee Smith vs Jason
                  Lee Smith — both Smith families but clearly different people)
      - None:     no surname overlap at all — reject outright

    Callers use this to stamp match_strength; agents filter weak matches
    via include_weak=false (default).
    """
    info = owners_db.get(pin) or {}
    owner_name = info.get('owner_name', '')
    owner_surnames = _extract_surnames(owner_name)
    if not owner_surnames:
        return None

    owner_distinctive_cache = None
    saw_weak = False

    for p in signal_parties:
        party_raw = p.get('raw', '') if isinstance(p, dict) else ''
        party_surnames = _extract_surnames(party_raw)
        overlap = party_surnames & owner_surnames
        if not overlap:
            continue

        # Uncommon surname overlap → strict match
        if any(s not in COMMON_SURNAMES for s in overlap):
            return "strict"

        # Overlap is all common surnames — check for distinctive corroboration
        if owner_distinctive_cache is None:
            owner_distinctive_cache = _distinctive_tokens(owner_name)
        party_distinctive = _distinctive_tokens(party_raw)
        if owner_distinctive_cache & party_distinctive:
            return "strict"

        # No distinctive overlap — weak match (but keep going; a later
        # party might have a stronger match)
        saw_weak = True

    return "weak" if saw_weak else None
