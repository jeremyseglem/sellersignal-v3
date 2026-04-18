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
                 "FAMILY", "REVOCABLE", "LIVING", "ET", "AL"}


def normalize_name(name: str) -> set[str]:
    """Return a set of last+first tokens from a name string, uppercased."""
    if not name:
        return set()
    up = name.upper()
    up = _NAME_NOISE.sub(" ", up)
    up = _WHITESPACE.sub(" ", up).strip()
    tokens = {t for t in up.split() if len(t) >= 2}
    tokens -= _TITLE_TOKENS
    tokens -= _TRUST_TOKENS
    return tokens


def name_match(filing_name: str, owner_name: str,
               min_overlap: int = 2) -> bool:
    """
    True if the filing and owner names share at least `min_overlap`
    meaningful tokens. Default 2 = both first and last name must match.
    Single-token matches (e.g., just shared surname) are intentionally
    rejected — too many false positives.
    """
    a = normalize_name(filing_name)
    b = normalize_name(owner_name)
    return len(a & b) >= min_overlap


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


def load_divorce_filings_csv(path: str | Path) -> list[DivorceFiling]:
    """
    Load a CSV export from KC Script Portal Family Law case search.
    Expected columns (may vary by export format — normalize in code):
      Case Number, Filing Date, Case Type, Petitioner Last, Petitioner First,
      Respondent Last, Respondent First
    """
    filings: list[DivorceFiling] = []
    p = Path(path)
    if not p.exists():
        return filings

    with p.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                fd = row.get("Filing Date") or row.get("filing_date") or ""
                dt = None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                    try:
                        dt = datetime.strptime(fd.strip(), fmt); break
                    except ValueError:
                        continue
                if not dt:
                    continue

                pet = " ".join([
                    row.get("Petitioner First", row.get("petitioner_first", "")),
                    row.get("Petitioner Last", row.get("petitioner_last", "")),
                ]).strip()
                resp = " ".join([
                    row.get("Respondent First", row.get("respondent_first", "")),
                    row.get("Respondent Last", row.get("respondent_last", "")),
                ]).strip()

                filings.append(DivorceFiling(
                    case_number=row.get("Case Number", row.get("case_number", "")),
                    filing_date=dt,
                    case_type=row.get("Case Type", row.get("case_type", "")),
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

    Returns candidate dicts for divorce_unwinding signal family.
    """
    candidates = []
    for filing in filings:
        if not filing.is_dissolution:
            continue

        for pin, info in owners_db.items():
            # Residential only
            if use_codes.get(pin, {}).get("prop_type", "") != "R":
                continue
            owner_name = info.get("owner_name", "")
            if not owner_name:
                continue

            # Both petitioner AND respondent on title → STRONG
            # Just one on title → SUPPORT, needs other evidence
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
                    if use_codes.get(pin, {}).get("prop_type", "") != "R":
                        continue
                    if name_match(grantor, info.get("owner_name", "")):
                        matched_pins.append(pin)

        for pin in matched_pins:
            if use_codes.get(pin, {}).get("prop_type", "") != "R":
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
