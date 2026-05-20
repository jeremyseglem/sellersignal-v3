"""
Snohomish County Daily New Case Report harvester.

Downloads and parses Snohomish County Superior Court's "Daily New Case
Report" PDF — published by the County Clerk's office every business day,
no reCAPTCHA, no subscription, no authentication. Writes one
raw_signals_v3 row per qualifying case (one row per case_number, not per
party — parties get bundled into the row's party_names JSONB array).

────────────────────────────────────────────────────────────────────────
WHY THIS HARVESTER EXISTS (and why it's different from KC's)
────────────────────────────────────────────────────────────────────────
King County built its own custom court records portal (kc_superior_court.
py targets that). Every other Washington county uses the statewide JIS
portal at dw.courts.wa.gov, which is reCAPTCHA-gated and only supports
name-search or case-number-search — no "give me all probate cases in
date range" discovery query.

The unlock for non-KC counties is the daily PDF reports many county
clerks publish. Snohomish's are at:

    https://snohomishcountywa.gov/5516/Daily-New-Case-and-Judgment-Audit-Report

Each business day produces a separate PDF whose URL contains a per-day
DocumentCenter ID. We scrape the landing page to map dates → IDs, then
download the PDFs.

This pattern is expected to generalize to Pierce, Thurston, Whatcom,
Kitsap, and most other WA counties. See MANIFESTO "WA court system
architecture" section.

────────────────────────────────────────────────────────────────────────
WHAT WE EXTRACT (and what we don't, yet)
────────────────────────────────────────────────────────────────────────
The PDF contains a structured table:

    Case Number  | File Date  | Category | Type Code | Type Desc       | Connection | Party
    26-3-01021-31| 5/15/2026  | Family   | DIC       | Dissolution of  | PET        | KAUR, TAYLOR LYNN
                 |            |          |           | Marriage        |            |
    26-4-01015-31| 5/18/2026  | Probate  | EST       | Estate          | DEC        | Zettl, Judith Ann

Case-type codes WE EXTRACT (Phase 1 launch — Tier 1 signals):
    EST, WLL, TRS, GDN   → signal_type='probate'
    DIC, DIN             → signal_type='divorce'

Case-type codes WE SKIP (will reconsider for Phase 2):
    TAXDOR, TAXESD, TAXLI  Tax warrants are business-debt judgments, NOT
                           real property foreclosures. They become real
                           property events only on subsequent "Execution -
                           Real Property" filings (which appear in the
                           Judgment Audit Report — a separate report).
                           Skipping these in v1 avoids polluting briefings
                           with non-property signals.
    COM, ABJ, MST2, CPO,   Civil cases (commercial disputes, minor settle-
    UNDRES, ADL, TRJ,      ments, abstracts of judgment, civil protection
    EXT, QTI               orders) — none are direct property signals.

Connection-type mapping (PDF code → our role string):
    DEC      → 'decedent'    (probate)
    PET      → 'petitioner'  (probate PR-once-appointed, OR divorce filer)
    RSP      → 'respondent'  (divorce respondent, guardianship subject)
    ATY/ATYZ → 'attorney'    (recorded but the matcher ignores attorneys)
    WIPPET   → 'petitioner-protected'  (info protected; surfaced raw only)
    WIPRSP   → 'respondent-protected'  (info protected; surfaced raw only)

────────────────────────────────────────────────────────────────────────
PERSONAL REPRESENTATIVE LIMITATION (the day-1 gap)
────────────────────────────────────────────────────────────────────────
On the day a probate case is FILED, only the decedent is named. The
Personal Representative is appointed in a subsequent Petition for
Letters Testamentary, typically weeks later. So probate signals from
this harvester land in raw_signals_v3 with role='decedent' only.

The matcher links the decedent to the property's canonical owner — if
they match, the lead launches in contact_status='no_pr_yet' state. The
dossier UI handles this state correctly (shows the "PR pending" wait
pattern, no Call Now button).

Phase 2 PR enrichment is a separate workstream (statewide JIS scrape or
Odyssey Portal subscription). See MANIFESTO for the options.

────────────────────────────────────────────────────────────────────────
SOURCE-TYPE TAG IN raw_signals_v3
────────────────────────────────────────────────────────────────────────
We use 'wa_state_courts' (the same source_type as the KC harvester)
because downstream matching logic doesn't need to distinguish KC court
filings from Snohomish court filings — they're both first-party court
records writing to the same schema. The 'jurisdiction' field
('WA_SNOHOMISH' vs 'WA_KING') is what differentiates them for queries
that need to.
"""
from __future__ import annotations

import io
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LANDING_URL = (
    "https://snohomishcountywa.gov/5516/Daily-New-Case-and-Judgment-Audit-Report"
)
DOCUMENT_BASE = "https://snohomishcountywa.gov"

USER_AGENT = "SellerSignal-Snohomish-Daily-Harvester/1.0"
HTTP_TIMEOUT = 30
POLITE_DELAY_SECS = 1.0  # pause between PDF downloads

# Case-type code → (signal_type, label)
# Keep this dict authoritative — adding a new code here is the only place
# Phase-2 expansion needs to touch (e.g., adding 'TRJ' or 'TAXDOR' once we
# decide they're useful signals).
CASE_TYPE_MAP: dict[str, tuple[str, str]] = {
    "EST": ("probate", "Estate"),
    "WLL": ("probate", "Will Only"),
    "TRS": ("probate", "Trust"),
    "GDN": ("probate", "Guardianship"),
    "DIC": ("divorce", "Dissolution of Marriage"),
    "DIN": ("divorce", "Dissolution of Marriage"),
}

# Connection-type code → role string in party_names JSONB
CONNECTION_TYPE_MAP: dict[str, str] = {
    "DEC":    "decedent",
    "PET":    "petitioner",
    "RSP":    "respondent",
    "ATY":    "attorney",
    "ATYZ":   "attorney",
    "WIPPET": "petitioner-protected",
    "WIPRSP": "respondent-protected",
    "MNR":    "minor",
    "PLA":    "plaintiff",   # rare for our case types; recorded for completeness
    "DEF":    "defendant",
    "INV":    "involved",    # appears on trust cases
    "TRS":    "trustee",
}

# Roles whose names the matcher should consider as ownership-relevant for
# matching against parcels_v3 owners. Attorneys, minors, and the "involved"
# party do NOT belong here — they're recorded for human review but not for
# name-based matching.
MATCHABLE_ROLES = {"decedent", "petitioner", "respondent", "trustee", "defendant"}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class IndexEntry:
    """One row of the landing-page index — a single date's report."""
    report_date: date
    doc_id: str
    title: str
    url: str


@dataclass
class CasePartyRow:
    """One row from the PDF table — a (case, party) pair."""
    case_number:     str
    file_date:       Optional[date]
    category:        str           # 'Civil', 'Family', 'Probate or Family', etc.
    type_code:       str           # 'EST', 'DIC', etc.
    type_desc:       str           # full text e.g. 'Dissolution of Marriage'
    connection_type: str           # 'DEC', 'PET', etc.
    party_raw:       str           # 'Zettl, Judith Ann'


@dataclass
class ParsedCase:
    """Aggregated case — multiple party rows collapsed into one record."""
    case_number: str
    file_date:   Optional[date]
    type_code:   str
    type_desc:   str
    parties:     list[CasePartyRow] = field(default_factory=list)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes:
    """GET a URL. Raises on non-200."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()


# ── Step 1: scrape the landing page index ────────────────────────────────────

# Pattern: href="/DocumentCenter/View/{id}/{Month-DD-YYYY}-New-Case-Report"
# (sometimes the year suffix is missing in the URL slug, so be permissive).
_INDEX_LINK_RE = re.compile(
    r'href=["\'](?P<href>/DocumentCenter/View/(?P<id>\d+)/'
    r'(?P<slug>[^"\']*New[-_]Case[-_]Report[^"\']*))["\']',
    re.IGNORECASE,
)

# Pattern: the visible link text contains "Month DD, YYYY New Case Report"
# We match against the page text near each href.
_DATE_RE = re.compile(
    r'(?P<month>January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})',
    re.IGNORECASE,
)

_MONTH_NAME_TO_NUM = {
    name.lower(): num for num, name in enumerate(
        ["January","February","March","April","May","June","July","August",
         "September","October","November","December"], start=1)
}


def _parse_date_from_slug(slug: str) -> Optional[date]:
    """
    Extract the report's date from the URL slug, e.g.
    'May-18-2026-New-Case-Report' → date(2026, 5, 18).
    """
    m = re.match(
        r'^(?P<month>\w+)[-_](?P<day>\d{1,2})[-_](?P<year>\d{4})',
        slug,
    )
    if not m:
        return None
    month_num = _MONTH_NAME_TO_NUM.get(m.group("month").lower())
    if not month_num:
        return None
    try:
        return date(int(m.group("year")), month_num, int(m.group("day")))
    except ValueError:
        return None


def fetch_index(landing_url: str = LANDING_URL) -> list[IndexEntry]:
    """
    Scrape the Snohomish daily reports landing page and return a list of
    available New Case Reports with their dates + URLs.

    Returns newest-first by report_date. Skips Judgment Audit Reports (we
    only want New Case Reports).
    """
    html = _http_get(landing_url).decode("utf-8", errors="replace")

    entries: list[IndexEntry] = []
    seen_doc_ids: set[str] = set()
    for m in _INDEX_LINK_RE.finditer(html):
        doc_id = m.group("id")
        slug   = m.group("slug")
        href   = m.group("href")

        if doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(doc_id)

        report_date = _parse_date_from_slug(slug)
        if not report_date:
            log.debug(f"could not parse date from slug: {slug!r}")
            continue

        entries.append(IndexEntry(
            report_date = report_date,
            doc_id      = doc_id,
            title       = slug.replace("-", " "),
            url         = DOCUMENT_BASE + href,
        ))

    entries.sort(key=lambda e: e.report_date, reverse=True)
    return entries


# ── Step 2: download + extract text from a single PDF ────────────────────────

def _pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Extract text from a PDF. Prefers pdftotext (better column preservation
    via -layout). Falls back to pypdf if pdftotext isn't installed in the
    container.
    """
    # Try pdftotext first
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = f.name
    try:
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", pdf_path, "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Fallback: pypdf
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(p.extract_text() or "" for p in r.pages)
        except ImportError:
            raise RuntimeError(
                "Neither pdftotext nor pypdf available for PDF extraction"
            )
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass


# ── Step 3: parse rows out of the PDF text ────────────────────────────────────

# Each row of the PDF table looks deceptively simple but has two visual
# layouts depending on whether pdftotext -layout wrapped the long
# "type description" text onto its own line.
#
# Layout A (short type desc on same line as data row):
#   26-2-04993-31  5/15/2026  Civil    ABJ  ABJ Abstract of Judgment   ATY  Abdulle, Asha A
#
# Layout B (type desc wraps to a separate line above; data row has just
# the type code):
#                                              DIC Dissolution of Marriage   ← previous line
#   26-3-01021-31  5/15/2026  Family   DIC                           ATY  Ehrlich, Daniel Benn
#
# What's invariant: the data row always starts with `{case#}  {date}` and
# contains exactly one connection-type code followed by the party name.
# The connection codes are a fixed enumeration (DEC, PET, RSP, ATY,
# WIPPET, etc.) — we anchor on THAT set, not on a generic uppercase-token
# pattern. The generic-pattern approach broke on party names that
# happened to be all uppercase (e.g., "ALVIAR, CHENG JIANG" → "JIANG"
# would be misread as the connection code).

# Anchor: case number + date prefix identifies a candidate data row.
_ROW_PREFIX_RE = re.compile(
    r'^\s*(?P<case>\d{2}-\d-\d{5}-\d+)\s+'
    r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
    r'(?P<rest>.+?)\s*$',
    re.MULTILINE,
)

# Connection code matcher — uses the known set from CONNECTION_TYPE_MAP
# (sorted longest-first so 'WIPPET' wins before 'WIP', etc.). Unanchored
# so we can find ALL occurrences and pick the rightmost — important for
# rows where the type code matches a connection code (e.g., TRS Trust
# cases have TRS as type AND can have TRS as a party connection-type,
# meaning the regex must NOT match the left-most TRS).
_KNOWN_CONN_CODES_SORTED = sorted(CONNECTION_TYPE_MAP.keys(),
                                  key=len, reverse=True)
_CONN_TOKEN_RE = re.compile(
    r'(?<=\s)(?P<conn>' + '|'.join(re.escape(c) for c in _KNOWN_CONN_CODES_SORTED)
    + r')(?=\s|$)'
)

# Type-code matcher — first standalone all-caps token after the date,
# matching the keys in CASE_TYPE_MAP plus any other 2-7 char uppercase
# token (so we can capture non-Tier-1 codes like TAXDOR / COM / ABJ for
# stats / future expansion).
_TYPE_CODE_RE = re.compile(r'(?:^|\s)([A-Z][A-Z0-9]{1,7})(?:\s|$)')


def _parse_row_line(case: str, date_str: str, rest: str) -> Optional[CasePartyRow]:
    """
    Given the matched case_number + date + rest-of-line, extract the
    connection type + type code + party. Returns None if the row's
    connection code isn't one we recognize (most likely it's a header
    or footer line that incidentally matched the prefix).
    """
    # Parse date (mm/dd/yyyy)
    try:
        mo, d, y = date_str.split("/")
        fd: Optional[date] = date(int(y), int(mo), int(d))
    except (ValueError, IndexError):
        fd = None

    # Find ALL connection-code occurrences and take the rightmost. This
    # is the safety against rows like:
    #   "TRS  TRS Trust  ATY  Andrus, Peter J."   ← type=TRS, conn=ATY
    #   "TRS  TRS Trust  TRS  Brashear, Sheila"   ← type=TRS, conn=TRS
    # Leftmost-match would pick the type-code's TRS; rightmost picks the
    # actual connection code.
    padded = " " + rest
    matches = list(_CONN_TOKEN_RE.finditer(padded))
    if not matches:
        return None
    last = matches[-1]
    conn   = last.group("conn")
    party  = padded[last.end():].strip()
    middle = padded[:last.start()].strip()

    # Find the type code in the middle portion. It's the first all-caps
    # token there.
    tc_match = _TYPE_CODE_RE.search(" " + middle)
    type_code = tc_match.group(1) if tc_match else ""

    # Category — best-effort: leading mixed-case word(s) before the type code
    category = ""
    if type_code and tc_match:
        cat_part = middle[:tc_match.start()].strip()
        category = " ".join(w for w in cat_part.split() if w.replace(" ", "").isalpha())

    return CasePartyRow(
        case_number     = case,
        file_date       = fd,
        category        = category,
        type_code       = type_code,
        type_desc       = "",  # not reliably extractable; type_code is the truth
        connection_type = conn,
        party_raw       = party,
    )


def parse_report(pdf_text: str) -> list[CasePartyRow]:
    """
    Parse a New Case Report's text into a list of CasePartyRow.

    Page headers/footers ("Report Run Time", "Page N of M",
    "Snohomish County Superior Court", "CASE-New Case Filings", etc.)
    are filtered out by virtue of not matching the case#+date prefix
    OR not containing a known connection code.
    """
    rows: list[CasePartyRow] = []
    for m in _ROW_PREFIX_RE.finditer(pdf_text):
        parsed = _parse_row_line(m.group("case"), m.group("date"), m.group("rest"))
        if parsed is not None:
            rows.append(parsed)
    return rows


def group_by_case(rows: Iterable[CasePartyRow]) -> list[ParsedCase]:
    """Collapse party rows into one ParsedCase per unique case_number."""
    cases: dict[str, ParsedCase] = {}
    for r in rows:
        c = cases.get(r.case_number)
        if c is None:
            c = ParsedCase(
                case_number = r.case_number,
                file_date   = r.file_date,
                type_code   = r.type_code,
                type_desc   = r.type_desc,
            )
            cases[r.case_number] = c
        c.parties.append(r)
        # Keep the strongest fields if duplicate rows differ
        if r.file_date and not c.file_date:
            c.file_date = r.file_date
        if r.type_desc and len(r.type_desc) > len(c.type_desc):
            c.type_desc = r.type_desc
    return list(cases.values())


# ── Step 4: build raw_signals_v3 records from parsed cases ────────────────────

def _normalize_party_name(raw: str) -> dict:
    """
    Normalize a party name into a structured form.

    Snohomish reports use both "LAST, FIRST [MIDDLE]" (often uppercase)
    and "First Last" (mixed case). We extract a best-effort {first, last,
    middle} tuple for the matcher's canonicalizer.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"first": "", "last": "", "middle": ""}

    # "LAST, FIRST MIDDLE"
    if "," in raw:
        last_part, _, rest = raw.partition(",")
        last = last_part.strip()
        first_middle = rest.strip().split()
        first  = first_middle[0] if first_middle else ""
        middle = " ".join(first_middle[1:]) if len(first_middle) > 1 else ""
        return {"first": first, "last": last, "middle": middle}

    # "First Last" or "First Middle Last"
    parts = raw.split()
    if len(parts) == 1:
        return {"first": "", "last": parts[0], "middle": ""}
    if len(parts) == 2:
        return {"first": parts[0], "last": parts[1], "middle": ""}
    return {
        "first":  parts[0],
        "last":   parts[-1],
        "middle": " ".join(parts[1:-1]),
    }


def build_signal_row(case: ParsedCase, jurisdiction: str = "WA_SNOHOMISH") -> Optional[dict]:
    """
    Map a ParsedCase to a raw_signals_v3 row dict, or None if the case's
    type_code isn't one we extract.
    """
    mapping = CASE_TYPE_MAP.get(case.type_code)
    if not mapping:
        return None
    signal_type, _label = mapping

    party_names: list[dict] = []
    for p in case.parties:
        role = CONNECTION_TYPE_MAP.get(p.connection_type, p.connection_type.lower())
        # Skip empty parties (placeholder rows)
        if not p.party_raw.strip():
            continue
        party_names.append({
            "raw":        p.party_raw,
            "normalized": _normalize_party_name(p.party_raw),
            "role":       role,
            "matchable":  role in MATCHABLE_ROLES,
        })

    if not party_names:
        # Probate case with no parties parseable (shouldn't happen but
        # guard) — skip rather than write a half-empty signal.
        return None

    return {
        "source_type":   "wa_state_courts",
        "signal_type":   signal_type,
        "trust_level":   "high",   # court records are first-party authoritative
        "party_names":   party_names,
        "event_date":    case.file_date.isoformat() if case.file_date else None,
        "jurisdiction":  jurisdiction,
        "property_hint": None,     # filings don't list specific properties
        "document_ref":  case.case_number,
        "raw_data": {
            "case_number":  case.case_number,
            "file_date":    case.file_date.isoformat() if case.file_date else None,
            "type_code":    case.type_code,
            "type_desc":    case.type_desc,
            "category":     case.parties[0].category if case.parties else "",
            "harvester":    "snohomish_daily_report",
        },
    }


# ── Step 5: top-level harvest entry points ────────────────────────────────────

@dataclass
class HarvestResult:
    """Returned by harvest_*() so callers can log / persist stats."""
    report_dates:    list[date]
    rows_parsed:     int
    cases_parsed:    int
    signals_built:   int
    signals_by_type: dict[str, int]
    skipped_types:   dict[str, int]
    errors:          list[str] = field(default_factory=list)


def harvest_report(entry: IndexEntry) -> tuple[list[dict], HarvestResult]:
    """
    Download ONE report PDF, parse it, build signals.

    Returns (signal_rows, result_stats). The caller writes signal_rows to
    raw_signals_v3 (via the existing orchestrator.upsert_rows pattern).
    """
    log.info(f"snohomish: downloading {entry.report_date} report from {entry.url}")

    pdf_bytes = _http_get(entry.url, timeout=60)
    text = _pdf_to_text(pdf_bytes)
    rows = parse_report(text)
    cases = group_by_case(rows)

    signals: list[dict] = []
    by_type: dict[str, int] = {}
    skipped: dict[str, int] = {}
    for case in cases:
        sig = build_signal_row(case)
        if sig is None:
            skipped[case.type_code] = skipped.get(case.type_code, 0) + 1
            continue
        signals.append(sig)
        by_type[sig["signal_type"]] = by_type.get(sig["signal_type"], 0) + 1

    return signals, HarvestResult(
        report_dates    = [entry.report_date],
        rows_parsed     = len(rows),
        cases_parsed    = len(cases),
        signals_built   = len(signals),
        signals_by_type = by_type,
        skipped_types   = skipped,
    )


def harvest_recent(lookback_days: int = 7) -> tuple[list[dict], HarvestResult]:
    """
    Download the last `lookback_days` of New Case Reports and aggregate
    signals from all of them. Skips dates that aren't in the index (e.g.,
    weekends — Snohomish doesn't publish on Sat/Sun).

    Returns (all_signal_rows, combined_stats). Caller writes to
    raw_signals_v3; the unique constraint on (source_type, document_ref)
    handles dedup so re-running the same lookback is safe.
    """
    index = fetch_index()
    cutoff = date.today() - timedelta(days=lookback_days)
    targets = [e for e in index if e.report_date >= cutoff]

    log.info(f"snohomish: harvesting {len(targets)} report(s) "
             f"from {cutoff} forward")

    all_signals: list[dict] = []
    combined = HarvestResult(
        report_dates=[], rows_parsed=0, cases_parsed=0, signals_built=0,
        signals_by_type={}, skipped_types={},
    )

    for entry in sorted(targets, key=lambda e: e.report_date):
        try:
            signals, res = harvest_report(entry)
        except Exception as e:
            err = f"{entry.report_date}: {type(e).__name__}: {e}"
            log.warning(f"snohomish: harvest failed — {err}")
            combined.errors.append(err)
            continue

        all_signals.extend(signals)
        combined.report_dates.append(entry.report_date)
        combined.rows_parsed   += res.rows_parsed
        combined.cases_parsed  += res.cases_parsed
        combined.signals_built += res.signals_built
        for k, v in res.signals_by_type.items():
            combined.signals_by_type[k] = combined.signals_by_type.get(k, 0) + v
        for k, v in res.skipped_types.items():
            combined.skipped_types[k] = combined.skipped_types.get(k, 0) + v

        time.sleep(POLITE_DELAY_SECS)

    return all_signals, combined


# ── BaseHarvester adapter (for orchestrator integration) ──────────────────────

# The orchestrator at backend/harvesters/orchestrator.py:run_harvest() expects
# a BaseHarvester subclass that yields RawSignal objects. The function-based
# API above is what does the actual work; this class is a thin adapter so the
# Snohomish harvester plugs into the same run_harvest() entry point as the
# KC harvesters. Wiring the autofill task through /api/harvest/run with
# source='snohomish_daily' (rather than calling harvest_recent() directly)
# means we automatically get the matcher invocation, dedup, and stats
# accounting for free.

class SnohomishDailyReportHarvester:
    """
    Adapter exposing the snohomish_daily_report module as a BaseHarvester
    subclass for the orchestrator. Iterates the report index, downloads
    each PDF in the date range, and yields RawSignal objects.
    """
    source_type  = "wa_state_courts"
    jurisdiction = "WA_SNOHOMISH"

    def __init__(self, case_types: Optional[list[str]] = None):
        # case_types is ignored — we always extract our Tier 1 set
        # (probate + divorce) defined by CASE_TYPE_MAP. The argument is
        # accepted for interface compatibility with the KC harvester
        # registry signature in orchestrator.HARVESTERS.
        self.case_types = case_types

    def harvest(self, since: date, until: Optional[date] = None):
        """
        Yield one RawSignal per qualifying case across reports in
        [since, until]. Resilient to per-day failures: a malformed or
        unreachable PDF for one date doesn't stop the rest.
        """
        # Import here to avoid a circular-load risk at module import time
        # (base imports happen at orchestrator.py boot).
        from backend.harvesters.base import RawSignal, Party

        until = until or date.today()

        try:
            index = fetch_index()
        except Exception as e:
            log.error(f"snohomish: failed to fetch report index: {e}")
            return

        targets = [e for e in index if since <= e.report_date <= until]
        log.info(
            f"snohomish: harvesting {len(targets)} report(s) "
            f"from {since} to {until}"
        )

        for entry in sorted(targets, key=lambda e: e.report_date):
            try:
                pdf_bytes = _http_get(entry.url, timeout=60)
                text  = _pdf_to_text(pdf_bytes)
                rows  = parse_report(text)
                cases = group_by_case(rows)
            except Exception as e:
                log.warning(
                    f"snohomish: skipping {entry.report_date} — "
                    f"{type(e).__name__}: {e}"
                )
                continue

            for case in cases:
                mapping = CASE_TYPE_MAP.get(case.type_code)
                if not mapping:
                    continue
                signal_type, _label = mapping

                # Build the Party objects. Sort so matchable roles
                # (decedent, petitioner, etc.) come BEFORE attorneys and
                # protected-info parties — the matcher reads parties[0]
                # as the primary lookup name for some signal types.
                parties: list = []
                for p in case.parties:
                    raw = (p.party_raw or "").strip()
                    if not raw:
                        continue
                    role = CONNECTION_TYPE_MAP.get(
                        p.connection_type, p.connection_type.lower(),
                    )
                    norm = _normalize_party_name(raw)
                    parties.append(Party(
                        raw    = raw,
                        role   = role,
                        first  = norm.get("first") or None,
                        last   = norm.get("last")  or None,
                        middle = norm.get("middle") or None,
                    ))

                if not parties:
                    continue

                # Stable sort: matchable roles first, then by role name
                parties.sort(key=lambda p: (p.role not in MATCHABLE_ROLES, p.role))

                yield RawSignal(
                    source_type   = "wa_state_courts",
                    signal_type   = signal_type,
                    trust_level   = "high",
                    party_names   = parties,
                    document_ref  = case.case_number,
                    event_date    = case.file_date,
                    jurisdiction  = "WA_SNOHOMISH",
                    property_hint = None,
                    raw_data      = {
                        "case_number": case.case_number,
                        "file_date":   case.file_date.isoformat() if case.file_date else None,
                        "type_code":   case.type_code,
                        "type_desc":   case.type_desc,
                        "category":    case.parties[0].category if case.parties else "",
                        "harvester":   "snohomish_daily_report",
                        "report_date": entry.report_date.isoformat(),
                    },
                )

            time.sleep(POLITE_DELAY_SECS)
