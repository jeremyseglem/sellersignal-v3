"""
KC Superior Court — Participants tab scraper.

The primary KC Superior Court harvester (kc_superior_court.py) extracts
the SEARCH RESULTS list: one row per case with case number, filing date,
case name (like "IN RE MARK LAWRENCE GABOUER"), and cause. That row
gives us the DECEDENT's name via case-name parsing.

This module drills deeper: for each case, fetch the Participants tab
and extract every named party with their role. That's where we find
the Personal Representative — the LIVING human who actually makes the
decision to list and sell the property.

Why this matters:
  - Sending a letter to a decedent's mailing address has ~0% conversion
  - The PR is the decision-maker; attorneys are gatekeepers who block outreach
  - ~80% of probate cases have a family-member PR (spouse, adult child)
  - ~20% have a corporate trustee or attorney PR — unworkable for agent pitch

URL pattern (reverse-engineered from live portal):
  Search results     → /node/411?caseType={code}  (POSTs here to search)
  Case detail (bootstrap)
                     → /?q=node/420/{internal_id}  (link from search results)
                     → server redirects to /node/420?id={internal_id}
  Participants tab   → /node/420?Id={internal_id}&folder=FV-Public-Case-Participants-Portal
                       (note capital Id= on the folder URL)

Session requirements:
  - Must reuse the session that performed the search (cookies required)
  - Must send Referer header (portal rejects direct access)
  - Must bootstrap detail view before requesting Participants tab

Rate: tested ~1.2 sec per case. For 8,705 historical probate signals that's
~3 hours wall-clock. Acceptable for a one-time backfill.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://dja-prd-ecexap1.kingcounty.gov"


# ─── Role normalization ──────────────────────────────────────────────────

# The portal displays roles with varying casing and occasional embedded
# newlines (e.g. "Petitioner\r\n \r\n/ Personal Representative"). We
# normalize to a stable vocabulary for storage.
_ROLE_PATTERNS = [
    # Most specific first — "Petitioner / Personal Representative" shows up
    # as a combined label when the filer is also the appointed PR. Treat as PR.
    (re.compile(r"petitioner.*personal\s*rep", re.I), "personal_representative"),
    (re.compile(r"personal\s*rep", re.I),             "personal_representative"),
    (re.compile(r"^petitioner$", re.I),               "petitioner"),
    (re.compile(r"respondent", re.I),                 "respondent"),
    (re.compile(r"decea?sed", re.I),                  "deceased"),
    (re.compile(r"^guardian$", re.I),                 "guardian"),
    (re.compile(r"ward", re.I),                       "ward"),
    (re.compile(r"attorney", re.I),                   "attorney"),
    (re.compile(r"trustee", re.I),                    "trustee"),
    (re.compile(r"minor|child", re.I),                "minor"),
]


def _normalize_role(raw: str) -> str:
    """Map a raw role string to our normalized vocabulary."""
    raw_clean = re.sub(r"\s+", " ", (raw or "").strip())
    for pattern, norm in _ROLE_PATTERNS:
        if pattern.search(raw_clean):
            return norm
    return "other"


# ─── PR classification ──────────────────────────────────────────────────
#
# When role is 'personal_representative', determine whether the PR is:
#   'family'    — workable, individual human contact
#   'corporate' — unworkable, corporate trustee/fiduciary
#   'attorney'  — unworkable, law firm or attorney serving as PR
#   'unknown'   — doesn't match any pattern; treat with caution
#
# These patterns are conservative — bias toward classifying as 'family'
# since most PRs ARE family. Only flag as unworkable with strong signals.

_CORPORATE_PR_PATTERNS = re.compile(
    r"\b("
    # Banks & trust services
    r"BANK|TRUST\s+SERVICES|TRUST\s+COMPANY|TRUSTEE\s+SERVICES|"
    r"FIDUCIARY|FIRST\s+AMERICAN|STATE\s+STREET|NORTHERN\s+TRUST|"
    r"WELLS\s+FARGO|BANK\s+OF\s+AMERICA|U\.?S\.?\s+BANK|"
    r"CAPITAL\s+ONE|CHARLES\s+SCHWAB|FIDELITY|VANGUARD|"
    # Medical / healthcare institutions
    r"HOSPITAL|MEDICAL\s+CENTER|MEDICAL\s+CTR|HEALTHCARE|"
    r"HEALTH\s+SYSTEM|HEALTH$|HEALTH\s+SVCS|FRANCISCAN|"
    r"VIRGINIA\s+MASON|SWEDISH\s+MEDICAL|OVERLAKE\s+MEDICAL|"
    r"KAISER\s+PERMANENTE|PROVIDENCE\s+HEALTH|EVERGREEN\s+HEALTH|"
    # Care facilities
    r"NURSING|HOSPICE|CONVALESCENT|ADULT\s+FAMILY\s+HOME|"
    r"ASSISTED\s+LIVING|RETIREMENT\s+CENTER|LONG\s+TERM\s+CARE|"
    # Government / institutional
    r"DEPARTMENT\s+OF|DSHS|STATE\s+OF\s+WASHINGTON|COUNTY\s+OF|"
    r"SOCIAL\s+SECURITY\s+ADMIN|VETERANS\s+AFFAIRS|MEDICARE|"
    # Nonprofits / foundations
    r"FOUNDATION|CHARITY|CHARITIES|UNITED\s+WAY|"
    r"RED\s+CROSS|SALVATION\s+ARMY|GOODWILL|"
    # Generic corporate suffixes
    r"INC\.?|LLC\.?|L\.?L\.?C\.?|CORP\.?|CORPORATION|COMPANY|"
    r"N\.?\s*A\.?$|NATIONAL\s+ASSOCIATION"
    r")\b",
    re.IGNORECASE,
)

_ATTORNEY_PR_PATTERNS = re.compile(
    r"\b("
    r"ESQ\.?|ATTORNEY\s+AT\s+LAW|LAW\s+OFFICES?|LAW\s+GROUP|"
    r"LAW\s+FIRM|PLLC|LAW\s+P\.?L\.?L\.?C\.?|ASSOCIATES"
    r")\b",
    re.IGNORECASE,
)


def classify_pr(name_raw: str) -> str:
    """Classify a Personal Representative name as family/corporate/attorney/unknown."""
    if not name_raw:
        return "unknown"
    name_upper = name_raw.upper()

    if _CORPORATE_PR_PATTERNS.search(name_upper):
        return "corporate"
    if _ATTORNEY_PR_PATTERNS.search(name_upper):
        return "attorney"

    # Heuristic: individuals on the KC portal are always "LAST, FIRST MIDDLE"
    # with a comma. A 3+ word uppercase name with NO comma is institutional
    # (e.g. "VIRGINIA MASON FRANCISCAN HEALTH", "STATE OF WASHINGTON DSHS").
    # Catch these even if no specific keyword matched.
    if "," not in name_raw:
        tokens = [t for t in name_raw.split() if t]
        if len(tokens) >= 3 and name_raw.isupper():
            return "corporate"

    # "LAST, FIRST MIDDLE" or "FIRST MIDDLE LAST" — individual human.
    # Allow single-char tokens (middle initials like "JUDITH P").
    cleaned = re.sub(r"[^A-Za-z,\- ]", "", name_raw).strip()
    tokens = re.findall(r"[A-Za-z\-]+", cleaned)
    if not tokens:
        return "unknown"
    # At least one token must be multi-char (otherwise "A B" or similar garbage)
    multi_char_tokens = [t for t in tokens if len(t) > 1]
    if 2 <= len(tokens) <= 6 and len(multi_char_tokens) >= 2:
        return "family"

    return "unknown"


# ─── Name parsing ──────────────────────────────────────────────────────

def _parse_party_name(raw: str) -> dict:
    """
    Parse a party name from the Participants tab into last/first/middle.
    The KC portal uses "LAST, FIRST MIDDLE" format consistently.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    if "," in raw:
        last, rest = raw.split(",", 1)
        tokens = rest.strip().split()
        out = {"last": last.strip().title()} if last.strip() else {}
        if tokens:
            out["first"] = tokens[0].title()
            if len(tokens) > 1:
                # Handle suffixes embedded in middle
                rest_tokens = tokens[1:]
                suffix_tokens = {"JR", "SR", "II", "III", "IV", "V"}
                middle_tokens = [
                    t for t in rest_tokens
                    if t.upper().rstrip(".") not in suffix_tokens
                ]
                if middle_tokens:
                    out["middle"] = " ".join(middle_tokens).title()
        return out
    # Fallback: "FIRST LAST" form
    tokens = raw.split()
    if len(tokens) == 1:
        return {"last": tokens[0].title()}
    return {
        "first": tokens[0].title(),
        "last":  tokens[-1].title(),
        **({"middle": " ".join(tokens[1:-1]).title()} if len(tokens) > 2 else {}),
    }


# ─── Participants extraction ──────────────────────────────────────────

@dataclass
class ParsedParty:
    """A single party row from the Participants tab."""
    role: str                    # normalized role
    raw_role: str                # original portal label
    name_raw: str                # "LEITHE, JUDITH P"
    name_last: Optional[str]
    name_first: Optional[str]
    name_middle: Optional[str]
    represented_by: Optional[str]
    pr_classification: Optional[str]  # only set for PR roles


def _parse_participants_html(html: str) -> list[ParsedParty]:
    """
    Parse the Participants tab HTML into structured party records.

    Expected table structure (class="table table-condensed table-hover"):
      [empty] | Type | Name | Represented By     (header)
      [empty] | "Petition - filed on MM/DD/YYYY" (section divider, colspan)
      [empty] | <role> | <name> | <attorney>    (data row)
      ...
    """
    soup = BeautifulSoup(html, "html.parser")
    parties: list[ParsedParty] = []

    # The participants table is the only table with class "table-condensed"
    # in the portal layout. Fall back to first table containing "Type" and
    # "Name" headers if class match fails.
    table = soup.find("table", class_="table-condensed")
    if table is None:
        for tbl in soup.find_all("table"):
            first_tr = tbl.find("tr")
            if not first_tr:
                continue
            header_txt = first_tr.get_text(" ", strip=True).lower()
            if "type" in header_txt and "name" in header_txt:
                table = tbl
                break

    if table is None:
        log.warning("No participants table found in HTML")
        return parties

    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        # We want 4-cell data rows. First cell is always empty (spacer).
        if len(cells) < 4:
            continue

        texts = [c.get_text(" ", strip=True) for c in cells]
        # Skip header row
        if texts[1].lower() == "type" and texts[2].lower() == "name":
            continue

        raw_role = texts[1]
        name_raw = texts[2]
        represented_by = texts[3] or None

        # Skip empty or non-data rows
        if not raw_role or not name_raw:
            continue

        # Skip section-divider rows that sometimes collapse into 4 cells
        # (e.g. "Petition - filed on 04/20/2026" can show in cell[1] with
        # nothing else meaningful)
        if name_raw.lower().startswith("petition") and "filed on" in name_raw.lower():
            continue

        # Clean up embedded whitespace/newlines in role
        raw_role_clean = re.sub(r"\s+", " ", raw_role).strip()
        role_norm = _normalize_role(raw_role_clean)

        parsed = _parse_party_name(name_raw)
        pr_class = classify_pr(name_raw) if role_norm == "personal_representative" else None

        parties.append(ParsedParty(
            role=role_norm,
            raw_role=raw_role_clean,
            name_raw=name_raw,
            name_last=parsed.get("last"),
            name_first=parsed.get("first"),
            name_middle=parsed.get("middle"),
            represented_by=represented_by.strip() if represented_by else None,
            pr_classification=pr_class,
        ))

    return parties


def fetch_case_participants(
    session: requests.Session,
    internal_id: str,
    search_referer: str,
    case_url_code: str = "511110",
    polite_delay: float = 0.4,
) -> list[ParsedParty]:
    """
    Fetch and parse the Participants tab for a single case.

    Args:
        session: A requests.Session already warm from performing a search
                 (has cookies set). Reuse the session from the primary harvester.
        internal_id: The case's internal node ID (e.g. "7629118"), extracted
                     from the search-results link href "?q=node/420/{id}".
        search_referer: URL of the search-results page, used as Referer.
        case_url_code: "511110" for probate, "211110" for domestic.
        polite_delay: Seconds to sleep before request. Default 0.4s.

    Returns:
        list of ParsedParty objects. Empty if fetch fails or no parties
        are parseable.
    """
    if polite_delay > 0:
        time.sleep(polite_delay)

    # Bootstrap: visit the detail-page entry link to establish view session
    detail_url = f"{BASE}/?q=node/420/{internal_id}"
    try:
        session.get(
            detail_url,
            headers={"Referer": search_referer},
            timeout=30,
        )
    except requests.RequestException as e:
        log.warning(f"Bootstrap GET failed for case {internal_id}: {e}")
        return []

    # Now fetch the Participants tab
    part_url = (
        f"{BASE}/node/420"
        f"?Id={internal_id}"
        f"&folder=FV-Public-Case-Participants-Portal"
    )
    try:
        resp = session.get(
            part_url,
            headers={"Referer": detail_url},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"Participants GET failed for case {internal_id}: {e}")
        return []

    parties = _parse_participants_html(resp.text)
    if not parties:
        log.debug(f"No parties parsed for case internal_id={internal_id}")
    return parties


def compute_html_hash(html: str) -> str:
    """Compact hash of participants HTML for change detection."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
