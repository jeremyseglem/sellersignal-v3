#!/usr/bin/env python3
"""
TOPICs statewide probate-citation harvester — Texas Office of Court
Administration "Citations by Publication/Posting" feed.

THE SURFACE (discovered 2026-06-11): https://topics.txcourts.gov/CitationsPublic
publishes legally-required probate citations for ALL Texas counties in one
stream. Detail pages live at sequential numeric IDs:

    /CitationsPublic/CitationsPublic/{id}          (server-rendered HTML table)
    /CitationsPublic/PreviewCitationNoticeAttachment/{id}   (PDF citation text)

No captcha, no Cloudflare, plain HTTP (verified from datacenter egress).
~58 records/day statewide, ~63% probate. Per 2-day sample: Dallas 4 probate,
Tarrant 9, Collin 2, Travis 2, Harris, Montgomery, Williamson...

WHY IT MATTERS: this is the statewide Texas court-side probate discovery
channel — the county courts portals (Tyler) are lookup-keyed with no
date-filed search, but the citation stream IS date-ordered and enumerable.
One harvester covers every future TX market (Tarrant/Collin/Travis/Harris)
by adding a county->market entry to COUNTY_MARKETS.

WHAT A RECORD CARRIES:
  detail page  -> cause number (PR-26-01692-1), court/county, party-to-be-
                  served text (contains "ESTATE OF {decedent}, Deceased"),
                  publication start/end dates, status
  PDF attach   -> full citation text naming the APPLICANT ("...filed by
                  Margaret Mashburn, on the June 08, 2020...") — the future
                  executor/PR, i.e. the decision-maker.

HONEST COVERAGE NOTE: this is the citation-by-publication/posting subset —
heirship / unknown-heirs skew. Dallas shows ~2/day here vs ~14/day total
probate filings (~15% capture). Testate estates with clean executors are
underrepresented. Stacks with (does not replace) the recorder heirship
channel: TOPICs catches the court filing weeks before the title transfer.

Signal shape mirrors dallas_recorder: decedent is party_names[0]
(matchable — still on title in the assessor roll), applicant is the
personal_representative contact. source_type=tx_topics_citations.
"""
from __future__ import annotations

import html as _html
import io
import re
import time
from datetime import datetime

import requests

BASE = "https://topics.txcourts.gov/CitationsPublic"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# County (as it appears in parentheses in Court/County) -> market_key.
# ONLY counties listed here are emitted. Extend when new TX markets onboard
# (and add the matching SOURCE_MARKET_SCOPE entry in matcher.py).
COUNTY_MARKETS = {
    "Dallas": "TX_DALLAS",
    "Travis": "TX_TRAVIS",
}

# Probate detection across cause number / court / party text.
_PROBATE_RE = re.compile(
    r"probate|estate of|heirs of|guardianship|\bPR-|\bCPR|\bCCPR|muniment",
    re.I)

_DECEDENT_RE = re.compile(
    r"ESTATE\s+OF\s+(.+?)(?:,?\s+(?:Deceased|DECEASED|an?\s+Incapacitated))",
    re.S)

# Applicant patterns seen in citation PDFs:
#   "...filed by Margaret Mashburn, on the June 08, 2020..."
#   "...Application ... filed by JOHN A SMITH on..."
_APPLICANT_RE = re.compile(
    r"filed\s+by\s+([A-Z][A-Za-z'.\- ]{2,60}?)\s*(?:,| on\b| in\b|\.\s)", )

_FILED_DATE_RE = re.compile(
    r"filed by .{2,80}? on (?:the )?([A-Z][a-z]+ \d{1,2},? \d{4})")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch_detail(session: requests.Session, topics_id: int) -> dict | None:
    """Fetch + parse one detail page. Returns None for nonexistent IDs.

    NOTE: nonexistent IDs do NOT 404 — they redirect to the search page
    (title 'Search Citations/Notices'), which still contains 'Cause Number'
    as a filter label. Existence = the cause-number CELL grabs a value.
    """
    r = session.get(f"{BASE}/CitationsPublic/{topics_id}",
                    headers={"User-Agent": UA}, timeout=25)
    t = r.text
    if r.status_code != 200 or "Citation/Notice Details" not in t:
        return None

    def grab(label: str) -> str:
        m = re.search(label + r".*?<td[^>]*>(.*?)</td>", t, re.S)
        return _clean(m.group(1)) if m else ""

    cause = grab("Cause Number")
    if not cause:
        return None
    cc = grab("Court/County")
    county_m = re.search(r"\((.*?)\)\s*$", cc)
    pub_start = grab("Publication Start Date")
    try:
        pub_iso = datetime.strptime(pub_start, "%m/%d/%Y").date().isoformat()
    except ValueError:
        pub_iso = None
    return {
        "topics_id": topics_id,
        "cause_number": cause,
        "court": cc,
        "county": county_m.group(1) if county_m else "",
        "party_text": grab("party to be served"),
        "pub_start": pub_iso,
        "pub_end": grab("Publication End Date"),
        "status": grab("Status"),
    }


def is_probate(rec: dict) -> bool:
    blob = " ".join([rec.get("cause_number", ""), rec.get("court", ""),
                     rec.get("party_text", "")])
    return bool(_PROBATE_RE.search(blob))


def extract_decedent(rec: dict) -> str | None:
    m = _DECEDENT_RE.search(rec.get("party_text", ""))
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" ,")
    return None


def fetch_attachment_text(session: requests.Session, topics_id: int) -> str:
    """Fetch the citation PDF and extract its text (pypdf layout mode, the
    proven Snohomish pattern). Returns '' on any failure — the detail page
    alone still yields a usable signal (decedent name, no applicant)."""
    try:
        r = session.get(f"{BASE}/PreviewCitationNoticeAttachment/{topics_id}",
                        headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200 or not r.content[:5].startswith(b"%PDF"):
            return ""
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        out = []
        for page in reader.pages[:4]:
            try:
                out.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:
                out.append(page.extract_text() or "")
        return re.sub(r"\s+", " ", " ".join(out))
    except Exception:
        return ""


def extract_applicant(pdf_text: str) -> tuple[str | None, str | None]:
    """Return (applicant_name, filed_date_iso) from citation text."""
    name = None
    filed = None
    m = _APPLICANT_RE.search(pdf_text or "")
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
    m = _FILED_DATE_RE.search(pdf_text or "")
    if m:
        for fmt in ("%B %d, %Y", "%B %d %Y"):
            try:
                filed = datetime.strptime(m.group(1).replace(",", ", ")
                                          .replace("  ", " "), fmt).date().isoformat()
                break
            except ValueError:
                continue
    return name, filed


def _normalize(raw: str) -> str:
    return re.sub(r"[^A-Z ]", " ", (raw or "").upper()).strip()


def to_signal_row(rec: dict, applicant: str | None,
                  filed_date: str | None) -> dict | None:
    """Map a probate citation to the proven raw_signals_v3 shape."""
    market = COUNTY_MARKETS.get(rec.get("county") or "")
    if not market:
        return None
    decedent = extract_decedent(rec)
    if not decedent or not rec.get("cause_number"):
        return None

    parties = [{"raw": decedent, "normalized": _normalize(decedent),
                "role": "decedent", "matchable": True}]
    if applicant and applicant.upper() != decedent.upper():
        parties.append({"raw": applicant, "normalized": _normalize(applicant),
                        "role": "personal_representative", "matchable": False})

    return {
        "source_type": "tx_topics_citations",
        "signal_type": "probate",
        "trust_level": "high",
        "party_names": parties,
        "event_date": filed_date or rec.get("pub_start"),
        "jurisdiction": market,
        "property_hint": None,
        "document_ref": rec["cause_number"],
        "raw_data": {
            "topics_id": rec["topics_id"],
            "cause_number": rec["cause_number"],
            "court": rec["court"],
            "county": rec["county"],
            "decedent": decedent,
            "applicant": applicant,
            "filed_date": filed_date,
            "publication_start": rec.get("pub_start"),
            "publication_end": rec.get("pub_end"),
            "status": rec.get("status"),
            "detail_url": f"{BASE}/CitationsPublic/{rec['topics_id']}",
            "harvester": "topics_citations",
        },
    }


def find_live_edge(session: requests.Session, start_hint: int = 105000,
                   step: int = 500) -> int:
    """Locate the highest existing ID. Walk forward in coarse steps from the
    hint until empty, then binary-narrow. ~12-18 requests."""
    lo = start_hint
    # ensure the hint itself exists; if not, walk back
    while fetch_detail(session, lo) is None and lo > 0:
        lo -= step
    hi = lo + step
    while fetch_detail(session, hi) is not None:
        lo = hi
        hi += step
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fetch_detail(session, mid) is not None:
            lo = mid
        else:
            hi = mid
    return lo
