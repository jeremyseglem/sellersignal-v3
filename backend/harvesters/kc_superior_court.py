"""
KC Superior Court harvester.

Pulls probate + divorce filings from King County Superior Court via the
Washington Courts public search at dw.courts.wa.gov.

Query approach: case-type + date-range (NOT per-name). One HTTP round-trip
per case type per date window. Returns all filings in that window.

Architecture: harvests ALL of KC (court-level), matcher filters to
canonicalized owners — which can be scoped to 98004 for the pilot and
expanded later with no harvester changes.

Form reverse-engineered from:
    https://dw.courts.wa.gov/index.cfm?fa=home.casesearch&tab=clj

Required form fields for case-type-by-date search:
    courtType=superior
    searchType=casetype
    CRT_ITL_NU_superior=S17         (King County Superior Court)
    TYP_CD_Superior=PG              (Probate/Guardianship) or DO (Domestic)
    fil_dt_from=MM-DD-YYYY
    fil_dt_to=MM-DD-YYYY
    pageSize=50
    pageIndex=1
    saveHistory=1
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Iterator, Optional

from bs4 import BeautifulSoup

from .base import BaseHarvester, Party, RawSignal

log = logging.getLogger(__name__)

BASE_URL = "https://dw.courts.wa.gov"
SEARCH_URL = f"{BASE_URL}/index.cfm?fa=home.casesearch&terms=accept&flashform=0&tab=clj"
SUBMIT_URL = f"{BASE_URL}/index.cfm?fa=home.namelist"

# Case type -> (WA code, signal_type for downstream scoring)
CASE_TYPES = {
    "probate":  ("PG", "probate"),
    "divorce":  ("DO", "divorce"),
    # Civil includes NOD, trustee sales, lis pendens — but mixed with everything
    # else. We enable it but downstream filtering on case sub-type matters.
    # "civil": ("CV", "civil"),
}

# King County Superior Court code
KC_COURT_CODE = "S17"


class KCSuperiorCourtHarvester(BaseHarvester):
    source_type = "wa_state_courts"
    jurisdiction = "WA_KING"

    # Polite rate limiting between page fetches
    request_delay_seconds = 1.0

    # Court paginates at 10 by default; ask for 50 to reduce round-trips
    page_size = 50

    # Max pages to walk per (case_type, window). Hard safety bound.
    max_pages = 40

    def __init__(self, case_types: Optional[list[str]] = None):
        """
        case_types: subset of CASE_TYPES keys to harvest. Defaults to all.
        """
        self.case_types = case_types or list(CASE_TYPES.keys())
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = self.build_session()
            # Seed the terms-accept cookie by hitting the landing page
            self._session.get(SEARCH_URL, timeout=30)
        return self._session

    # ─── Public API ────────────────────────────────────────────────────

    def harvest(
        self,
        since: date,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        """
        Yield RawSignals for all cases filed in [since, until] across
        configured case types in King County Superior Court.
        """
        until = until or date.today()

        for case_key in self.case_types:
            type_code, signal_type = CASE_TYPES[case_key]
            log.info(f"Harvesting {case_key} ({type_code}) {since} -> {until}")
            yield from self._harvest_type(type_code, signal_type, since, until)

    # ─── Internals ─────────────────────────────────────────────────────

    def _harvest_type(
        self,
        type_code: str,
        signal_type: str,
        since: date,
        until: date,
    ) -> Iterator[RawSignal]:
        """Harvest one case type across a date range, paging through results."""
        page = 1
        total_seen = 0

        while page <= self.max_pages:
            html = self._post_search(type_code, since, until, page)
            soup = BeautifulSoup(html, "html.parser")

            rows = self._parse_result_rows(soup)
            if not rows:
                log.info(f"  page {page}: no rows, stopping")
                break

            for row in rows:
                signal = self._row_to_signal(row, signal_type)
                if signal:
                    yield signal
                    total_seen += 1

            # Detect last page: if fewer rows than page_size, we're done
            if len(rows) < self.page_size:
                log.info(f"  page {page}: last page ({len(rows)} rows)")
                break

            page += 1
            time.sleep(self.request_delay_seconds)

        log.info(f"  {signal_type}: yielded {total_seen} rows across {page} page(s)")

    def _post_search(
        self,
        type_code: str,
        since: date,
        until: date,
        page: int,
    ) -> str:
        """POST the case-type-by-date form, return response HTML."""
        form = {
            "courtType":            "superior",
            "searchType":           "casetype",
            "selectedCourtName":    "KING COUNTY SUPERIOR COURT",
            "CRT_ITL_NU_superior":  KC_COURT_CODE,
            "TYP_CD_Superior":      type_code,
            "fil_dt_from":          since.strftime("%m-%d-%Y"),
            "fil_dt_to":            until.strftime("%m-%d-%Y"),
            "pageSize":             str(self.page_size),
            "pageIndex":            str(page),
            "saveHistory":          "1",
            # Empty fields required by the form even though we're doing
            # a case-type search, not a name search:
            "firstName":            "",
            "lastName":             "",
            "MiddleInitial":        "",
            "Name_bus":             "",
            "caseNumber":           "",
        }

        resp = self.session.post(
            SUBMIT_URL,
            data=form,
            timeout=30,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

    def _parse_result_rows(self, soup: BeautifulSoup) -> list[dict]:
        """
        Extract case rows from the search results HTML.

        The WA courts result layout shows each case as a table row with:
          - Case Number (link to case detail)
          - Case Title (parties)
          - File Date
          - Court
        The exact HTML shape varies; we use resilient selectors.
        """
        rows = []

        # Primary strategy: look for result table rows with case-link cells.
        # The portal renders results in a <table> with class 'hits' or similar.
        # Fall back to any <tr> that has a case-number-looking cell.
        candidate_tables = soup.find_all("table")
        for tbl in candidate_tables:
            trs = tbl.find_all("tr")
            for tr in trs:
                cells = tr.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                # Look for a case-number pattern anywhere in the row:
                # WA case numbers: NN-N-NNNNN-N (or similar variants)
                row_text = tr.get_text(" | ", strip=True)
                case_match = re.search(
                    r"\b(\d{2}-\d-\d{3,6}-\d{1,2}(?:-[A-Z]{3})?)\b",
                    row_text,
                )
                if not case_match:
                    continue

                # Extract case link (detail URL) if present
                link = tr.find("a", href=True)
                detail_url = None
                if link and "casesummary" in link["href"].lower():
                    detail_url = link["href"]
                    if detail_url.startswith("/"):
                        detail_url = BASE_URL + detail_url

                # Heuristic: cells are typically [Case #, Title, File Date, Court]
                # but the order varies. We grab text by content type.
                texts = [c.get_text(" ", strip=True) for c in cells]

                case_number = case_match.group(1)
                title = next((t for t in texts if "vs" in t.lower() or "in re" in t.lower() or "estate of" in t.lower()), None)
                # File date: find MM/DD/YYYY or M/D/YYYY in the row
                date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", row_text)
                file_date = date_match.group(1) if date_match else None

                rows.append({
                    "case_number":  case_number,
                    "title":        title or texts[1] if len(texts) > 1 else "",
                    "file_date_raw": file_date,
                    "detail_url":   detail_url,
                    "raw_row":      texts,
                })

        return rows

    def _row_to_signal(self, row: dict, signal_type: str) -> Optional[RawSignal]:
        """Convert a parsed search result row into a RawSignal."""
        case_number = row.get("case_number")
        if not case_number:
            return None

        title = row.get("title") or ""
        parties = self._parse_parties_from_title(title, signal_type)
        if not parties:
            # No extractable parties — skip (useless for matching)
            log.debug(f"Skipping {case_number}: no parties extractable from '{title}'")
            return None

        # Parse file date (MM/DD/YYYY -> date)
        event_date = None
        if row.get("file_date_raw"):
            try:
                parts = row["file_date_raw"].split("/")
                event_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass

        return RawSignal(
            source_type="wa_state_courts",
            signal_type=signal_type,
            trust_level="high",                       # Court records are HIGH trust
            party_names=parties,
            event_date=event_date,
            jurisdiction="WA_KING",
            document_ref=case_number,
            raw_data={
                "case_title":   title,
                "detail_url":   row.get("detail_url"),
                "raw_cells":    row.get("raw_row"),
            },
        )

    @staticmethod
    def _parse_parties_from_title(title: str, signal_type: str) -> list[Party]:
        """
        Best-effort party extraction from a case title string.

        Typical patterns:
          - "IN RE ESTATE OF SMITH, JOHN Q"          (probate)
          - "SMITH, JANE vs SMITH, JOHN"             (divorce)
          - "IN RE GUARDIANSHIP OF DOE, JOHN"        (probate)
          - "IN THE MATTER OF THE ESTATE OF ..."     (probate variant)

        Returns zero or more Party objects. Role is inferred by signal
        type (decedent for probate, petitioner/respondent for divorce).
        """
        title = (title or "").strip()
        if not title:
            return []

        parties: list[Party] = []

        # Probate: "IN RE [GUARDIANSHIP|ESTATE] OF LASTNAME, FIRSTNAME ..."
        m = re.search(
            r"\b(?:ESTATE|GUARDIANSHIP)\s+OF\s+([^,]+?,\s*[A-Za-z .'\-]+)",
            title,
            re.IGNORECASE,
        )
        if m:
            raw = m.group(1).strip().rstrip(".,;")
            role = "decedent" if "estate" in title.lower() else "ward"
            parties.append(Party(raw=raw, role=role, **_split_lastfirst(raw)))
            return parties

        # Divorce: "PETITIONER AND RESPONDENT" (KC Superior Court format,
        # per existing ingest code). Handles optional "ET AL" / "ET ANO"
        # suffixes on the petitioner side.
        # Note: other WA counties may use "vs" — we accept both.
        m = re.search(
            r"^\s*(.+?)\s+(?:AND|vs\.?|v\.)\s+(.+?)\s*$",
            title,
            re.IGNORECASE,
        )
        if m:
            a = m.group(1).strip().rstrip(".,;")
            b = m.group(2).strip().rstrip(".,;")
            # Strip ET AL / ET ANO from petitioner
            a = re.sub(r"\s+ET\s+A(NO|L)\s*$", "", a, flags=re.IGNORECASE).strip()

            parties.append(Party(raw=a, role="petitioner", **_split_lastfirst(a)))
            parties.append(Party(raw=b, role="respondent", **_split_lastfirst(b)))
            return parties

        # Fallback: take the whole title as a single party (best effort).
        # The canonicalizer downstream will attempt to parse further.
        if len(title) < 200 and any(c.isalpha() for c in title):
            parties.append(Party(raw=title, role="party"))

        return parties


# ─── Helpers ───────────────────────────────────────────────────────────

def _split_lastfirst(raw: str) -> dict:
    """
    Split "LAST, FIRST M" form into components.

    Returns a dict with first/last/middle/suffix (omits missing keys).
    Safe to pass as **kwargs to Party(...).
    """
    if "," not in raw:
        return {}

    last, rest = raw.split(",", 1)
    last = last.strip()
    rest = rest.strip()

    # Suffix: trailing Jr/Sr/II/III/IV
    suffix = None
    suffix_match = re.search(r"\b(JR|SR|II|III|IV)\b\.?$", rest, re.IGNORECASE)
    if suffix_match:
        suffix = suffix_match.group(1).upper().rstrip(".")
        rest = rest[: suffix_match.start()].strip()

    tokens = rest.split()
    first = tokens[0] if tokens else None
    middle = " ".join(tokens[1:]) if len(tokens) > 1 else None

    out = {}
    if first:  out["first"] = first.title()
    if last:   out["last"] = last.title()
    if middle: out["middle"] = middle.title()
    if suffix: out["suffix"] = suffix
    return out
