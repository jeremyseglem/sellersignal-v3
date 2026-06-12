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
# Newer neumo tenants (Travis, Collin — 2026-06-12) do NOT auto-execute a
# search from /results URL params on direct page load; the search only fires
# via client-side navigation. UI_DRIVE=True makes iter_window_rows drive the
# real search form (aria-labeled date inputs + Search submit) instead of a
# direct URL load. Confirmed working via interactive capture on Collin:
# fill Starting/Ending Recorded Date, click Search -> grid renders with the
# same column structure the Dallas parser reads. Dallas keeps URL mode.
UI_DRIVE = False
HOME_URL = "https://dallas.tx.publicsearch.us/"
# Overridable by county runners that reuse this platform-generic module
# (e.g. run_travis_recorder.py sets RESULTS_URL + SOURCE_TYPE for Travis).
SOURCE_TYPE = "tx_dallas_recorder"
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


def _ui_drive_search(page, begin: date, end: date):
    """Drive the real search UI for tenants that don't auto-execute URL
    searches. Fills the recorded-date range and clicks Search; leaves the
    keyword box empty so the full grid (all doc types) comes back, exactly
    like Dallas's keyword-less URL search.

    Two tenant layouts observed (2026-06-12 captures):
      - Collin: Starting/Ending Recorded Date inputs render INLINE.
      - Travis: inputs collapsed behind a #date-range-select button
        (aria 'Recorded Date'); click to expand first.
    """
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)
    # dismiss any announcement banner that can cover controls
    try:
        dis = page.query_selector("button[aria-label='Dismiss announcement']")
        if dis:
            dis.click()
            time.sleep(1)
    except Exception:
        pass

    def _find_dates():
        return (page.query_selector("input[aria-label='Starting Recorded Date']"),
                page.query_selector("input[aria-label='Ending Recorded Date']"))

    start_el, end_el = _find_dates()
    if not (start_el and end_el):
        # Travis layout: expand the collapsed date-range panel first.
        toggle = (page.query_selector("#date-range-select")
                  or page.query_selector("button[aria-label='Recorded Date']")
                  or page.query_selector("button[aria-label='select date range']"))
        if toggle:
            toggle.click()
            time.sleep(2)
            start_el, end_el = _find_dates()
    if not (start_el and end_el):
        raise RuntimeError("UI_DRIVE: date inputs not found on search page")
    start_el.fill(begin.strftime("%m/%d/%Y"))
    end_el.fill(end.strftime("%m/%d/%Y"))
    btn = page.query_selector("button[aria-label='Search']")
    if not btn:
        raise RuntimeError("UI_DRIVE: Search button not found")
    btn.click()
    time.sleep(8)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    # diagnostics: prove the search actually navigated + grid presence
    try:
        head = page.inner_text("body")[:240].replace("\n", " ")
        print(f"    [ui_drive] url={page.url[:110]}")
        print(f"    [ui_drive] body_head={head[:200]}")
    except Exception:
        pass


def iter_window_rows(page, begin: date, end: date, max_pages: int = 60,
                     polite_delay: float = 1.2):
    """Yield parsed rows across all pages of a recorded-date window by clicking
    neumo's next-page control until the first doc number stops changing.
    """
    if UI_DRIVE:
        _ui_drive_search(page, begin, end)
    else:
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


def _strip_decd(name: str) -> str:
    """Remove trailing estate markers (DECD, DECEASED, FKA, AKA, EST OF) for matching."""
    n = (name or "").upper()
    n = re.sub(r"\b(DECD|DECEASED|EST(ATE)? OF|FKA|AKA|NKA|ET AL|ET UX)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def to_signal_row(row: dict) -> dict | None:
    """Map a parsed recorder row to a raw_signals_v3 row (proven shape).

    On a Texas AFFIDAVIT OF HEIRSHIP the recorder tags the deceased owner with a
    'DECD' suffix — and that party can appear in EITHER the grantor or grantee
    column (verified 2026-06-11: DECD landed on the grantee). The decedent is the
    one still on the DCAD roll, so we match on the DECD-tagged name (party_names[0]
    is read by the matcher against parcel owners). The other party is the
    affiant/heir (the lead contact). Falls back to grantor-as-decedent when
    neither party carries a DECD marker.
    """
    sig = classify_doc_type(row.get("doc_type"))
    if not sig:
        return None
    grantor = (row.get("grantor") or "").strip()
    grantee = (row.get("grantee") or "").strip()
    if not row.get("doc_number") or not (grantor or grantee):
        return None

    g_decd = "DECD" in grantor.upper() or "DECEASED" in grantor.upper()
    e_decd = "DECD" in grantee.upper() or "DECEASED" in grantee.upper()
    if e_decd and not g_decd:
        decedent_raw, heir_raw = grantee, grantor
    else:
        decedent_raw, heir_raw = grantor, grantee

    decedent_clean = _strip_decd(decedent_raw)
    if not decedent_clean:
        return None

    parties = [{"raw": decedent_raw, "normalized": _normalize_party_name(decedent_clean),
                "role": "decedent", "matchable": True}]
    if heir_raw and heir_raw.upper() != decedent_raw.upper():
        parties.append({"raw": heir_raw,
                        "normalized": _normalize_party_name(_strip_decd(heir_raw)),
                        "role": "personal_representative", "matchable": False})

    return {
        "source_type": SOURCE_TYPE,
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
            "grantor": grantor,
            "grantee": grantee,
            "decedent": decedent_raw,
            "heir": heir_raw,
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
