#!/usr/bin/env python3
"""
California seed builder (market_key CA_SANTACLARA). Santa Clara West Valley —
Los Gatos / Monte Sereno / Saratoga. FIRST CALIFORNIA.

Proves CA is winnable: CA assessor parcel layers DO publish owner via the ASSESSEE
field (California's "gated" reputation is about the Esri-hosted directory, not the
counties' own ArcGIS orgs). This West Valley layer carries ASSESSEE (owner) +
SiteAddressFull (situs) + SITUS_ZIP_CODE (native situs ZIP) + NetAssessedValue +
LTST_TRANSFER_DT (YYYYMMDD -> real tenure, 100%) + USE_CODE/LandUseCode (prop_type)
+ MAILSTATE (absentee) + polygon geometry. Full signal.

  services3.arcgis.com/JAU7IM34hqT9y9ew/.../Parcels/FeatureServer/0

USAGE: python3 scripts/build_ca_owners.py  |  ZIPS=95030 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("CA_SCL_URL",
    "https://services3.arcgis.com/JAU7IM34hqT9y9ew/arcgis/rest/services/Parcels/FeatureServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "95030": ("Los Gatos", {"LOS GATOS", "MONTE SERENO"}),   # elite; incl Monte Sereno
}
FIELDS = ("ASSESSEE,SiteAddressFull,SITUS_ZIP_CODE,SITUS_CITY_NAME,NetAssessedValue,"
          "LTST_TRANSFER_DT,USE_CODE,LandUseCode,MAILSTATE,MAILCITY")
_R_USE = {1, 2, 3, 4, 5}       # SFR / duplex / etc.
_K_USE = {6, 7}                # condo / townhouse-ish
_R_LUC = {"LDR", "MDR", "HDR", "RES", "R"}


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
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSN", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " FOUNDATION", " SCHOOL")): return "company"
    return "individual"


def parse_dt(s):
    s = str(s or "").strip()
    if len(s) != 8 or not s.isdigit(): return None, None
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
            d = gj({"where": f"SITUS_ZIP_CODE='{z}'", "outFields": FIELDS, "returnGeometry": "true",
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
            owner = (a.get("ASSESSEE") or "").strip()
            addr = (a.get("SiteAddressFull") or "").strip()
            if not owner or not addr: continue
            pin = f"{z}-{addr}-{i}".replace(" ", "")[:60]
            ten, iso = parse_dt(a.get("LTST_TRANSFER_DT"))
            try: uc = int(a.get("USE_CODE"))
            except (ValueError, TypeError): uc = None
            luc = (a.get("LandUseCode") or "").strip().upper()
            if uc in _K_USE: pt = "K"
            elif uc in _R_USE or luc in _R_LUC: pt = "R"
            else: pt = (luc or "R")[:20]
            try: val = int(float(a.get("NetAssessedValue") or 0))
            except (ValueError, TypeError): val = 0
            ms = (a.get("MAILSTATE") or "").strip().upper()
            mc = (a.get("MAILCITY") or "").strip().upper()
            lat, lng = centroid(f.get("geometry"))
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val,
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": ms or None, "owner_city": mc or None,
                "is_out_of_state": bool(ms and ms != "CA"),
                "is_absentee": bool(ms and ms != "CA") or bool(mc and mc not in local),
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/ca-santaclara-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        tr = sum(1 for i in items.values() if i["owner_type"] in ("trust", "llc"))
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, trust/llc {tr/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
