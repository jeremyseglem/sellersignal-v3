"""
Maricopa County Superior Court — Probate docket harvester.

Recon (2026-07-28): the probate docket at
  superiorcourt.maricopa.gov/docket/ProbateCourtCases/
offers name-search and case-number search only (NO filing-date discovery,
same shape as MT district courts and the 38 non-KC WA counties). The
"recaptcha" on the site is chrome-wide, not gating the search form — plain
GET requests work. The caseInfo.asp?caseNumber=PB{year}-{seq} detail page
carries a full party table (Party Name / Relationship / Sex / Attorney)
plus filing date.

Strategy: enumerate PB{year}-{seq:06d} case numbers (mirrors the MT
district-court DP enumeration) and parse each detail page.

CRITICAL — the PB prefix is a MIXED bucket. Maricopa files BOTH decedent
estates (Decedent / Personal Representative / Heir) AND guardianship /
conservatorship (Ward / Petitioner / Conservator) under PB. Only decedent
estates are SellerSignal probate leads — a named PR is the seller's
decision-maker. Guardianships are a different, weaker signal (ward often
alive, property murky) and are dropped here: to_signal_row emits a probate
signal ONLY when the case has a Decedent + a PR-type party.

Nothing writes to raw_signals_v3 until the parse path is truth-tested.
source_type: 'maricopa_probate_court' (register in matcher.SOURCE_MARKETS →
AZ_MARICOPA before first write).
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

BASE = "https://www.superiorcourt.maricopa.gov/docket/ProbateCourtCases"
CASE_INFO = f"{BASE}/caseInfo.asp"
SEARCH = f"{BASE}/caseSearchResults.asp"

# Roles that identify a decedent-estate probate (the leads we want).
_DECEDENT_ROLES = ("DECEDENT", "DECEASED", "ESTATE OF")
_PR_ROLES = ("PERSONAL REPRESENTATIVE", "SPECIAL ADMINISTRATOR",
             "SPECIAL ADMR", "ADMINISTRATOR", "EXECUTOR", "APPLICANT")
# In fresh estates the formal PR isn't appointed on day one — only a
# Petitioner is named (the person who filed to open the estate, typically
# the eventual PR / a family member). Used as the contact fallback so a
# just-filed estate still surfaces a callable name (KC "no_pr_yet" shape).
_PETITIONER_ROLES = ("PETITIONER", "APPLICANT")
_HEIR_ROLES = ("HEIR", "DEVISEE", "BENEFICIARY")
# Roles that mark a case as guardianship/conservatorship — NOT a seller
# signal. Presence of a Ward with no Decedent means "drop".
_GUARDIANSHIP_ROLES = ("WARD", "PROTECTED PERSON", "CONSERVATOR",
                       "GUARDIAN", "MINOR")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_case_detail(html: str) -> Optional[dict]:
    """Parse a caseInfo.asp page into a structured case dict, or None if it
    isn't a viewable probate case (not found / no party table)."""
    low = html.lower()
    if "no case" in low or "not found" in low or "no matching" in low:
        return None
    if "party name" not in low or "filing date" not in low:
        return None

    cap = re.search(r"(PB\d{4}-\d{6})", html)
    case_no = cap.group(1) if cap else None
    if not case_no:
        return None

    txt = re.sub(r"<[^>]+>", "|", html)
    txt = re.sub(r"\|+", "|", txt)
    txt = re.sub(r"[ \t\r\n]+", " ", txt)

    # "Filing Date" appears as a column header in the case-activity table,
    # not as a labeled value — the actual case filing date is the EARLIEST
    # docket/activity date on the page (register of actions). Verified
    # 2026-07-28: the min mm/dd/yyyy on the page = the case filing date.
    all_dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", txt)
    filing_date = None
    if all_dates:
        def _key(d):
            mm, dd, yy = d.split("/")
            return (int(yy), int(mm), int(dd))
        filing_date = min(all_dates, key=_key)

    ct = re.search(r"Case Type\|?\s*([A-Za-z /]+?)\s*\|", txt)
    case_type = _clean(ct.group(1)) if ct else None

    # Party table renders as a flat repeating sequence:
    #   Party Name| | {name} | |Relationship| | {rel} | |Sex| | {sex} |
    #   |Attorney| | {atty} |
    # One regex captures each party in order (verified 2026-07-28).
    parties = []
    row_re = re.compile(
        r"Party Name\|\s*\|\s*([^|]+?)\s*\|\s*\|Relationship\|\s*\|\s*"
        r"([^|]*?)\s*\|\s*\|Sex\|\s*\|\s*([^|]*?)\s*\|\s*\|Attorney\|\s*\|\s*"
        r"([^|]*?)\s*\|")
    for m in row_re.finditer(txt):
        name = _clean(m.group(1))
        rel = _clean(m.group(2))
        atty = _clean(m.group(4))
        if not name or name.lower() in ("relationship", "sex", "attorney"):
            continue
        parties.append({"name": name, "relationship": rel,
                        "attorney": None if atty in ("", "Pro Per") else atty})
    if not parties:
        return None

    return {
        "case_number": case_no,
        "case_type": case_type,
        "filing_date": filing_date,
        "parties": parties,
    }


def _has_role(parties, roles) -> Optional[dict]:
    for p in parties:
        rel = (p.get("relationship") or "").upper()
        if any(r in rel for r in roles):
            return p
    return None


def _normalize_party_name(name: str) -> str:
    n = re.sub(r"[.,]", " ", (name or "").upper())
    n = re.sub(r"\b(JR|SR|II|III|IV|ESQ)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _mmddyyyy_to_iso(s: str) -> Optional[str]:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def classify(case: dict) -> str:
    """decedent_estate | guardianship | other. Only decedent_estate becomes
    a seller signal."""
    parties = case.get("parties") or []
    decedent = _has_role(parties, _DECEDENT_ROLES)
    guardianship = _has_role(parties, _GUARDIANSHIP_ROLES)
    if decedent:
        return "decedent_estate"
    if guardianship:
        return "guardianship"
    return "other"


def to_signal_row(case: dict, jurisdiction: str = "Maricopa County") -> Optional[dict]:
    """Map a parsed case to a raw_signals_v3 row. Returns None unless the
    case is a decedent estate with a matchable decedent. party_names[0] is
    the DECEDENT (still on the assessor roll → matcher key); the PR is the
    contact (not matchable)."""
    if classify(case) != "decedent_estate":
        return None
    parties = case.get("parties") or []
    decedent = _has_role(parties, _DECEDENT_ROLES)
    pr = _has_role(parties, _PR_ROLES)
    if not decedent:
        return None

    out_parties = [{
        "raw": decedent["name"],
        "normalized": _normalize_party_name(decedent["name"]),
        "role": "decedent", "matchable": True,
    }]
    contact = pr or _has_role(parties, _PETITIONER_ROLES)
    pr_status = "pr_identified" if pr else (
        "petitioner_only" if contact else "no_pr_yet")
    if contact and contact["name"].upper() != decedent["name"].upper():
        out_parties.append({
            "raw": contact["name"],
            "normalized": _normalize_party_name(contact["name"]),
            "role": "personal_representative" if pr else "petitioner",
            "matchable": False,
            "attorney": contact.get("attorney"),
        })

    heirs = [p for p in parties
             if any(r in (p.get("relationship") or "").upper()
                    for r in _HEIR_ROLES)]
    attorneys = sorted({p["attorney"] for p in parties if p.get("attorney")})

    return {
        "source_type": "maricopa_probate_court",
        "signal_type": "probate",
        "trust_level": "high",
        "party_names": out_parties,
        "event_date": _mmddyyyy_to_iso(case.get("filing_date") or ""),
        "jurisdiction": jurisdiction,
        "property_hint": None,
        "document_ref": case["case_number"],
        "raw_data": {
            "case_number": case["case_number"],
            "case_type": case.get("case_type"),
            "filing_date": case.get("filing_date"),
            "parties": parties,
            "heir_count": len(heirs),
            "pr_status": pr_status,
            "attorneys": attorneys,
            "harvester": "maricopa_probate_court",
        },
    }
