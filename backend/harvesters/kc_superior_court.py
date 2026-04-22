"""
KC Superior Court harvester.

Scrapes King County Superior Court's "Records Access Portal" (eCourt Public)
at dja-prd-ecexap1.kingcounty.gov. This is the authoritative KC system —
distinct from dw.courts.wa.gov (state-level) which doesn't support
date-range batch queries for KC.

Portal technology: Drupal + eCourt Public form renderer. Forms use
`data(FIELD_ID)` field naming with accompanying `_op` and `_incnull`
hidden fields. Each form submit requires a fresh `form_build_id` which
Drupal issues on GET.

Query approach: case-type + filing-date-range, single POST. The portal
natively supports "all probate filings between X and Y" — exactly the
per-filing architecture we need.

Case type codes (from the caseType URL param, also the data(199355)[]
select value):
    911110 = Criminal (1)
    411110 = Civil (2)
    211110 = Domestic/Family (3)
    511110 = Probate/Guardianship (4)

Result page layout: single <table class="searchResultsPage"> with rows:
    Case Number | Filing Date | Case Name | Charge/Cause | Next Hearing | Status

Pagination: GET `?page=N` appended to the results URL. Page size is
controlled by the ecp_searchResult_recordsPerPage select (values 20/50/100/150).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Iterator, Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseHarvester, Party, RawSignal

log = logging.getLogger(__name__)

BASE = "https://dja-prd-ecexap1.kingcounty.gov"
FORM_BASE_PATH = "/node/411"

# search_key → (caseType URL param, data(199355) select value, signal_type downstream)
CASE_TYPES = {
    "probate":  ("511110", "511110", "probate"),
    "divorce":  ("211110", "211110", "divorce"),
    # Civil (411110) not enabled — giant bucket with NOD, unlawful detainer,
    # lis pendens, contract disputes all mixed. Better to pull recorder data
    # separately for foreclosure-pressure signals.
}


class KCSuperiorCourtHarvester(BaseHarvester):
    source_type = "kc_superior_court"
    jurisdiction = "WA_KING"

    # Records per page (valid portal values: 20, 50, 100, 150)
    # Note: the portal's submit form ignores our page_size preference and
    # always returns 20/page. So pagination is our main mechanism.
    page_size = 20

    # Polite rate-limit between page fetches
    request_delay_seconds = 1.0

    # Max pages per (case_type, window). Safety bound.
    # 180-day window = ~3,600 probate filings KC-wide ≈ 180 pages @ 20/page.
    # 500 gives us headroom for divorce (~100/day = 500 pages over 6mo).
    max_pages = 500

    def __init__(self, case_types: Optional[list[str]] = None):
        self.case_types = case_types or list(CASE_TYPES.keys())

    # ─── Public API ────────────────────────────────────────────────────

    def harvest(
        self,
        since: date,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        until = until or date.today()

        for case_key in self.case_types:
            case_url_code, case_select_code, signal_type = CASE_TYPES[case_key]
            log.info(
                f"Harvesting {case_key} (code {case_select_code}) "
                f"{since.isoformat()} → {until.isoformat()}"
            )
            yield from self._harvest_type(
                case_url_code, case_select_code, signal_type, since, until
            )

    # ─── Internals ─────────────────────────────────────────────────────

    def _harvest_type(
        self,
        case_url_code: str,
        case_select_code: str,
        signal_type: str,
        since: date,
        until: date,
    ) -> Iterator[RawSignal]:
        session = self.build_session()
        form_ctx = self._open_search_form(session, case_url_code)

        # Page 1 = POST search
        html = self._post_search(
            session, case_url_code, case_select_code, form_ctx, since, until
        )

        page_idx = 0   # 0-based: page_idx=0 is first page, ?page=1 is second
        total = 0
        while page_idx < self.max_pages:
            rows = self._parse_result_rows(html)
            if not rows:
                log.info(f"  page {page_idx + 1}: no rows, stopping")
                break

            for row in rows:
                sig = self._row_to_signal(row, signal_type)
                if sig:
                    yield sig
                    total += 1

            # Stop condition: detect "no next page" by scanning for a
            # pagination link with ?page=(next). If we can't find a link
            # pointing to the next page number, this is the last page.
            next_page_idx = page_idx + 1
            if not self._has_next_page_link(html, next_page_idx):
                log.info(f"  page {page_idx + 1}: last page ({len(rows)} rows)")
                break

            page_idx += 1
            time.sleep(self.request_delay_seconds)
            html = self._get_next_page(session, case_url_code, page_idx)

        log.info(f"  {signal_type}: yielded {total} rows across {page_idx + 1} page(s)")

    def _has_next_page_link(self, html: str, next_page_idx: int) -> bool:
        """
        Return True if the current page has a pagination link pointing to
        ?page=<next_page_idx>. Drupal's eCourt uses 1-indexed ?page= values
        where ?page=1 is actually the 2nd page (the first page has no ?page=).
        """
        # Crude but reliable: look for the raw href pattern in the HTML
        # rather than DOM-walking (faster + less brittle).
        patterns = [
            f"page={next_page_idx}",
            f"page={next_page_idx}&",
            f"page={next_page_idx}\"",
            f"page={next_page_idx}'",
        ]
        return any(p in html for p in patterns)

    def build_session(self) -> requests.Session:
        s = super().build_session()
        s.max_redirects = 10
        return s

    def _open_search_form(self, session: requests.Session, case_url_code: str) -> dict:
        """GET the search form → extract form_build_id etc. Drupal requires these on POST."""
        url = f"{BASE}{FORM_BASE_PATH}?caseType={case_url_code}"
        r = session.get(url, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form")
        if not form:
            raise RuntimeError(f"No <form> found at {url}")

        def hidden(name: str) -> str:
            inp = form.find("input", attrs={"name": name})
            return inp.get("value", "") if inp else ""

        return {
            "form_build_id":    hidden("form_build_id"),
            "form_id":          hidden("form_id")         or "ecp_search_extend",
            "formId":           hidden("formId")          or "13341",
            "eCourtFormCode":   hidden("eCourtFormCode")  or "S-Case_Public_Portal_Types_1_2_3_4",
            "ecpFormId":        hidden("ecpFormId")       or "7",
        }

    def _post_search(
        self,
        session: requests.Session,
        case_url_code: str,
        case_select_code: str,
        form_ctx: dict,
        since: date,
        until: date,
    ) -> str:
        """POST the search form with the date range. Returns page-1 HTML."""
        url = f"{BASE}{FORM_BASE_PATH}?caseType={case_url_code}"
        from_str = since.strftime("%m/%d/%Y")
        to_str   = until.strftime("%m/%d/%Y")

        form = [
            ("formId",                  form_ctx["formId"]),
            # Case Type multi-select — scope to the type we want
            ("data(199355_op)",         "IN"),
            ("data(199355_incnull)",    "false"),
            ("data(199355)[]",          case_select_code),
            # Case Number (blank)
            ("data(199339_op)",         "CONTAINS"),
            ("data(199339_incnull)",    "false"),
            ("data(199339)",            ""),
            # Pre-1979 Case Number (blank)
            ("data(223968_op)",         "EQUALS"),
            ("data(223968_incnull)",    "false"),
            ("data(223968)",            ""),
            # Filing Date range — data(223972) + _right
            ("data(223972_op)",         "EQUALS"),
            ("data(223972_incnull)",    ""),
            ("data(223972)",            from_str),
            ("data(223972_right)",      to_str),
            # Name fields (blank)
            ("data(223967_op)",         "STARTS_WITH"),
            ("data(223967_incnull)",    "false"),
            ("data(223967)",            ""),
            ("data(223969_op)",         "STARTS_WITH"),
            ("data(223969_incnull)",    "false"),
            ("data(223969)",            ""),
            ("data(223973_op)",         "STARTS_WITH"),
            ("data(223973_incnull)",    "false"),
            ("data(223973)",            ""),
            ("data(223975_op)",         "STARTS_WITH"),
            ("data(223975_incnull)",    "false"),
            ("data(223975)",            ""),
            # Required Drupal/eCourt hidden fields
            ("eCourtFormCode",          form_ctx["eCourtFormCode"]),
            ("ecpFormId",               form_ctx["ecpFormId"]),
            ("op",                      "Search"),
            ("form_build_id",           form_ctx["form_build_id"]),
            ("form_id",                 form_ctx["form_id"]),
        ]

        resp = session.post(
            url,
            data=form,
            headers={"Referer": url},
            timeout=60,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

    def _get_next_page(self, session: requests.Session, case_url_code: str, page_idx: int) -> str:
        """GET page N of results. Drupal pagination = same URL + ?page=N."""
        url = f"{BASE}{FORM_BASE_PATH}?caseType={case_url_code}&page={page_idx}"
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.text

    def _parse_result_rows(self, html: str) -> list[dict]:
        """
        Extract case rows from the Drupal eCourt results table.
        Expected columns: [Case Number, Filing Date, Case Name, Charge/Cause,
        Next Hearing, Status]
        """
        soup = BeautifulSoup(html, "html.parser")

        # Find the results table — class contains 'searchResultsPage'
        table = None
        for tbl in soup.find_all("table"):
            classes = tbl.get("class") or []
            if any("searchResultsPage" in c for c in classes):
                table = tbl
                break

        # Fallback: any table whose header row looks right
        if table is None:
            for tbl in soup.find_all("table"):
                header = tbl.find("tr")
                if not header:
                    continue
                cells = [c.get_text(" ", strip=True).lower()
                         for c in header.find_all(["th", "td"])]
                if "case number" in cells and "filing date" in cells:
                    table = tbl
                    break

        if table is None:
            return []

        rows_out: list[dict] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]

            # Skip header
            if "Case Number" in texts[0]:
                continue

            # Case numbers look like '26-4-03246-4 SEA' — capture the stable portion
            m = re.search(r"(\d{2}-\d-\d{3,6}-\d{1,2})", texts[0])
            if not m:
                continue

            # Extract the portal's internal node ID from the case-number link.
            # Each case in search results is a link like <a href="?q=node/420/7629118">.
            # That trailing integer is a stable internal ID we need to visit
            # the case's Participants / Documents / Events tabs.
            internal_id = None
            first_link = cells[0].find("a", href=True)
            if first_link:
                id_match = re.search(r"/(\d+)(?:$|\?|#)", first_link["href"])
                if id_match:
                    internal_id = id_match.group(1)

            rows_out.append({
                "case_number":     m.group(1),
                "case_number_raw": texts[0],
                "filing_date_raw": texts[1] if len(texts) > 1 else "",
                "case_name":       texts[2] if len(texts) > 2 else "",
                "cause":           texts[3] if len(texts) > 3 else "",
                "next_hearing":    texts[4] if len(texts) > 4 else "",
                "status":          texts[5] if len(texts) > 5 else "",
                "internal_id":     internal_id,
            })

        return rows_out

    def _row_to_signal(self, row: dict, signal_type: str) -> Optional[RawSignal]:
        """Convert a parsed KC result row into a RawSignal."""
        # --- Fix 1: filter non-dissolution cases out of divorce stream ---
        # KC caseType 211110 (Family/Domestic) is a bucket containing:
        #   - "Dissolution w/ Children", "Dissolution w/ Real Property",
        #     "Dissolution - No Children" (THESE are real divorces we want)
        #   - "Petition for Entry of KC Support Order" (state-initiated child
        #     support — NOT a divorce, petitioner is STATE OF WASHINGTON)
        #   - "Out of State Support Registration /Foreign Judgment" (interstate
        #     support enforcement — NOT a divorce)
        #   - "Parentage" (paternity establishment — NOT a divorce)
        #   - "Modification" (modifying an existing order)
        # Only "Dissolution" cases represent actual marital breakups and thus
        # real seller signal. Everything else gets filtered here so it never
        # enters raw_signals_v3.
        if signal_type == "divorce":
            cause = (row.get("cause") or "").lower()
            if "dissolution" not in cause:
                log.debug(f"Skipping {row['case_number']}: cause='{cause}' "
                          f"is not a dissolution")
                return None

        parties = self._parse_parties(row["case_name"], signal_type)
        if not parties:
            log.debug(f"Skipping {row['case_number']}: no parties from "
                      f"'{row['case_name']}'")
            return None

        event_date = None
        if row["filing_date_raw"]:
            m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", row["filing_date_raw"])
            if m:
                try:
                    event_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                except ValueError:
                    pass

        return RawSignal(
            source_type=self.source_type,
            signal_type=signal_type,
            trust_level="high",
            party_names=parties,
            event_date=event_date,
            jurisdiction="WA_KING",
            document_ref=row["case_number"],
            raw_data={
                "case_number_raw": row["case_number_raw"],
                "case_name":       row["case_name"],
                "cause":           row["cause"],
                "next_hearing":    row["next_hearing"],
                "status":          row["status"],
                # Internal node ID for the portal — used later to fetch
                # Participants / Documents / Events tabs. Captured here so
                # we don't have to re-search to find it.
                "internal_id":     row.get("internal_id"),
            },
        )

    @staticmethod
    def _parse_parties(case_name: str, signal_type: str) -> list[Party]:
        """
        Extract parties from the KC 'Case Name' field.

        Probate formats observed:
          - "IN RE ALLISON SARAHI AGUIRRE MEDINA"
          - "IN RE ESTATE OF SMITH, JOHN Q"
          - "IN RE GUARDIANSHIP OF DOE, JOHN"
          - "ESTATE OF SMITH, JOHN"

        Divorce formats (per existing ingest):
          - "PETITIONER AND RESPONDENT"
          - "LASTNAME, FIRSTNAME AND LASTNAME, FIRSTNAME"
        """
        name = (case_name or "").strip()
        if not name:
            return []

        parties: list[Party] = []

        # "IN RE [ESTATE|GUARDIANSHIP] OF <n>"
        m = re.search(
            r"\bIN\s+RE\s+(?:THE\s+)?(?:ESTATE\s+OF|GUARDIANSHIP\s+OF)\s+(.+)",
            name,
            re.IGNORECASE,
        )
        if m:
            raw = m.group(1).strip().rstrip(".,;")
            role = "ward" if "guardian" in name.lower() else "decedent"
            parties.append(Party(raw=raw, role=role, **_split_name(raw)))
            return parties

        # "IN RE <n>" (common for minor settlements, name changes, probate variants)
        m = re.search(r"\bIN\s+RE\s+(.+)", name, re.IGNORECASE)
        if m and signal_type == "probate":
            raw = m.group(1).strip().rstrip(".,;")
            role = "decedent"
            if re.search(r"\b(MINOR|ADOPT|NAME\s+CHANGE)\b", raw, re.IGNORECASE):
                role = "subject"
            raw = re.sub(r"^(?:ESTATE|GUARDIANSHIP|MATTER)\s+OF\s+", "",
                         raw, flags=re.IGNORECASE)
            parties.append(Party(raw=raw, role=role, **_split_name(raw)))
            return parties

        # "ESTATE OF <n>"
        m = re.search(r"\bESTATE\s+OF\s+(.+)", name, re.IGNORECASE)
        if m:
            raw = m.group(1).strip().rstrip(".,;")
            parties.append(Party(raw=raw, role="decedent", **_split_name(raw)))
            return parties

        # Divorce: "PETITIONER AND RESPONDENT"
        if signal_type == "divorce":
            m = re.search(
                r"^\s*(.+?)\s+(?:AND|vs\.?|v\.)\s+(.+?)\s*$",
                name,
                re.IGNORECASE,
            )
            if m:
                a = m.group(1).strip().rstrip(".,;")
                b = m.group(2).strip().rstrip(".,;")
                a = re.sub(r"\s+ET\s+A(NO|L)\s*$", "", a, flags=re.IGNORECASE).strip()
                parties.append(Party(raw=a, role="petitioner", **_split_name(a)))
                parties.append(Party(raw=b, role="respondent", **_split_name(b)))
                return parties

        # Fallback: keep whole case_name as one party. Canonicalizer downstream
        # will try to extract further signal.
        if 2 < len(name) < 200 and any(c.isalpha() for c in name):
            parties.append(Party(raw=name, role="party"))

        return parties


# ─── Name parser helpers ───────────────────────────────────────────────

_ROLE_SUFFIX = re.compile(r"\s+(JR|SR|II|III|IV)\.?$", re.IGNORECASE)


def _split_name(raw: str) -> dict:
    """
    Return first/last/middle/suffix hints from a raw name string.
    Accepts both "LAST, FIRST M" and "FIRST M LAST" forms.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}

    # Pull off suffix (works for both forms)
    suffix = None
    m_suffix = _ROLE_SUFFIX.search(raw)
    if m_suffix:
        suffix = m_suffix.group(1).upper().rstrip(".")
        raw = raw[: m_suffix.start()].strip()

    # "LAST, FIRST MIDDLE"
    if "," in raw:
        last, rest = raw.split(",", 1)
        tokens = rest.strip().split()
        out: dict = {}
        if tokens:
            out["first"] = tokens[0].title()
            if len(tokens) > 1:
                out["middle"] = " ".join(tokens[1:]).title()
        if last.strip():
            out["last"] = last.strip().title()
        if suffix:
            out["suffix"] = suffix
        return out

    # "FIRST MIDDLE LAST" (no comma) — last token is surname
    tokens = raw.split()
    if len(tokens) == 1:
        return {"last": tokens[0].title(), **({"suffix": suffix} if suffix else {})}
    if len(tokens) == 2:
        return {
            "first": tokens[0].title(),
            "last":  tokens[1].title(),
            **({"suffix": suffix} if suffix else {}),
        }
    return {
        "first":  tokens[0].title(),
        "middle": " ".join(tokens[1:-1]).title(),
        "last":   tokens[-1].title(),
        **({"suffix": suffix} if suffix else {}),
    }
