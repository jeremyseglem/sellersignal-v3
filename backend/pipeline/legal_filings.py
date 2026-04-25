"""
SellerSignal v2 — Legal filings ingest.

Consumes CSV exports from:
  1. KC Superior Court KC Script Portal (Family Law dissolution filings)
     https://dja-prd-ecexap1.kingcounty.gov/node/411?caseType=211110

  2. KC Recorder LandmarkWeb (NOD / Lis Pendens / Trustee Sale)
     https://recordsearch.kingcounty.gov/LandmarkWeb → Record Date Search

Produces candidates for `divorce_unwinding` and `financial_stress` signal
families. Matching logic is name-based for court filings (no parcel link)
and parcel-based for recorder documents (direct PIN on record).

Workflow is weekly human-driven pulls — the ToS permits targeted searches,
prohibits automated mass-downloading. This module only consumes the exports.
"""
from __future__ import annotations
import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# ─── Name normalization ──────────────────────────────────────────────────
_NAME_NOISE = re.compile(r"[^A-Z\s]")
_WHITESPACE = re.compile(r"\s+")

# Common suffixes / prefixes to strip
_TITLE_TOKENS = {"MR", "MRS", "MS", "DR", "JR", "SR", "II", "III", "IV", "ESQ"}

# Family-trust tokens we want to strip so a trust-titled owner still matches
# when one of the trustees is named in a filing
_TRUST_TOKENS = {"TRUSTEE", "TRUSTEES", "TTEE", "TTEES", "TRT", "TRUST",
                 "FAMILY", "REVOCABLE", "LIVING", "ET", "ANO", "AL"}


def normalize_name(name: str) -> set[str]:
    """Return a set of meaningful tokens from a name string, uppercased."""
    if not name:
        return set()
    up = name.upper()
    up = _NAME_NOISE.sub(" ", up)
    up = _WHITESPACE.sub(" ", up).strip()
    tokens = {t for t in up.split() if len(t) >= 2}
    tokens -= _TITLE_TOKENS
    tokens -= _TRUST_TOKENS
    return tokens


def _ordered_tokens(name: str) -> list[str]:
    """Meaningful tokens in document order — surname extraction."""
    if not name:
        return []
    up = _NAME_NOISE.sub(" ", name.upper())
    up = _WHITESPACE.sub(" ", up).strip()
    out: list[str] = []
    for t in up.split():
        if len(t) < 2:
            continue
        if t in _TITLE_TOKENS or t in _TRUST_TOKENS:
            continue
        out.append(t)
    return out


def _extract_surname(name: str) -> str:
    """Last meaningful token — works for 'IN RE FIRST MIDDLE LAST' decedent
    names and for standard First-Last filer/respondent names."""
    toks = _ordered_tokens(name)
    return toks[-1] if toks else ""


# ═══════════════════════════════════════════════════════════════════════
# LEGACY string-to-string matcher (retained for back-compat only)
# ═══════════════════════════════════════════════════════════════════════
def name_match(filing_name: str, owner_name: str,
               min_overlap: int = 2) -> bool:
    """
    LEGACY: string-to-string strict matcher.

    Use this only when no canonical record exists for the owner (pre-
    canonicalizer parcels, or low-confidence canonical rows). Requires
    surname equality AND at least one given-name overlap — stricter than
    the old 2-token-overlap rule to eliminate false positives like
    'ROBERT LEE HARRIS' ↔ 'Robert Lee Steil'.

    Prefer `match_canonical()` whenever owner_canonical_v3 has a row.
    The `min_overlap` parameter is retained for signature compatibility
    but is no longer the controlling rule.
    """
    f_surname = _extract_surname(filing_name)
    o_surname = _extract_surname(owner_name)
    if not f_surname or not o_surname or f_surname != o_surname:
        return False
    shared = (normalize_name(filing_name) & normalize_name(owner_name)) - {f_surname}
    return len(shared) >= 1


# ═══════════════════════════════════════════════════════════════════════
# CANONICAL-aware matcher — the production path
# ═══════════════════════════════════════════════════════════════════════
def match_canonical(filing_name: str, canonical: dict) -> tuple[str, int] | None:
    """
    Match a filing name (petitioner, respondent, grantor, decedent) against
    a canonical owner record from owner_canonical_v3.

    Returns:
        ('STRONG',       3)  — surname matches + ≥1 given-name token overlaps
        ('SURNAME_ONLY', 2)  — surname matches, no given-name overlap
                                (possible heir/spouse; review queue)
        None                 — no match

    Matching logic:
      - Pure entity (llc/company, no persons): no match ever.
      - Decedent surname must appear in canonical['surnames_all'] (so multi-
        owner trust families also match).
      - Given-name overlap checks both the primary given_all AND any
        co_owner given tokens (handles 'Bohan David+liesl Trust' where
        Liesl would be a co-owner).
    """
    if not canonical:
        return None

    d_surname = _extract_surname(filing_name)
    if not d_surname:
        return None

    surnames_all = canonical.get('surnames_all') or []
    if d_surname not in surnames_all:
        return None

    # Pure entity = no match even if someone named 'LLC' parses somehow
    if canonical.get('entity_type') in ('llc', 'company'):
        # Unless the canonical includes an embedded person (has surname_primary)
        # — in which case surname check above already decided
        if not canonical.get('surname_primary'):
            return None

    # Collect all given-name tokens we know about (primary + co-owners)
    all_given: set[str] = set(canonical.get('given_all') or [])
    for co in (canonical.get('co_owners') or []):
        for g in (co.get('given') or []):
            all_given.add(g)

    d_tokens = normalize_name(filing_name)
    shared_given = (d_tokens - {d_surname}) & all_given

    if shared_given:
        return ('STRONG', 3)
    return ('SURNAME_ONLY', 2)


def surname_only_match(filing_name: str, canonical: dict) -> bool:
    """Convenience wrapper — True iff match_canonical returns SURNAME_ONLY."""
    m = match_canonical(filing_name, canonical)
    return m is not None and m[0] == 'SURNAME_ONLY'


def strong_match(filing_name: str, canonical: dict) -> bool:
    """Convenience wrapper — True iff match_canonical returns STRONG."""
    m = match_canonical(filing_name, canonical)
    return m is not None and m[0] == 'STRONG'


# ═══════════════════════════════════════════════════════════════════════
# DIVORCE FILINGS
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class DivorceFiling:
    case_number: str
    filing_date: datetime
    case_type: str  # e.g., "Dissolution with children", "Dissolution no children"
    petitioner_name: str
    respondent_name: str

    @property
    def is_dissolution(self) -> bool:
        """Filter to actual dissolution cases vs. other family law filings."""
        ct = self.case_type.upper()
        return "DISSOL" in ct or "DIVORCE" in ct or "MARRIAGE" in ct


# Case causes that represent actual dissolutions (divorce / legal separation).
# Everything else — state-initiated child support, parenting plans alone,
# out-of-state custody — is filtered out.
_DISSOLUTION_CAUSES = {
    "Dissolution no Children",
    "Dissolution w/ Children",
    "Dissolution of Domestic Partnership /No Children",
    "Dissolution of Domestic Partnership /w Children",
    "Legal Separation",
    "Legal Separation w/ Children",
    "Legal Separation, Domestic Partnership /No Children",
}


def _split_kc_case_name(case_name: str) -> tuple[str, str]:
    """
    KC Superior Court format: 'PETITIONER AND RESPONDENT' in a single field.
    Returns (petitioner, respondent) or ('', '') if unparseable.
    Strips 'ET ANO' / 'ET AL' suffixes from petitioner name.
    """
    if not case_name:
        return "", ""
    parts = re.split(r"\s+AND\s+", case_name.strip(), maxsplit=1)
    if len(parts) != 2:
        return "", ""
    petitioner = re.sub(r"\s+ET\s+A(NO|L)\s*$", "", parts[0]).strip()
    respondent = parts[1].strip()
    return petitioner, respondent


def load_divorce_filings_csv(path: str | Path) -> list[DivorceFiling]:
    """
    Load filings from a KC Superior Court Script Portal export.

    The portal has NO export button — operators copy-paste search result
    tables from the browser, which produces tab-separated text with
    headers:
      Case Number, Filing Date, Case Name, Charge/Cause of Action,
      Next Hearing, Status

    'Case Name' is a single field: 'PETITIONER AND RESPONDENT'.
    State-initiated cases ('STATE OF WASHINGTON AND X') are filtered out.

    Supports either tab-separated or comma-separated input — we
    auto-detect from the first line.

    Legacy CSV format (separate Petitioner First/Last columns) is also
    supported for backward compatibility with the sandbox test fixtures.
    """
    filings: list[DivorceFiling] = []
    p = Path(path)
    if not p.exists():
        return filings

    # Auto-detect delimiter from the header line
    with p.open() as f:
        first_line = f.readline()
    delimiter = "\t" if "\t" in first_line else ","

    with p.open() as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            try:
                # Parse filing date
                fd = row.get("Filing Date") or row.get("filing_date") or ""
                dt = None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                    try:
                        dt = datetime.strptime(fd.strip(), fmt); break
                    except ValueError:
                        continue
                if not dt:
                    continue

                case_number = (row.get("Case Number")
                               or row.get("case_number", "")).strip()

                # ── Resolve petitioner/respondent names ──
                # Modern KC format: single 'Case Name' field
                case_name = (row.get("Case Name") or "").strip()
                if case_name:
                    # Skip state-initiated support cases
                    if case_name.upper().startswith("STATE OF WASHINGTON"):
                        continue
                    pet, resp = _split_kc_case_name(case_name)
                else:
                    # Legacy format: separate first/last columns
                    pet = " ".join([
                        row.get("Petitioner First", row.get("petitioner_first", "")),
                        row.get("Petitioner Last", row.get("petitioner_last", "")),
                    ]).strip()
                    resp = " ".join([
                        row.get("Respondent First", row.get("respondent_first", "")),
                        row.get("Respondent Last", row.get("respondent_last", "")),
                    ]).strip()

                if not pet or not resp:
                    continue

                # ── Resolve cause-of-action ──
                # KC uses 'Charge/Cause of Action'; sandbox fixtures
                # used 'Case Type'. Accept either.
                cause = (row.get("Charge/Cause of Action")
                         or row.get("Case Type")
                         or row.get("case_type", "")).strip()

                # Skip non-dissolution family-law filings at parse time.
                # is_dissolution() on the object is a second line of defense
                # for backward compat with code that doesn't pre-filter.
                if cause and cause not in _DISSOLUTION_CAUSES:
                    # Accept any Dissolution/Legal Separation even if the
                    # exact label shifted slightly — substring check
                    uc = cause.upper()
                    if "DISSOL" not in uc and "LEGAL SEPARATION" not in uc:
                        continue

                filings.append(DivorceFiling(
                    case_number=case_number,
                    filing_date=dt,
                    case_type=cause,
                    petitioner_name=pet,
                    respondent_name=resp,
                ))
            except Exception:
                continue
    return filings


def match_divorce_to_parcels(
    filings: list[DivorceFiling],
    owners_db: dict,
    use_codes: dict[str, dict],
    zip_filter: Optional[str] = None,
) -> list[dict]:
    """
    For each dissolution filing, find residential parcels where both parties
    (or at least one party + co-owner) appear on title.

    owners_db[pin] may carry:
      - 'owner_name':       raw string (always present)
      - 'owner_canonical':  dict from owner_canonical_v3 (optional, preferred)

    When a canonical record is present, matching uses match_canonical() which
    distinguishes STRONG (surname + given overlap) from SURNAME_ONLY (surname
    match only, no given overlap). When absent, falls back to legacy strict
    string matcher.

    Returns candidate dicts for divorce_unwinding signal family.
    """
    candidates = []
    for filing in filings:
        if not filing.is_dissolution:
            continue

        for pin, info in owners_db.items():
            # Residential only
            if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
                continue

            canonical = info.get("owner_canonical")
            owner_name = info.get("owner_name", "")

            if canonical:
                # Canonical path: use the structured match tiers
                p_result = match_canonical(filing.petitioner_name, canonical)
                r_result = match_canonical(filing.respondent_name, canonical)
                p_strong = p_result is not None and p_result[0] == 'STRONG'
                r_strong = r_result is not None and r_result[0] == 'STRONG'
                p_any = p_result is not None
                r_any = r_result is not None

                if p_strong and r_strong:
                    strength = "strong"   # both parties on title
                elif p_strong or r_strong:
                    strength = "weak"      # one party clearly on title
                elif p_any or r_any:
                    strength = "weak"      # surname-only on one party; flag
                else:
                    continue
            else:
                if not owner_name:
                    continue
                p_match = name_match(filing.petitioner_name, owner_name)
                r_match = name_match(filing.respondent_name, owner_name)
                if p_match and r_match:
                    strength = "strong"
                elif p_match or r_match:
                    strength = "weak"
                else:
                    continue

            candidates.append({
                "parcel_id": pin,
                "signal_family": "divorce_unwinding",
                "trigger_hint": {
                    "case_number": filing.case_number,
                    "filing_date": filing.filing_date.strftime("%Y-%m-%d"),
                    "case_type": filing.case_type,
                    "petitioner": filing.petitioner_name,
                    "respondent": filing.respondent_name,
                    "match_strength": strength,
                },
            })
    return candidates


# ═══════════════════════════════════════════════════════════════════════
# RECORDER DOCUMENTS — NOD, LIS PENDENS, TRUSTEE SALE
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class RecorderDocument:
    recording_number: str
    recording_date: datetime
    document_type: str   # NOTICE OF DEFAULT, LIS PENDENS, NOTICE OF TRUSTEE SALE
    grantor_names: list[str]   # typically the property owner being noticed
    grantee_names: list[str]   # typically the lender / plaintiff
    parcel_id: Optional[str] = None   # direct PIN link when available

    @property
    def urgency_tier(self) -> str:
        dt = self.document_type.upper()
        if "TRUSTEE SALE" in dt:
            return "act_this_week"      # sale is scheduled
        if "DEFAULT" in dt:
            return "act_this_week"      # 90-day foreclosure clock started
        if "LIS PENDENS" in dt:
            return "active_window"      # litigation pending; slower
        return "active_window"


def load_recorder_documents_csv(path: str | Path) -> list[RecorderDocument]:
    """
    Load a CSV export from KC Recorder LandmarkWeb Record Date Search.
    Expected columns: Recording Number, Recording Date, Document Type,
    Grantor, Grantee, Parcel Number (optional)
    """
    docs: list[RecorderDocument] = []
    p = Path(path)
    if not p.exists():
        return docs

    with p.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rd = row.get("Recording Date") or row.get("recording_date") or ""
                dt = None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(rd.strip(), fmt); break
                    except ValueError:
                        continue
                if not dt:
                    continue

                grantor = row.get("Grantor", row.get("grantor", ""))
                grantee = row.get("Grantee", row.get("grantee", ""))

                docs.append(RecorderDocument(
                    recording_number=row.get("Recording Number", row.get("recording_number", "")),
                    recording_date=dt,
                    document_type=row.get("Document Type", row.get("document_type", "")),
                    grantor_names=[n.strip() for n in grantor.split(";") if n.strip()],
                    grantee_names=[n.strip() for n in grantee.split(";") if n.strip()],
                    parcel_id=(row.get("Parcel Number") or row.get("parcel_id") or "").strip() or None,
                ))
            except Exception:
                continue
    return docs


def match_recorder_to_parcels(
    docs: list[RecorderDocument],
    owners_db: dict,
    use_codes: dict[str, dict],
) -> list[dict]:
    """
    Match recorded documents to parcels. Two paths:
      1. Direct PIN match (preferred — recorder documents have parcel ID)
      2. Name match against current owner (fallback when PIN absent)

    Uses match_canonical() when owners_db[pin]['owner_canonical'] is present,
    falling back to legacy name_match() otherwise. Recorder grantor matches
    are always treated as STRONG (both STRONG and SURNAME_ONLY tiers
    surface as match_strength='strong') because the filing itself is the
    hard signal — NOD/trustee-sale/lis-pendens don't get filed against
    random neighbors. A surname-only match on a Notice of Default from a
    rare surname is still a real foreclosure signal for that household.
    """
    candidates = []
    for doc in docs:
        matched_pins: list[str] = []

        # Path 1: direct PIN
        if doc.parcel_id and doc.parcel_id in owners_db:
            matched_pins.append(doc.parcel_id)

        # Path 2: name-based fallback
        if not matched_pins:
            for grantor in doc.grantor_names:
                for pin, info in owners_db.items():
                    if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
                        continue
                    canonical = info.get("owner_canonical")
                    if canonical:
                        if match_canonical(grantor, canonical) is not None:
                            matched_pins.append(pin)
                    else:
                        if name_match(grantor, info.get("owner_name", "")):
                            matched_pins.append(pin)

        for pin in matched_pins:
            if use_codes.get(pin, {}).get("prop_type", "") not in ("R", "K", ""):
                continue
            candidates.append({
                "parcel_id": pin,
                "signal_family": "financial_stress",
                "trigger_hint": {
                    "recording_number": doc.recording_number,
                    "recording_date": doc.recording_date.strftime("%Y-%m-%d"),
                    "document_type": doc.document_type,
                    "grantor": "; ".join(doc.grantor_names),
                    "grantee": "; ".join(doc.grantee_names),
                    "urgency_tier": doc.urgency_tier,
                    "days_since_recording": (datetime.utcnow() - doc.recording_date).days,
                },
            })
    return candidates
