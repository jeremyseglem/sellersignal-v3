#!/usr/bin/env python3
"""
Indian River County FL seed builder (market_key FL_INDIAN_RIVER). Vero Beach
barrier island — John's Island / Windsor / Orchid / Riomar.

Built from the Indian River County Property Appraiser (IRCPA) ArcGIS layer DIRECTLY
— owner + geometry in ONE layer, bypassing the FL DOR NAL portal entirely (which was
intermittently blocking downloads). Full signal: OWNER_NAME + SITE_ADDR (situs) +
AD_ZIP (situs ZIP) + CAMA_VALUE + SALE_YEAR/SALE_MONTH (tenure) + PROPUSE_CD/DOR_DESC
(prop_type) + polygon geometry (exterior-ring centroid).

  gisportal.ircgov.com/server3/rest/services/IRCPA/Parcels_MS/MapServer/0

USAGE: python3 scripts/build_ircpa_owners.py  |  ZIPS=32963 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("IRCPA_URL",
    "https://gisportal.ircgov.com/server3/rest/services/IRCPA/Parcels_MS/MapServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "32963": ("Vero Beach", {"VERO BEACH"}),   # barrier island: John's Island / Windsor / Orchid
}
FIELDS = ("OWNER_NAME,SITE_ADDR,AD_ZIP,OWN_CITY,OWN_STATE,OWN_ZIP,CAMA_VALUE,LAND_VALUE,"
          "BLDG_VALUE,SALE_YEAR,SALE_MONTH,PROPUSE_CD,DOR_DESC")
_R_DOR = {"0", "1", "2", "00", "01", "02", "000", "001", "002"}   # DOR residential-ish
_K_DOR = {"4", "04", "004", "005", "05", "5"}                     # condo


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
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSN", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM", " FOUNDATION", " CLUB")): return "company"
    return "individual"


def tenure(yr, mo):
    try:
        yr = int(yr); mo = int(mo) if mo else 1
        if yr < 1900 or yr > datetime.now(timezone.utc).year: return None, None
        if not 1 <= mo <= 12: mo = 1
        dt = datetime(yr, mo, 1, tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).days / 365.25, 1), dt.date().isoformat()
    except (ValueError, TypeError):
        return None, None


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config {z}")
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"AD_ZIP='{z}'", "outFields": FIELDS, "returnGeometry": "true",
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
            owner = (a.get("OWNER_NAME") or "").strip()
            addr = (a.get("SITE_ADDR") or "").strip()
            if not owner or not addr: continue
            pin = f"{z}-{addr}-{i}".replace(" ", "")[:60]
            ten, iso = tenure(a.get("SALE_YEAR"), a.get("SALE_MONTH"))
            dc = str(a.get("PROPUSE_CD") or "").strip().lstrip("0") or "0"
            desc = (a.get("DOR_DESC") or "").upper()
            if dc in _K_DOR or "CONDO" in desc: pt = "K"
            elif dc in _R_DOR or "SINGLE" in desc or "RESIDENT" in desc: pt = "R"
            else: pt = (str(a.get("PROPUSE_CD") or "R"))[:20]
            try: val = int(float(a.get("CAMA_VALUE") or (float(a.get("LAND_VALUE") or 0) + float(a.get("BLDG_VALUE") or 0))))
            except (ValueError, TypeError): val = 0
            ost = (a.get("OWN_STATE") or "").strip().upper()
            oct = (a.get("OWN_CITY") or "").strip().upper()
            lat, lng = centroid(f.get("geometry"))
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val,
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": ost or None, "owner_city": oct or None,
                "is_out_of_state": bool(ost and ost != "FL"),
                "is_absentee": bool(ost and ost != "FL") or bool(oct and oct not in local),
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/fl-indianriver-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        gm = sum(1 for i in items.values() if i["lat"] is not None)
        ab = sum(1 for i in items.values() if i["is_absentee"])
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, geom {gm/max(len(items),1)*100:.0f}%, "
              f"tenure {tn/max(len(items),1)*100:.0f}%, absentee {ab/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
