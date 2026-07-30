#!/usr/bin/env python3
"""
Denver (City & County) CO probate/TOD signal harvester — REST, no browser.

Replaces the abandoned publicsearch.us recorder approach (that Denver tenant
delivers results over a websocket gated to datacenter IPs — unharvestable from
our infra). Instead uses Denver's OWN authoritative open-data transfers layer,
which exposes the exact death->title instruments as plain ArcGIS REST — same
infrastructure the Denver seed builder already uses, so it is fully testable
locally and needs NO Playwright / GitHub Action.

  Layer: ODC_real_property_sales_and_transfers/FeatureServer/60
  Fields: INSTRUMENT, GRANTOR, GRANTEE, RECEPTION_NUM, RECEPTION_DATE,
          SALE_YEAR, SALE_MONTHDAY, PARID, D_CLASS_N

Death/estate instruments harvested (confirmed against live data 2026-07-30):
  PR  Personal Representative's Deed  -> probate           (est. 2,033 total,
                                                             433 since 2025)
  BF  Beneficiary Deed (CO's TOD)     -> transfer_on_death  (est. 192)
(Other codes — WD/SW/QC ordinary deeds, DC ambiguous — are excluded; PR and BF
are the unambiguous death-driven transfers.)

RECEPTION_DATE is epoch-0/null in this layer; the real date is SALE_YEAR +
SALE_MONTHDAY (MMDD) -> we synthesize event_date from those.

Output: raw_signals_v3 rows via dallas_recorder.to_signal_row (reused — same
proven shape), source_type=co_denver_transfers, jurisdiction=CO_DENVER. The
grantor/grantee names are resolved downstream by the existing rematch matcher
against the loaded Denver parcels_v3 owners (name match — the standard path;
PARID uses a different key format than parcel SCHEDNUM so is kept in raw_data
for reference only, not relied on for the join).

USAGE (dry run — prints sample signals, writes nothing):
  python3 scripts/run_denver_transfers.py
Write to DB (needs SUPABASE_URL + SUPABASE_SERVICE_KEY):
  WRITE=1 python3 scripts/run_denver_transfers.py
  SINCE_YEAR=2024 WRITE=1 python3 scripts/run_denver_transfers.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import dallas_recorder as dr  # noqa: E402

dr.SOURCE_TYPE = "co_denver_transfers"

LAYER = os.environ.get(
    "CO_DENVER_TRANSFERS_URL",
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_real_property_sales_and_transfers/FeatureServer/60",
)
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Harvest/1.0"}
PAGE = 2000

# Denver instrument code -> the doc-type STRING dallas_recorder.classify_doc_type
# will recognize. We hand to_signal_row a doc_type it already classifies, so no
# new classifier logic is needed.
INSTRUMENT_DOCTYPE = {
    "PR": "PERSONAL REPRESENTATIVE DEED",   # -> probate
    "BF": "BENEFICIARY DEED",               # -> transfer_on_death
}
# ensure BENEFICIARY DEED is a recognized needle (CO TOD)
if not any(n[0] == "BENEFICIARY DEED" for n in dr.DEATH_DOCTYPE_SIGNALS):
    dr.DEATH_DOCTYPE_SIGNALS.append(("BENEFICIARY DEED", "transfer_on_death"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
SINCE_YEAR = int(os.environ.get("SINCE_YEAR", str(date.today().year - 1)))
TABLE = "raw_signals_v3"
SOURCE = "co_denver_transfers"


def gj(params: dict) -> dict:
    url = f"{LAYER}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=120))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def _event_date(a: dict) -> str | None:
    yr = a.get("SALE_YEAR")
    md = a.get("SALE_MONTHDAY")
    if not yr:
        return None
    md = str(md or "").zfill(4)
    try:
        mm, dd = int(md[:2]), int(md[2:])
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            mm = mm if 1 <= mm <= 12 else 1
            dd = dd if 1 <= dd <= 31 else 1
        return date(int(yr), mm, dd).isoformat()
    except (ValueError, TypeError):
        try:
            return date(int(yr), 1, 1).isoformat()
        except Exception:
            return None


def fetch_instruments() -> list[dict]:
    codes = "','".join(INSTRUMENT_DOCTYPE)
    where = f"INSTRUMENT IN ('{codes}') AND SALE_YEAR >= {SINCE_YEAR}"
    rows, offset = [], 0
    while True:
        d = gj({"where": where,
                "outFields": "INSTRUMENT,GRANTOR,GRANTEE,RECEPTION_NUM,"
                             "SALE_YEAR,SALE_MONTHDAY,PARID,D_CLASS_N",
                "returnGeometry": "false", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"transfers layer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        if len(feats) < PAGE:
            break
    return rows


def to_row(a: dict) -> dict:
    """Shape a transfers feature into the dict dallas_recorder.to_signal_row reads."""
    return {
        "grantor": (a.get("GRANTOR") or "").strip(),
        "grantee": (a.get("GRANTEE") or "").strip(),
        "doc_type": INSTRUMENT_DOCTYPE.get((a.get("INSTRUMENT") or "").strip(), ""),
        "recorded_date": _event_date(a),
        "doc_number": str(a.get("RECEPTION_NUM") or "").strip() or None,
        "legal_description": (a.get("D_CLASS_N") or "").strip(),
        "town": "Denver",
        "book_vol_page": str(a.get("PARID") or ""),
    }


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    r = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?source_type=eq.{SOURCE}&select=document_ref",
        headers=_headers())
    return {row["document_ref"] for row in json.load(urllib.request.urlopen(r, timeout=90))}


def write_rows(rows: list) -> int:
    if not rows:
        return 0
    body = json.dumps(rows).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?on_conflict=source_type,document_ref",
        data=body, method="POST",
        headers={**_headers(),
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    urllib.request.urlopen(req, timeout=180)
    return len(rows)


def main():
    print(f"[denver_transfers] instruments={list(INSTRUMENT_DOCTYPE)} "
          f"since_year={SINCE_YEAR} write={WRITE}")
    feats = fetch_instruments()
    print(f"[denver_transfers] fetched {len(feats):,} raw transfer rows")
    sigs, by_type = [], {}
    for f in feats:
        sig = dr.to_signal_row(to_row(f["attributes"]))
        if not sig:
            continue
        sig["jurisdiction"] = "CO_DENVER"
        sig["raw_data"]["harvester"] = "denver_transfers"
        sigs.append(sig)
        by_type[sig["signal_type"]] = by_type.get(sig["signal_type"], 0) + 1
    print(f"[denver_transfers] {len(sigs):,} signals ({by_type})")

    if not WRITE:
        print("[denver_transfers] DRY RUN — sample signals:")
        for s in sigs[:8]:
            print("  ", json.dumps({k: s.get(k) for k in
                  ("signal_type", "document_ref", "event_date", "party_names",
                   "property_hint")}, default=str)[:240])
        return

    if not (SUPABASE_URL and SERVICE_KEY):
        print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
        sys.exit(1)
    seen = existing_refs()
    fresh = [s for s in sigs if s["document_ref"] and s["document_ref"] not in seen]
    wrote = 0
    for i in range(0, len(fresh), 500):
        wrote += write_rows(fresh[i:i + 500])
    print(f"[denver_transfers] wrote {wrote:,} new signals "
          f"({len(sigs) - len(fresh)} already in db)")


if __name__ == "__main__":
    main()
