#!/usr/bin/env python3
"""
Denver (City & County) CO seed builder — wave 1 (market_key CO_DENVER).

Pulls Denver's authoritative open-data parcel layer (refreshed daily —
verified dataLastEditDate = same-day at recon):
  services1.arcgis.com/zdB7qR0BtYrg0Xpl/.../ODC_PROP_PARCELS_A/FeatureServer/245

Situs-ZIP native (SITUS_ZIP, stored as ZIP+4 — filtered with LIKE 'zip%'),
so no ZCTA join; data/zip_polygons/co.json holds boundaries for the map only.

Fields:
  - pin           = SCHEDNUM (Denver schedule number)
  - owner_name    = OWNER_NAME
  - value         = APPRAISED_TOTAL_VALUE
  - tenure_years  = years since SALE_DATE (epoch ms)
  - prop_type     = D_CLASS_CN contains 'CONDO' -> 'K'; startswith
                    'RESIDENTIAL' -> 'R'; else raw truncated (matcher
                    market-aware default covers CO_*)
  - is_absentee   = OWNER_STATE != 'CO' or owner mail city outside local set
  - lat/lng       = parcel centroid (returnCentroid, outSR=4326)

USAGE:
  python3 scripts/build_denver_owners.py
  ZIPS=80206 python3 scripts/build_denver_owners.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "CO_DENVER_PARCELS_URL",
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_PROP_PARCELS_A/FeatureServer/245",
)
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

ZIP_CONFIG = {
    "80206": ("Denver", {"DENVER"}),   # Cherry Creek / Country Club / Congress Park
    "80209": ("Denver", {"DENVER"}),   # Wash Park / Belcaro / Bonnie Brae
    "80210": ("Denver", {"DENVER"}),   # Observatory Park / DU / Cory-Merrill
    "80220": ("Denver", {"DENVER"}),   # Hilltop / Montclair / Crestmoor
    "80211": ("Denver", {"DENVER"}),   # Highlands / LoHi / Berkeley
}

FIELDS = ("SCHEDNUM,OWNER_NAME,OWNER_CITY,OWNER_STATE,SITUS_ADDRESS_LINE1,"
          "SITUS_ZIP,SALE_DATE,SALE_PRICE,APPRAISED_TOTAL_VALUE,D_CLASS_CN,"
          "LAND_AREA")


def gj(params: dict) -> dict:
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=120))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def classify_owner_type(name: str) -> str:
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE", " REV ",
                            " LIVING TRUST", " FAMILY TRUST", " QPRT")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " CITY AND COUNTY", " COUNTY",
                            " STATE OF", " UNITED STATES", " SCHOOL",
                            " DISTRICT", " PARTNERSHIP", " HOMEOWNERS",
                            " CONDOMINIUM", " FOUNDATION", " UNIVERSITY",
                            " AUTHORITY", " HOUSING")):
        return "company"
    return "individual"


def fetch_zip(zip_code: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        d = gj({"where": f"SITUS_ZIP LIKE '{zip_code}%'", "outFields": FIELDS,
                "returnGeometry": "false", "returnCentroid": "true",
                "outSR": "4326", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"{zip_code}: FeatureServer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] {zip_code} fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break
    return rows


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] \
        or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG:
            raise SystemExit(f"ZIP {z} has no ZIP_CONFIG entry.")
    now = datetime.now(timezone.utc)
    for z in target:
        city, local_cities = ZIP_CONFIG[z]
        rows = fetch_zip(z)
        items: dict[str, dict] = {}
        no_owner = 0
        for f in rows:
            a = f.get("attributes") or {}
            c = f.get("centroid") or {}
            owner = (a.get("OWNER_NAME") or "").strip()
            if not owner:
                no_owner += 1
                continue
            pin = str(a.get("SCHEDNUM") or "").strip()
            if not pin:
                continue
            sale_ms = a.get("SALE_DATE")
            tenure = sale_iso = None
            if sale_ms:
                try:
                    dt = datetime.fromtimestamp(sale_ms / 1000, tz=timezone.utc)
                    if dt.year >= 1900:
                        tenure = round((now - dt).days / 365.25, 1)
                        sale_iso = dt.date().isoformat()
                except (ValueError, OSError):
                    pass
            dc = (a.get("D_CLASS_CN") or "").strip().upper()
            if "CONDO" in dc:
                prop_type = "K"
            elif (dc.startswith("RESIDENTIAL") or dc.startswith("SFR")
                  or "ROWHOUSE" in dc or "TOWNHOME" in dc or "TOWNHOUSE" in dc
                  or "DUPLEX" in dc or "TRIPLEX" in dc):
                prop_type = "R"
            else:
                prop_type = (dc or "R")[:40]
            mail_city = (a.get("OWNER_CITY") or "").strip().upper()
            mail_state = (a.get("OWNER_STATE") or "").strip().upper()
            items[pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": (a.get("SITUS_ADDRESS_LINE1") or "").strip(),
                "value": int(a.get("APPRAISED_TOTAL_VALUE") or 0),
                "tenure_years": tenure,
                "last_transfer_date": sale_iso,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("OWNER_CITY") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "CO"),
                "is_absentee": bool(mail_state and mail_state != "CO")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": "",
                "lat": c.get("y"), "lng": c.get("x"),
            }
        path = f"data/seeds/co-denver-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        ten = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels (no_owner {no_owner}), "
              f"addr {cov:.0f}%, tenure {ten/max(len(items),1)*100:.0f}%, "
              f"R/K {rk/max(len(items),1)*100:.0f}% -> {path}", flush=True)


if __name__ == "__main__":
    main()
