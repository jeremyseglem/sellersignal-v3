"""
Snohomish County SCOPI (Property Account Summary) scraper.

The Snohomish bulk Sales Excel publishes only a 5-year window. About
74% of 98290 parcels have no sale in that window — meaning their
current owners have held the property at least 5 years. For the bander
to classify those as `individual_long_tenure` (the actionable Tier-2
cohort), we need older transfer dates. SCOPI's per-parcel detail page
exposes the full Sales History going back decades.

This module hits SCOPI for a single parcel and returns the most recent
sale date + price (the same fields the bulk-Excel pipeline produces).
The autofill task in backend/tasks/snohomish_tenure_autofill.py iterates
over `parcels_v3` rows missing tenure data and calls this scraper.

Source URL pattern:
  GET  https://www.snoco.org/proptax/                       (gets session id and VIEWSTATE)
  POST https://www.snoco.org/proptax/(S(<sid>))/default.aspx (search by Parcel ID)
       — server redirects to parcelinfo.aspx with full parcel detail.

The detail page contains a `<table id="mSalesHistory">` with columns:
  Sale Date | Entry Date | Recording Number | Sale Amount |
  Excise Number | Deed Type | Transfer Type | Grantor(Seller) |
  Grantee(Buyer) | Other Parcels

We extract the most recent (last by Sale Date) row's date + amount.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


SCOPI_BASE = "https://www.snoco.org/proptax/"
USER_AGENT = "Mozilla/5.0 (compatible; SellerSignal/1.0)"


@dataclass
class ScopiResult:
    """Outcome of a single parcel scrape."""
    parcel_id: str
    success: bool                       # did the scrape complete (vs network/parse error)
    most_recent_sale: Optional[date]    # None means scrape succeeded but no sales found
    most_recent_price: Optional[int]    # in dollars
    sales_count: int                    # total rows in Sales History (0 means none)
    error: Optional[str] = None         # populated when success=False


# ── ASP.NET WebForms hidden-field extraction ─────────────────────────────
_HIDDEN_RE = re.compile(
    r'<input[^>]*\bname="(?P<name>__[A-Z]+)"[^>]*\bvalue="(?P<value>[^"]*)"',
    re.IGNORECASE,
)


def _extract_hidden_fields(html: str) -> dict[str, str]:
    """Pull __VIEWSTATE / __VIEWSTATEGENERATOR / __EVENTVALIDATION."""
    fields: dict[str, str] = {}
    for m in _HIDDEN_RE.finditer(html):
        fields[m.group("name")] = m.group("value")
    # Some pages list value before name — handle that too
    alt_re = re.compile(
        r'<input[^>]*\bvalue="(?P<value>[^"]*)"[^>]*\bname="(?P<name>__[A-Z]+)"',
        re.IGNORECASE,
    )
    for m in alt_re.finditer(html):
        fields.setdefault(m.group("name"), m.group("value"))
    return fields


# ── Sales History table parser ───────────────────────────────────────────
_TABLE_RE = re.compile(
    r'<table[^>]*\bid="mSalesHistory"[^>]*>(?P<body>.*?)</table>',
    re.DOTALL | re.IGNORECASE,
)
_ROW_RE = re.compile(r'<tr[^>]*>(?P<body>.*?)</tr>', re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r'<t[hd][^>]*>(?P<body>.*?)</t[hd]>', re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')


def _parse_sales_history(html: str) -> tuple[Optional[date], Optional[int], int]:
    """
    Parse the Sales History table. Returns (most_recent_date,
    most_recent_price_dollars, total_row_count). All None / 0 if no
    table or no data rows.
    """
    m = _TABLE_RE.search(html)
    if not m:
        return None, None, 0

    rows = _ROW_RE.findall(m.group("body"))
    data_rows: list[list[str]] = []
    for row_html in rows:
        cells = _CELL_RE.findall(row_html)
        cleaned = [_TAG_RE.sub("", c).strip() for c in cells]
        # Skip the header row (first cell == "Sale Date")
        if cleaned and cleaned[0].lower() == "sale date":
            continue
        # Need at least date + price columns
        if len(cleaned) < 4:
            continue
        data_rows.append(cleaned)

    if not data_rows:
        return None, None, 0

    # Find the row with the most recent (max) sale date
    best_date: Optional[date] = None
    best_price: Optional[int] = None
    for row in data_rows:
        sale_date_str = row[0].strip()
        if not sale_date_str:
            continue
        try:
            d = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
        except ValueError:
            continue
        if best_date is None or d > best_date:
            best_date = d
            # Price like "$844,999.00" — strip $/, and trailing .00
            raw_price = row[3].strip().replace("$", "").replace(",", "")
            try:
                best_price = int(float(raw_price))
            except ValueError:
                best_price = None

    return best_date, best_price, len(data_rows)


# ── Public entry point ───────────────────────────────────────────────────
def fetch_parcel_sales(
    client: "httpx.Client",
    parcel_id: str,
) -> ScopiResult:
    """
    Hit SCOPI for one parcel and return its most-recent sale.

    `client` should be an httpx.Client with cookies enabled and a
    sensible timeout (e.g. 20s). The caller can reuse a single client
    across many parcels; sessions are isolated per call by re-fetching
    the form (so a stale VIEWSTATE never poisons subsequent searches).

    Returns a ScopiResult — never raises for HTTP/parse errors. Network
    or parser failures populate `error` and set `success=False` so the
    autofill loop can decide whether to retry.
    """
    if httpx is None:
        return ScopiResult(parcel_id, False, None, None, 0,
                           error="httpx not installed")

    parcel_id = (parcel_id or "").strip()
    if not parcel_id:
        return ScopiResult(parcel_id, False, None, None, 0,
                           error="empty parcel_id")

    try:
        # Step 1: GET the form to grab session URL + VIEWSTATE
        resp = client.get(SCOPI_BASE)
        if resp.status_code != 200:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error=f"form GET status {resp.status_code}")
        form_url = str(resp.url)  # has the (S(...)) prefix
        hidden = _extract_hidden_fields(resp.text)
        if "__VIEWSTATE" not in hidden:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error="VIEWSTATE not found on form page")

        # Step 2: POST search. Form fields gleaned from default.aspx.
        form = {
            "__EVENTTARGET":         "",
            "__EVENTARGUMENT":       "",
            "__VIEWSTATE":           hidden.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR":  hidden.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION":     hidden.get("__EVENTVALIDATION", ""),
            "mParcelID":             parcel_id,
            "mStreetAddress":        "",
            "mCity":                 "",
            "mStateProvince":        "WA",
            "mPostalCode":           "",
            "mSubmit":               "Submit",
        }
        resp = client.post(form_url, data=form,
                           headers={"Referer": form_url})
        if resp.status_code != 200:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error=f"search POST status {resp.status_code}")
        html = resp.text

        # If we landed back on the search form (no result), the page
        # will not have an mSalesHistory table.
        sale_date, sale_price, count = _parse_sales_history(html)
        return ScopiResult(
            parcel_id=parcel_id,
            success=True,
            most_recent_sale=sale_date,
            most_recent_price=sale_price,
            sales_count=count,
        )

    except (httpx.HTTPError, ValueError) as e:
        return ScopiResult(parcel_id, False, None, None, 0,
                           error=f"{type(e).__name__}: {str(e)[:100]}")


def make_client(timeout_seconds: float = 20.0) -> "httpx.Client":
    """Build an httpx.Client tuned for SCOPI politeness."""
    if httpx is None:
        raise ImportError("httpx is required. pip install httpx")
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_seconds,
        follow_redirects=True,
    )
