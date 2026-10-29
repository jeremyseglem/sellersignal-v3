"""
King County Assessor public sales file -> sales_history_v3 rows.

Why (Harvester queue #10, 2026-10-29): the matcher fix the Signal
scientist backtested (match a court filing against whoever held title
ON THE FILING DATE — claude/SIGNAL_LAB.md run 1: precision on sold homes
26% -> 54%, estate recall 10/51 -> 27/51) needs point-in-time grantor
history. sales_history_v3 is filled only by the eReal page sweep, which
holds almost none of it (0 of 60 sampled post-filing deeds). The
county's own bulk file carries the same records for every parcel.

Source (public, no login, no captcha, $0; the same files
scripts/build_kc_owners.py reads):
  https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip
      -> EXTR_RPSale.csv  (one row per parcel per recorded document)
  https://aqua.kingcounty.gov/extranet/assessor/Lookup.zip
      -> EXTR_LookUp.csv  (code tables)

Columns used (header read from the 2026-10-23 file): ExciseTaxNbr,
Major, Minor, DocumentDate (MM/DD/YYYY), SalePrice, RecordingNbr,
SellerName, BuyerName, SaleInstrument, SaleReason.

Code tables (EXTR_LookUp.csv, verified 2026-10-29): LUType 6 =
SaleInstrument (3 'Statutory Warranty Deed', 15 'Quit Claim Deed', 18
"Trustees' Deed", 24 'Deed of Personal Rep', ...), LUType 5 =
SaleReason (1 'None', 8 'Estate Settlement', 11 'Divorce Settlement',
18 'Other', ...). These descriptions are the same strings the eReal
detail page prints (checked record-by-record on pin 3211900015:
recording 20260427000596, excise 3375477, 2026-04-16, 'Quit Claim
Deed' / 'Other' in both), so the existing classifiers
(_classify_arms_length, ereal_autofill._classify_transfer) read these
rows exactly as they read eReal rows.

Normalisation mirrors the eReal parser: names/recording numbers
stripped, price 0 -> None, rows without a recording number skipped
(sales_history_v3's key is (pin, recording_number)). Pins are
Major(6) + Minor(4) — the fabric's 10-char KC pin.

Duplicates: the file can list one recording number twice on the same
parcel (pin 7229350630: '199203100000' on two 1992 excise rows). One
upsert carrying both fails the whole batch with Postgres 21000 — the
cause of queue #5. dedupe_rows() keeps one row per key, the most
complete one.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Iterable, Iterator, Optional

from backend.harvesters.ereal_property_parser import _classify_arms_length

INSTRUMENT_LUTYPE = "6"
REASON_LUTYPE = "5"


def load_lookups(lookup_csv_text: str) -> dict:
    """Parse EXTR_LookUp.csv into {'instrument': {code: text},
    'reason': {code: text}}. Codes and descriptions are stripped (the
    file pads them)."""
    out = {"instrument": {}, "reason": {}}
    for r in csv.DictReader(io.StringIO(lookup_csv_text)):
        t = (r.get("LUType") or "").strip()
        code = (r.get("LUItem") or "").strip()
        desc = (r.get("LUDescription") or "").strip()
        if t == INSTRUMENT_LUTYPE:
            out["instrument"][code] = desc
        elif t == REASON_LUTYPE:
            out["reason"][code] = desc
    return out


def pin_of(major: str, minor: str) -> str:
    major = (major or "").strip()
    minor = (minor or "").strip()
    if not (major.isdigit() and minor.isdigit()):
        return ""
    return major.zfill(6) + minor.zfill(4)


def _date(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _price(s: str) -> Optional[int]:
    s = (s or "").strip()
    try:
        v = int(float(s))
    except ValueError:
        return None
    return v if v > 0 else None


def _clean(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()
    return s or None


def parse_row(row: dict, lookups: dict, unknown: Optional[dict] = None
              ) -> Optional[dict]:
    """One EXTR_RPSale.csv row -> a sales_history_v3 row, or None when
    the row has no pin or no recording number. Unknown instrument/reason
    codes are stored as None (never guessed) and counted in `unknown`."""
    pin = pin_of(row.get("Major"), row.get("Minor"))
    rec = _clean(row.get("RecordingNbr"))
    if not pin or not rec:
        return None
    icode = (row.get("SaleInstrument") or "").strip()
    rcode = (row.get("SaleReason") or "").strip()
    instrument = lookups["instrument"].get(icode)
    reason = lookups["reason"].get(rcode)
    if unknown is not None:
        if icode and instrument is None:
            unknown[f"instrument:{icode}"] = unknown.get(f"instrument:{icode}", 0) + 1
        if rcode and reason is None:
            unknown[f"reason:{rcode}"] = unknown.get(f"reason:{rcode}", 0) + 1
    return {
        "pin":              pin,
        "recording_number": rec,
        "excise_number":    _clean(row.get("ExciseTaxNbr")),
        "sale_date":        _date(row.get("DocumentDate")),
        "sale_price":       _price(row.get("SalePrice")),
        "seller_name":      (_clean(row.get("SellerName")) or "")[:200] or None,
        "buyer_name":       (_clean(row.get("BuyerName")) or "")[:200] or None,
        "instrument":       instrument,
        "sale_reason":      reason,
        "is_arms_length":   _classify_arms_length(instrument or "", reason or ""),
    }


def _completeness(r: dict) -> tuple:
    filled = sum(1 for k in ("excise_number", "sale_date", "sale_price",
                             "seller_name", "buyer_name", "instrument",
                             "sale_reason") if r.get(k) is not None)
    return (filled, r.get("sale_price") or 0, r.get("sale_date") or "",
            r.get("excise_number") or "")


def dedupe_rows(rows: Iterable[dict]) -> tuple[list[dict], int]:
    """One row per (pin, recording_number): the most complete (most
    filled fields, then higher price, later date, higher excise number —
    deterministic). Returns (rows, n_dropped)."""
    best: dict = {}
    n = 0
    for r in rows:
        n += 1
        k = (r["pin"], r["recording_number"])
        cur = best.get(k)
        if cur is None or _completeness(r) > _completeness(cur):
            best[k] = r
    return list(best.values()), n - len(best)


def iter_sales(csv_file, lookups: dict, pins: Optional[set] = None,
               since: Optional[date] = None,
               unknown: Optional[dict] = None) -> Iterator[dict]:
    """Stream parsed rows from an open EXTR_RPSale.csv handle, keeping
    pins in `pins` (if given) and sale_date >= since (if given; rows with
    no parseable date are kept only when since is None)."""
    since_iso = since.isoformat() if since else None
    for raw in csv.DictReader(csv_file):
        if pins is not None and pin_of(raw.get("Major"), raw.get("Minor")) not in pins:
            continue
        r = parse_row(raw, lookups, unknown)
        if r is None:
            continue
        if since_iso and (r["sale_date"] is None or r["sale_date"] < since_iso):
            continue
        yield r

