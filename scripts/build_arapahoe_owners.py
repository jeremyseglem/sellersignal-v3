#!/usr/bin/env python3
"""
Arapahoe County CO seed builder — wave 1 (market_key CO_ARAPAHOE).

Denver-suburb ultra-lux (Cherry Hills Village, Greenwood Village). Arapahoe's
OpenDataService parcel layer is A-grade and situs-ZIP native (Zip column), so
filtered by ZIP directly — no ZCTA join (co.json holds boundaries for the map).

  services: gis.arapahoegov.com/arcgis/rest/services/OpenDataService/FeatureServer/0
  Owner, Zip (situs), Sale_Date, Price, Appr_Value, PUC (prop_type),
  Owner_City/State (absentee), Coordinate_X/Y (WGS84 inline geometry).

USAGE: python3 scripts/build_arapahoe_owners.py  |  ZIPS=80113 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("CO_ARAPAHOE_URL",
    "https://gis.arapahoegov.com/arcgis/rest/services/OpenDataService/FeatureServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "80113": ("Cherry Hills Village", {"CHERRY HILLS VILLAGE", "ENGLEWOOD"}),
    "80111": ("Greenwood Village",    {"GREENWOOD VILLAGE", "ENGLEWOOD", "CENTENNIAL"}),
    "80121": ("Greenwood Village",    {"GREENWOOD VILLAGE", "LITTLETON", "CENTENNIAL"}),
    "80122": ("Centennial",           {"CENTENNIAL", "LITTLETON"}),
    "80110": ("Cherry Hills Village", {"CHERRY HILLS VILLAGE", "ENGLEWOOD"}),
}
FIELDS = "PIN,Owner,Zip,Situs_Address,Sale_Date,Price,Appr_Value,PUC,Owner_City,Owner_State,Coordinate_X,Coordinate_Y"
_R = {"SINGLE FAMILY", "TOWNHOUSE", "DUPLEX", "TRIPLEX", "ROWHOUSE"}


def gj(params):
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for a in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))
        except Exception:
            if a == 3: raise
            time.sleep(3 * (a + 1))


def cls(name):
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " REVOCABLE", " IRREVOCABLE", " REV ", " LIVING TRUST", " FAMILY TRUST", " QPRT")): return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")): return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " DISTRICT", " CHURCH", " SCHOOL", " AUTHORITY", " HOMEOWNERS", " PARTNERSHIP", " FOUNDATION")): return "company"
    return "individual"


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config for {z}")
    now = datetime.now(timezone.utc)
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"Zip LIKE '{z}%'", "outFields": FIELDS, "returnGeometry": "false",
                    "orderByFields": "OBJECTID", "resultOffset": str(off), "resultRecordCount": str(PAGE), "f": "json"})
            if "error" in d: raise SystemExit(f"{z}: {d['error']}")
            b = d.get("features", [])
            if not b: break
            rows += b; off += len(b)
            print(f"[seed] {z} fetched {off}", flush=True)
            if len(b) < PAGE: break
        items = {}
        for f in rows:
            a = f["attributes"]
            owner = (a.get("Owner") or "").strip()
            pin = str(a.get("PIN") or "").strip()
            if not owner or not pin: continue
            sd = a.get("Sale_Date"); ten = iso = None
            if sd:
                try:
                    dt = datetime.fromtimestamp(sd / 1000, tz=timezone.utc)
                    if dt.year >= 1900: ten = round((now - dt).days / 365.25, 1); iso = dt.date().isoformat()
                except (ValueError, OSError): pass
            puc = (a.get("PUC") or "").strip().upper()
            pt = "K" if "CONDO" in puc else ("R" if any(u in puc for u in _R) else (puc or "R")[:40])
            ms = (a.get("Owner_State") or "").strip().upper(); mc = (a.get("Owner_City") or "").strip().upper()
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": (a.get("Situs_Address") or "").strip(), "value": int(a.get("Appr_Value") or 0),
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": ms or None, "owner_city": (a.get("Owner_City") or "").strip() or None,
                "is_out_of_state": bool(ms and ms != "CO"),
                "is_absentee": bool(ms and ms != "CO") or bool(mc and mc not in local),
                "legal_description": "", "lat": a.get("Coordinate_Y"), "lng": a.get("Coordinate_X")}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/co-arapahoe-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
