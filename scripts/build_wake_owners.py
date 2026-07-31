#!/usr/bin/env python3
"""
Wake County NC seed builder — wave 1 (market_key NC_WAKE). First North Carolina.

Raleigh luxury (Five Points/Hayes Barton, North Hills). Wake's Property/Parcels
MapServer is situs-ZIP native (ZIPNUM) so filtered by ZIP directly. No
returnCentroid support on this MapServer, so lat/lng is computed from the
polygon exterior-ring centroid per parcel (approximate — fine for a map pin;
SITE_ADDRESS is the real locator).

  maps.wakegov.com/arcgis/rest/services/Property/Parcels/MapServer/0
  OWNER, SITE_ADDRESS, ZIPNUM, DEED_DATE (tenure), TOTAL_VALUE_ASSD,
  TYPE_USE_DECODE (prop_type), ADDR1-3 (owner mailing / absentee).

USAGE: python3 scripts/build_wake_owners.py  |  ZIPS=27608 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("NC_WAKE_URL",
    "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/MapServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "27608": ("Raleigh", {"RALEIGH"}),   # Five Points / Hayes Barton
    "27609": ("Raleigh", {"RALEIGH"}),   # North Hills
    "27612": ("Raleigh", {"RALEIGH"}),
    "27613": ("Raleigh", {"RALEIGH"}),
    "27607": ("Raleigh", {"RALEIGH"}),
}
FIELDS = "OWNER,ADDR1,ADDR2,ADDR3,SITE_ADDRESS,ZIPNUM,DEED_DATE,TOTAL_VALUE_ASSD,TYPE_USE_DECODE"
_R = {"SINGLFAM", "TWOFAM", "TOWNHOUSE", "TWNHOUSE", "DUPLEX", "SINGLE FAMILY"}


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
    return sum(ys) / len(ys), sum(xs) / len(xs)  # lat, lng


def cls(name):
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " REVOCABLE", " IRREVOCABLE", " REV ", " LIVING TRUST", " FAMILY TRUST")): return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")): return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " UNIVERSITY", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " FOUNDATION")): return "company"
    return "individual"


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config {z}")
    now = datetime.now(timezone.utc)
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"ZIPNUM='{z}'", "outFields": FIELDS, "returnGeometry": "true",
                    "outSR": "4326", "orderByFields": "OBJECTID", "resultOffset": str(off),
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
            owner = (a.get("OWNER") or "").strip()
            if not owner: continue
            pin = f"{z}-{a.get('SITE_ADDRESS','')}-{i}".replace(" ", "")[:60]
            # prefer a stable id: use ADDR/site; fall back to index
            dd = a.get("DEED_DATE"); ten = iso = None
            if dd:
                try:
                    dt = datetime.fromtimestamp(dd / 1000, tz=timezone.utc)
                    if dt.year >= 1900: ten = round((now - dt).days / 365.25, 1); iso = dt.date().isoformat()
                except (ValueError, OSError): pass
            use = (a.get("TYPE_USE_DECODE") or "").strip().upper()
            pt = "K" if "CONDO" in use else ("R" if any(u in use for u in _R) else (use or "R")[:40])
            mail = " ".join(str(a.get(k) or "").strip() for k in ("ADDR2", "ADDR3")).upper()
            oos = " NC " not in f" {mail} " and mail.strip() != "" and not mail.rstrip().endswith(" NC")
            lat, lng = centroid(f.get("geometry"))
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": (a.get("SITE_ADDRESS") or "").strip(), "value": int(a.get("TOTAL_VALUE_ASSD") or 0),
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": None, "owner_city": None,
                "is_out_of_state": False,
                "is_absentee": bool(mail and "RALEIGH" not in mail and mail.strip() != ""),
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/nc-wake-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
