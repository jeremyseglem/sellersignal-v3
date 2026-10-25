"""
Snohomish County Aumentum (publicaccessnow) per-parcel transfer-history
fetcher — the replacement for the dead SCOPI scraper.

Why this exists (2026-10-25, Harvester engineer repair #1):
  https://www.snoco.org/proptax/ now answers 302 → the county's Assessor
  landing page (snohomishcountywa.gov/5167/Assessor); the per-parcel app
  moved to Aumentum at https://wa-snohomish.publicaccessnow.com. Every
  SCOPI fetch therefore failed ("VIEWSTATE not found on form page") and
  the tenure autofill task sat at a 100% error rate (ZIP Warden
  2026-10-23 → 10-25; 741 parcels pending).

What the live portal actually does (probed from the container with
Chromium on 2026-10-25 — every URL, header and field below was read off
the network log, none is from memory):

  Property Account Summary page
    GET /PropertyInformation/PropertySearch/PropertyAccountSummary.aspx?p=<pin>&a=<altkey>&m=<pin>
  loads its "Transfer History" panel from a DNN DataDisplay module:
    GET /API/DataDisplay/DataSources/GetData
        ?p=<pin>&a=<altkey>&m=<pin>&itemsPerPage=11&page=1&_m=474
    request headers:  tabid: 39   moduleid: 474
    (without the two headers the API answers 401
     "Authorization has been denied for this request"; with them it
     answers with or without cookies, and with `a` omitted)
  JSON shape:
    {"headers": [...],
     "groups": [{"rows": [{"values": [{"column": "SaleDate",
                                       "value": "1/2/2013 12:00:00 AM"},
                                      {"column": "AdjustedSalesPrice",
                                       "value": "730000.00"},
                                      {"column": "DocNumber", ...},
                                      {"column": "ConveyanceForm", ...},
                                      {"column": "Grantor", ...},
                                      {"column": "Grantee", ...},
                                      {"column": "DocSubType",
                                       "value": "Statutory Warranty Deed"}]},
                          ...]}],
     "totalItems": 3, "grandTotals": []}
  Column list from GetViewSettings?_m=474: SaleDate ("Sale Date"),
  AdjustedSalesPrice ("Sale Price"), DocNumber ("Document No."),
  ConveyanceForm ("Excise Number"), Grantor, Grantee, DocSubType
  ("Deed Type"). Observed DocSubType values: Statutory Warranty Deed,
  Quit Claim Deed, Personal Representative Deed, Other. $0 rows exist
  (DocSubType "Other"/"Quit Claim Deed").
  An unknown pin returns totalItems 0 with one empty group (HTTP 200).

  Pin → Altkey (only needed if the server ever starts requiring `a`):
    POST /DesktopModules/QuickSearch/API/Module/GetData?_m=470
         headers: tabid: 38  moduleid: 470  content-type: application/json
         body:    {"keywords": "<pin>", "page": 1}
    → {"items": [{"fields": {"Altkey": 307866, "ParcelID": "...", ...}}],
       "total": 1}

This module returns the most recent transfer's date + price (the same
fields the bulk-Excel pipeline produces) so backend/tasks/
snohomish_tenure_autofill.py can keep writing last_transfer_date /
tenure_years / last_transfer_price exactly as before.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


AUMENTUM_BASE = "https://wa-snohomish.publicaccessnow.com"
USER_AGENT = "Mozilla/5.0 (compatible; SellerSignal/1.0)"

# Transfer History DataDisplay module on PropertyAccountSummary.aspx
TRANSFER_HISTORY_URL = f"{AUMENTUM_BASE}/API/DataDisplay/DataSources/GetData"
TRANSFER_HISTORY_MODULE_ID = "474"
TRANSFER_HISTORY_TAB_ID = "39"
# The portal pages 11 rows at a time; we ask for more so one call covers
# a parcel's whole history (the longest observed in the probe was 4 rows).
TRANSFER_HISTORY_PAGE_SIZE = 100

# QuickSearch module on PropertySearch.aspx (pin → Altkey fallback)
QUICKSEARCH_URL = f"{AUMENTUM_BASE}/DesktopModules/QuickSearch/API/Module/GetData"
QUICKSEARCH_MODULE_ID = "470"
QUICKSEARCH_TAB_ID = "38"

# Canary: a 98290 parcel with a stable, multi-row transfer history
# (3 rows, 2005/2012/2013, observed 2026-10-25). If this returns no rows
# the portal has changed again — the task must fail loudly, not stamp
# every pending parcel as "no sales".
CANARY_PIN = "00370500000200"
CANARY_MIN_ROWS = 1


@dataclass
class ScopiResult:
    """Outcome of a single parcel fetch (name kept for the task's sake)."""
    parcel_id: str
    success: bool                       # did the fetch complete (vs network/parse error)
    most_recent_sale: Optional[date]    # None means fetch succeeded but no transfers found
    most_recent_price: Optional[int]    # in dollars
    sales_count: int                    # total transfer rows (0 means none)
    error: Optional[str] = None         # populated when success=False


TenureResult = ScopiResult


# ── Parsing ──────────────────────────────────────────────────────────────
_DATE_FORMATS = ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _parse_sale_date(raw: Any) -> Optional[date]:
    s = str(raw or "").strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_price(raw: Any) -> Optional[int]:
    s = str(raw or "").strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _rows(payload: dict) -> list[dict[str, Any]]:
    """Flatten the DataDisplay payload into [{column: value}, ...]."""
    out: list[dict[str, Any]] = []
    for group in payload.get("groups") or []:
        for row in (group or {}).get("rows") or []:
            cells = {}
            for v in (row or {}).get("values") or []:
                col = v.get("column")
                if col:
                    cells[col] = v.get("value")
            if cells:
                out.append(cells)
    return out


def parse_transfer_history(payload: dict) -> tuple[Optional[date], Optional[int], int]:
    """
    Reduce a Transfer History payload to (most_recent_date,
    most_recent_price_dollars, total_row_count). Mirrors the old SCOPI
    parser: the row with the max SaleDate wins; its price is returned
    as-is (0 for $0 conveyances — the task only stores prices > 0).
    """
    rows = _rows(payload)
    best_date: Optional[date] = None
    best_price: Optional[int] = None
    for row in rows:
        d = _parse_sale_date(row.get("SaleDate"))
        if d is None:
            continue
        if best_date is None or d > best_date:
            best_date = d
            best_price = _parse_price(row.get("AdjustedSalesPrice"))
    return best_date, best_price, len(rows)


# ── HTTP ─────────────────────────────────────────────────────────────────
def _transfer_history(client: "httpx.Client", parcel_id: str,
                      altkey: Optional[int] = None) -> "httpx.Response":
    params: dict[str, Any] = {
        "p": parcel_id,
        "m": parcel_id,
        "itemsPerPage": TRANSFER_HISTORY_PAGE_SIZE,
        "page": 1,
        "_m": TRANSFER_HISTORY_MODULE_ID,
    }
    if altkey is not None:
        params["a"] = altkey
    return client.get(
        TRANSFER_HISTORY_URL, params=params,
        headers={
            "tabid": TRANSFER_HISTORY_TAB_ID,
            "moduleid": TRANSFER_HISTORY_MODULE_ID,
            "Accept": "application/json, text/plain, */*",
            "Referer": (f"{AUMENTUM_BASE}/PropertyInformation/PropertySearch/"
                        f"PropertyAccountSummary.aspx?p={parcel_id}&m={parcel_id}"),
        },
    )


def lookup_altkey(client: "httpx.Client", parcel_id: str) -> Optional[int]:
    """Pin → Aumentum Altkey via the QuickSearch module. None if not found."""
    resp = client.post(
        QUICKSEARCH_URL, params={"_m": QUICKSEARCH_MODULE_ID},
        json={"keywords": parcel_id, "page": 1},
        headers={
            "tabid": QUICKSEARCH_TAB_ID,
            "moduleid": QUICKSEARCH_MODULE_ID,
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{AUMENTUM_BASE}/PropertyInformation/PropertySearch.aspx",
        },
    )
    if resp.status_code != 200:
        return None
    for item in (resp.json() or {}).get("items") or []:
        fields = item.get("fields") or {}
        if str(fields.get("ParcelID") or "") == parcel_id and fields.get("Altkey") is not None:
            try:
                return int(fields["Altkey"])
            except (TypeError, ValueError):
                return None
    return None


def fetch_parcel_sales(client: "httpx.Client", parcel_id: str) -> ScopiResult:
    """
    Fetch one parcel's Transfer History from Aumentum and return its
    most-recent transfer. Never raises for HTTP/parse errors — failures
    populate `error` and set `success=False` so the autofill loop can
    retry the parcel on a later tick.
    """
    if httpx is None:
        return ScopiResult(parcel_id, False, None, None, 0, error="httpx not installed")

    parcel_id = (parcel_id or "").strip()
    if not parcel_id:
        return ScopiResult(parcel_id, False, None, None, 0, error="empty parcel_id")

    try:
        resp = _transfer_history(client, parcel_id)
        if resp.status_code in (401, 403):
            # Observed working without `a`; if the server ever insists on
            # the Altkey, resolve it through QuickSearch and retry once.
            altkey = lookup_altkey(client, parcel_id)
            if altkey is None:
                return ScopiResult(parcel_id, False, None, None, 0,
                                   error=f"transfer-history status {resp.status_code}; "
                                         f"altkey lookup failed")
            resp = _transfer_history(client, parcel_id, altkey=altkey)
        if resp.status_code != 200:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error=f"transfer-history status {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error="transfer-history: non-JSON response")
        if not isinstance(payload, dict) or "groups" not in payload:
            return ScopiResult(parcel_id, False, None, None, 0,
                               error="transfer-history: unexpected JSON shape "
                                     f"(keys={sorted(payload)[:6] if isinstance(payload, dict) else type(payload).__name__})")

        sale_date, sale_price, count = parse_transfer_history(payload)
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


def verify_portal(client: "httpx.Client") -> Optional[str]:
    """
    Canary check: fetch CANARY_PIN and confirm the portal still returns
    its transfer rows. Returns None when healthy, else a short reason.
    The task runs this before each batch so a portal change surfaces as
    an error (visible in /snohomish-tenure-autofill-status) instead of
    silently stamping every parcel as "no sales".
    """
    res = fetch_parcel_sales(client, CANARY_PIN)
    if not res.success:
        return f"canary {CANARY_PIN} failed: {res.error}"
    if res.sales_count < CANARY_MIN_ROWS or res.most_recent_sale is None:
        return (f"canary {CANARY_PIN} returned {res.sales_count} transfer rows "
                f"(expected >= {CANARY_MIN_ROWS}) — portal changed?")
    return None


def make_client(timeout_seconds: float = 20.0) -> "httpx.Client":
    """Build an httpx.Client tuned for the Aumentum API."""
    if httpx is None:
        raise ImportError("httpx is required. pip install httpx")
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_seconds,
        follow_redirects=True,
    )
