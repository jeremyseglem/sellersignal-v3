#!/usr/bin/env python3
"""
Buncombe County NC seed builder (market_key NC_BUNCOMBE). Asheville.

Buncombe's open-data parcel MapServer is situs-ZIP native (Zipcode) and carries
Owner, Address (situs), DeedDate (YYYYMMDD string -> tenure), AppraisedValue,
Class/LandUse (prop_type). Polygon layer with no returnCentroid, so lat/lng is
the exterior-ring centroid per parcel (fine for a map pin; Address is the locator).

  gis.buncombecounty.org/arcgis/rest/services/opendata/MapServer/1
  Verified 100% addr/sale/value on all Asheville trophy ZIPs.

USAGE: python3 scripts/build_buncombe_owners.py  |  ZIPS=28803 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("NC_BUNCOMBE_URL",
    "https://gis.buncombecounty.org/arcgis/rest/services/opendata/MapServer/1")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "28801": ("Asheville", {"ASHEVILLE"}),   # downtown / Montford
    "28803": ("Asheville", {"ASHEVILLE", "BILTMORE FOREST"}),  # Biltmore Forest/Village — trophy
    "28804": ("Asheville", {"ASHEVILLE"}),   # north / Grove Park / Kimberly
    "28805": ("Asheville", {"ASHEVILLE"}),   # east / Haw Creek
    "28806": ("Asheville", {"ASHEVILLE"}),   # west
}
FIELDS = "Owner,CareOf,Address,CityName,State,Zipcode,DeedDate,AppraisedValue,TotalMarketValue,Class,LandUse"
_R = {"SINGLE FAMILY", "SINGLFAM", "TOWNHOUSE", "TWO FAMILY", "DUPLEX", "RESIDENTIAL"}


def gj(params):
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for a in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))
        except Exception:
            if a == 3: raise
            time.sleep(3 * (a + 1))


def centroid(geom):
    if not geom or "rings" not in geom or not geom["rings"]:
        return None, None
    ring = geom["rings"][0]
    if not ring: return None, None
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return sum(ys) / len(ys), sum(xs) / len(xs)


def cls(name):
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " REVOCABLE", " IRREVOCABLE", " REV ", " LIVING TRUST", " FAMILY TRUST")): return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")): return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " UNIVERSITY", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " FOUNDATION")): return "company"
    return "individual"


def parse_deed(dd):
    """DeedDate is 'YYYYMMDD' string."""
    s = str(dd or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None, None
    try:
        dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=timezone.utc)
        if dt.year < 1900: return None, None
        return round((datetime.now(timezone.utc) - dt).days / 365.25, 1), dt.date().isoformat()
    except (ValueError, OSError):
        return None, None


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config {z}")
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"Zipcode='{z}'", "outFields": FIELDS, "returnGeometry": "true",
                    "outSR": "4326", "orderByFields": "objectid", "resultOffset": str(off),
                    "resultRecordCount": str(PAGE), "geometryPrecision": "6", "f": "json"})
            if "error" in d: raise SystemExit(f"{z}: {d['error']}")
            b = d.get("features", [])
            if not b: break
            rows += b; off += len(b)
            print(f"[seed] {z} fetched {off}", flush=True)
            if len(b) < PAGE: break
        items = {}
        for i, f in enumerate(rows):
            a = f["attributes"]
            owner = (a.get("Owner") or "").strip()
            if not owner: continue
            addr = (a.get("Address") or "").strip()
            pin = f"{z}-{addr}-{i}".replace(" ", "")[:60]
            ten, iso = parse_deed(a.get("DeedDate"))
            use = (a.get("LandUse") or a.get("Class") or "").strip().upper()
            cl = (a.get("Class") or "").strip()
            # Buncombe Class is a numeric use code: 1xx = residential, 3xx = commercial.
            if cl[:1] == "1":
                pt = "K" if cl in ("104", "105", "106") else "R"  # 10x = condo/townhome-ish
            elif "CONDO" in use:
                pt = "K"
            else:
                pt = (cl or "R")[:40]
            ost = (a.get("State") or "").strip().upper()
            oct = (a.get("CityName") or "").strip().upper()
            lat, lng = centroid(f.get("geometry"))
            try: val = int(float(a.get("AppraisedValue") or a.get("TotalMarketValue") or 0))
            except (ValueError, TypeError): val = 0
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val,
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": ost or None, "owner_city": oct or None,
                "is_out_of_state": bool(ost and ost != "NC"),
                "is_absentee": bool(ost and ost != "NC") or bool(oct and oct not in local),
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/nc-buncombe-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
