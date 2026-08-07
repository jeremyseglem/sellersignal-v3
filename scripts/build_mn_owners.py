#!/usr/bin/env python3
"""
Minnesota seed builder (market_key MN_HENNEPIN). Lake Minnetonka + Edina +
Minneapolis lakes. First Minnesota.

The HennCarv (Hennepin + Carver) parcel layer is a FULL-signal layer: OWNER_NAME,
componentized situs address (ANUMBER + ST_* -> assembled), native situs ZIP,
EMV_TOTAL (est. market value), SALE_DATE (epoch ms -> tenure), USECLASS1 (prop_type),
OWN_ADD_L* (owner mailing -> absentee), polygon geometry. Parcels with no SALE_DATE
are long-held (left null tenure). Situs ZIP native so filtered by ZIP directly.
No returnCentroid -> lat/lng from exterior-ring centroid.

  services.arcgis.com/8df8p0NlLFEShl0r/.../HennCarv_Parcels/FeatureServer/0

USAGE: python3 scripts/build_mn_owners.py  |  ZIPS=55391 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("MN_URL",
    "https://services.arcgis.com/8df8p0NlLFEShl0r/arcgis/rest/services/HennCarv_Parcels/FeatureServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "55391": ("Wayzata",     {"ORONO", "WAYZATA", "MINNETONKA BEACH"}),   # Lake Minnetonka N
    "55356": ("Long Lake",   {"LONG LAKE", "ORONO", "MEDINA"}),
    "55364": ("Mound",       {"MINNETRISTA", "MOUND", "SPRING PARK"}),
    "55331": ("Excelsior",   {"VICTORIA", "EXCELSIOR", "SHOREWOOD", "TONKA BAY", "DEEPHAVEN", "GREENWOOD"}),
    "55424": ("Edina",       {"EDINA"}),           # Country Club
    "55410": ("Minneapolis", {"MINNEAPOLIS", "EDINA"}),   # Linden Hills / Lake Harriet
    "55405": ("Minneapolis", {"MINNEAPOLIS"}),     # Kenwood / Lowry Hill
    "55416": ("Minneapolis", {"MINNEAPOLIS", "ST LOUIS PARK", "GOLDEN VALLEY"}),  # Cedar Lake
}
FIELDS = ("ANUMBER,ST_PRE_DIR,ST_NAME,ST_POS_TYP,ST_POS_DIR,CTU_NAME,POSTCOMM,ZIP,"
          "OWNER_NAME,OWN_ADD_L3,OWN_ADD_L4,EMV_TOTAL,SALE_DATE,USECLASS1")


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
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSN", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " FOUNDATION", " SCHOOL", " CHURCH")): return "company"
    return "individual"


def tenure(ms):
    try:
        ms = int(ms)
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        if dt.year < 1900 or dt.year > datetime.now(timezone.utc).year: return None, None
        return round((datetime.now(timezone.utc) - dt).days / 365.25, 1), dt.date().isoformat()
    except (ValueError, TypeError, OSError):
        return None, None


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config {z}")
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"ZIP='{z}'", "outFields": FIELDS, "returnGeometry": "true",
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
            addr = " ".join(str(a.get(k) or "").strip() for k in
                            ["ANUMBER", "ST_PRE_DIR", "ST_NAME", "ST_POS_TYP", "ST_POS_DIR"]).split()
            addr = " ".join(addr)
            if not owner or not addr: continue
            pin = f"{z}-{addr}-{i}".replace(" ", "")[:60]
            ten, iso = tenure(a.get("SALE_DATE"))
            uc = (a.get("USECLASS1") or "").upper()
            pt = "K" if any(k in uc for k in ("CONDO", "TOWNHOUSE", "TOWNHOME")) else ("R" if "RESIDENTIAL" in uc else (uc or "R")[:30])
            try: val = int(float(a.get("EMV_TOTAL") or 0))
            except (ValueError, TypeError): val = 0
            mc = (a.get("OWN_ADD_L3") or "").strip().upper()  # owner mailing city/state line
            oos = bool(mc) and " MN " not in f" {mc} " and not mc.rstrip().endswith("MN")
            lat, lng = centroid(f.get("geometry"))
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val,
                "tenure_years": ten, "last_transfer_date": iso, "prop_type": pt,
                "owner_state": None, "owner_city": mc or None,
                "is_out_of_state": oos,
                "is_absentee": oos or bool(mc and not any(c in mc for c in local)),
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/mn-hennepin-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        tr = sum(1 for i in items.values() if i["owner_type"] in ("trust", "llc"))
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, trust/llc {tr/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
