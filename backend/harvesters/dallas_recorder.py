#!/usr/bin/env python3
"""
Dallas County (TX) Recorder harvester — recorded-document signals via the
County Clerk's neumo Official Records search (dallas.tx.publicsearch.us).

Structural analog of the Maricopa Recorder + KC Superior Court harvesters, with
the key simplification that the neumo results grid renders grantor / grantee /
doc-type / recorded-date / legal-description as HTML TEXT — no OCR needed. The
only obstacle is a Cloudflare-managed edge gate, which a real headless browser
(Playwright Chromium) clears on navigation (verified 2026-06-10 from a GitHub
Actions runner; raw requests/curl get a 403 "Just a moment..." challenge).

PIPELINE
  1. render(date_range) -> results grid HTML  (Playwright; gate clears on load)
       GET /results?department=RP&recordedDateRange=YYYYMMDD,YYYYMMDD
           &searchType=quickSearch&keywordSearch=false&searchOcrText=false
  2. parse_rows(html)   -> [{grantor, grantee, doc_type, recorded_date,
                             doc_number, town, legal_description}]
  3. filter to death/estate instruments (client-side on DOC TYPE — we do NOT
     depend on neumo's server-side doc-type facet param, which is applied via
     opaque client state; same approach as KC: pull the date window, classify
     downstream).
  4. to_signal_row() -> raw_signals_v3 row (source_type=tx_dallas_recorder),
     matched downstream by the existing rematch_autofill matcher on decedent name.

DEATH / ESTATE DOC TYPES (the sellable probate-transfer signal — a death tied to
a specific parcel via the recorded instrument):
  AFFIDAVIT OF DEATH            -> probate   (grantor = decedent)
  EXECUTORS DEED / EXECUTOR     -> probate   (grantor = estate, grantee = heir)
  PERSONAL REPRESENTATIVE DEED  -> probate
  ADMINISTRATORS DEED           -> probate
  DEED OF DISTRIBUTION          -> probate
  TRANSFER ON DEATH / TODD      -> transfer_on_death
  DEATH CERTIFICATE             -> death

NOTE ON COURT vs RECORDER: Dallas probate CASES live in the County Courts portal
(courtsportal.dallascounty.org), which is lookup-keyed (no date-filed discovery)
— so the recorder is the discovery surface, exactly as in Maricopa. The recorded
instruments above are richer than a raw case filing: they bind the death to a
named parcel (legal description / subdivision-lot-block), which DCAD resolves to
an APN + owner for matching.

DEPLOYMENT: runs in a GitHub Action (like Maricopa) so the browser dependency
never touches the Railway service. Requires playwright + chromium.
"""
from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime, date, timedelta

RESULTS_URL = "https://dallas.tx.publicsearch.us/results"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# DOC TYPE (as rendered in the grid, uppercased) -> signal_type.
# Matched by substring against the row's DOC TYPE cell, so variants like
# "EXECUTORS DEED" / "EXECUTOR'S DEED" / "DEED EXECUTOR" all catch on "EXECUTOR".
DEATH_DOCTYPE_SIGNALS = [
    ("AFFIDAVIT OF DEATH",        "probate"),
    ("PERSONAL REPRESENTATIVE",   "probate"),
    ("EXECUTOR",                  "probate"),
    ("ADMINISTRATOR",             "probate"),
    ("DISTRIBUTION",              "probate"),   # DEED OF DISTRIBUTION
    ("TRANSFER ON DEATH",         "transfer_on_death"),
    ("TODD",                      "transfer_on_death"),
    ("DEATH CERTIFICATE",         "death"),
]


def classify_doc_type(doc_type: str):
    """Return signal_type for a death/estate doc type, else None."""
    dt = (doc_type or "").upper()
    for needle, sig in DEATH_DOCTYPE_SIGNALS:
        if needle in dt:
            return sig
    return None


# ── 1. render ────────────────────────────────────────────────────────────────

def _results_url(begin: date, end: date, page_num: int = 1) -> str:
    qs = urllib.parse.urlencode({
        "department": "RP",
        "recordedDateRange": f"{begin.strftime('%Y%m%d')},{end.strftime('%Y%m%d')}",
        "searchType": "quickSearch",
        "keywordSearch": "false",
        "searchOcrText": "false",
        "recordedDateRangeStart": begin.strftime("%Y%m%d"),
        "page": str(page_num),
    })
    return f"{RESULTS_URL}?{qs}"


def render_page(page, begin: date, end: date, page_num: int,
                settle_seconds: float = 7.0) -> str:
    """Navigate to one results page (1-indexed) and return the table inner_text.

    `page` is a live Playwright page on a context that has already cleared the
    Cloudflare gate (first navigation to the site root). The managed challenge
    re-clears transparently on subsequent same-origin navigations.
    """
    page.goto(_results_url(begin, end, page_num), wait_until="domcontentloaded",
              timeout=60000)
    time.sleep(settle_seconds)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    return extract_grid_text(page)


def iter_window_rows(page, begin: date, end: date, max_pages: int = 60,
                     polite_delay: float = 1.2):
    """Yield parsed rows across all pages of a recorded-date window.

    neumo paginates via &page=N at 50 rows/page. We advance pages until a page
    yields no new doc numbers (or repeats the previous page's first doc number),
    which marks the end — robust against neumo clamping page beyond the last.
    """
    prev_first = None
    seen_docs: set[str] = set()
    for pnum in range(1, max_pages + 1):
        grid_text = render_page(page, begin, end, pnum)
        rows = parse_rows_from_text(grid_text)
        if not rows:
            break
        first_doc = rows[0].get("doc_number")
        if first_doc and first_doc == prev_first:
            # page didn't advance (clamped at last page) — stop
            break
        prev_first = first_doc
        new_in_page = 0
        for r in rows:
            dn = r.get("doc_number")
            if dn and dn not in seen_docs:
                seen_docs.add(dn)
                new_in_page += 1
                yield r
        if new_in_page == 0:
            break
        time.sleep(polite_delay)


# ── 2. parse ─────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


# The grid renders rows as text; columns are:
#   GRANTOR  GRANTEE  DOC TYPE  RECORDED DATE  DOC NUMBER  BOOK/VOLUME/PAGE  TOWN  LEGAL DESCRIPTION
# In the DOM these are table cells. We parse from the inner_text of the results
# table, where each row is tab/newline-delimited. We anchor on the DOC NUMBER
# (12-digit neumo id, e.g. 202600116672) and the RECORDED DATE (m/d/yyyy) which
# are unambiguous, then take the cells around them.
_ROW_RE = re.compile(
    r"(?P<grantor>.+?)\t(?P<grantee>.+?)\t(?P<doctype>[A-Z][A-Z '/&.-]+?)\t"
    r"(?P<recorded>\d{1,2}/\d{1,2}/20\d{2})\t(?P<docnum>\d{10,14})\t"
    r"(?P<bvp>[^\t]*)\t(?P<town>[A-Z .]+?)\t(?P<legal>[^\n]*)"
)


def parse_rows_from_text(grid_text: str) -> list[dict]:
    """Parse rows from the results-table inner_text (tab-delimited cells)."""
    rows = []
    for m in _ROW_RE.finditer(grid_text):
        try:
            iso = datetime.strptime(m.group("recorded"), "%m/%d/%Y").date().isoformat()
        except ValueError:
            iso = None
        rows.append({
            "grantor": _clean(m.group("grantor")),
            "grantee": _clean(m.group("grantee")),
            "doc_type": _clean(m.group("doctype")),
            "recorded_date": iso,
            "doc_number": m.group("docnum"),
            "book_vol_page": _clean(m.group("bvp")),
            "town": _clean(m.group("town")),
            "legal_description": _clean(m.group("legal")),
        })
    return rows


# ── 3. emit ──────────────────────────────────────────────────────────────────

def _normalize_party_name(raw: str) -> str:
    return re.sub(r"[^A-Z ]", " ", (raw or "").upper()).strip()


def to_signal_row(row: dict) -> dict | None:
    """Map a parsed recorder row to a raw_signals_v3 row (proven shape).

    For an estate/death instrument the GRANTOR is the decedent or the estate;
    the GRANTEE is the heir / personal representative (the lead contact). We put
    the decedent first (party_names[0]) because the matcher reads [0] as the
    name to match against parcels_v3 owners — and the deceased is the one still
    on title in the assessor roll.
    """
    sig = classify_doc_type(row.get("doc_type"))
    if not sig:
        return None
    decedent = row.get("grantor")
    if not decedent or not row.get("doc_number"):
        return None

    parties = [{"raw": decedent, "normalized": _normalize_party_name(decedent),
                "role": "decedent", "matchable": True}]
    heir = row.get("grantee")
    if heir and heir.upper() != decedent.upper():
        parties.append({"raw": heir, "normalized": _normalize_party_name(heir),
                        "role": "personal_representative", "matchable": False})

    return {
        "source_type": "tx_dallas_recorder",
        "signal_type": sig,
        "trust_level": "high",
        "party_names": parties,
        "event_date": row.get("recorded_date"),
        "jurisdiction": "TX_DALLAS",
        "property_hint": row.get("legal_description") or row.get("town"),
        "document_ref": row.get("doc_number"),
        "raw_data": {
            "doc_number": row.get("doc_number"),
            "doc_type": row.get("doc_type"),
            "grantor": decedent,
            "grantee": heir,
            "town": row.get("town"),
            "book_vol_page": row.get("book_vol_page"),
            "legal_description": row.get("legal_description"),
            "harvester": "dallas_recorder",
        },
    }


# ── orchestration helper (used by the runner) ─────────────────────────────────

def extract_grid_text(page) -> str:
    """Return the inner_text of the results table (or whole body as fallback)."""
    try:
        el = page.query_selector("table") or page.query_selector("[role='table']")
        if el:
            return el.inner_text()
    except Exception:
        pass
    return page.inner_text("body")
