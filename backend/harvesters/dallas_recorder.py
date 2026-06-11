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
# Matched by substring against the row's DOC TYPE cell. Calibrated to the ACTUAL
# Dallas County recording taxonomy observed 2026-06-11 (250-row sample, 06/02):
# Texas names its death->property instruments differently from AZ/WA. The
# workhorse is AFFIDAVIT OF HEIRSHIP (filed when an owner dies and heirs
# establish title without full probate) — names decedent + heirs + the parcel.
DEATH_DOCTYPE_SIGNALS = [
    ("AFFIDAVIT OF HEIRSHIP",     "probate"),   # primary TX death->title signal
    ("AFFIDAVIT OF DEATH",        "probate"),
    ("EXECUTOR",                  "probate"),    # EXECUTOR'S DEED
    ("ADMINISTRATOR",             "probate"),    # ADMINISTRATOR'S DEED
    ("PERSONAL REPRESENTATIVE",   "probate"),
    ("DISTRIBUTION",              "probate"),     # DEED OF DISTRIBUTION
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

def _results_url(begin: date, end: date) -> str:
    # The five params proven to render results. neumo ignores a URL `page`
    # param (verified 2026-06-11: page=4 returned page-1's first doc), so we
    # paginate by CLICKING the in-DOM next control, not via the URL.
    qs = urllib.parse.urlencode({
        "department": "RP",
        "recordedDateRange": f"{begin.strftime('%Y%m%d')},{end.strftime('%Y%m%d')}",
        "searchType": "quickSearch",
        "keywordSearch": "false",
        "searchOcrText": "false",
    })
    return f"{RESULTS_URL}?{qs}"


def _click_next(page) -> bool:
    """Click neumo's 'next page' control. Returns True if a click happened.

    Confirmed control (probe 2026-06-11): <button aria-label="next page">▶</button>,
    disabled on the last page. We check enabled-state to avoid a no-op click.
    """
    el = page.query_selector("button[aria-label='next page']")
    if el:
        try:
            if el.get_attribute("disabled") is not None or not el.is_enabled():
                return False
        except Exception:
            pass
        try:
            el.click()
            return True
        except Exception:
            pass
    # Fallback: the ▶ glyph
    try:
        el = page.query_selector("text=▶")
        if el and el.is_enabled():
            el.click()
            return True
    except Exception:
        pass
    return False


def iter_window_rows(page, begin: date, end: date, max_pages: int = 60,
                     polite_delay: float = 1.2):
    """Yield parsed rows across all pages of a recorded-date window by clicking
    neumo's next-page control until the first doc number stops changing.
    """
    page.goto(_results_url(begin, end), wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass

    prev_first = None
    seen_docs: set[str] = set()
    for _ in range(max_pages):
        grid_text = extract_grid_text(page)
        rows = parse_rows_from_text(grid_text)
        if not rows:
            # one retry: SPA may still be rendering
            time.sleep(3)
            rows = parse_rows_from_text(extract_grid_text(page))
            if not rows:
                break
        first_doc = rows[0].get("doc_number")
        if first_doc and first_doc == prev_first:
            break  # page didn't advance — last page
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
        if not _click_next(page):
            break
        time.sleep(polite_delay)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass


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
