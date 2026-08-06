#!/usr/bin/env python3
"""
Wisconsin statewide seed builder (market_key WI_MILWAUKEE). Milwaukee North Shore
+ Lake Country trophy belt. First Wisconsin.

WI publishes a genuine STATEWIDE parcel layer (3.57M parcels) with owner + situs +
situs-ZIP + assessed/FMV value + PROPCLASS + polygon geometry. NO sale date, so
TENURE-EXEMPT (FL-style profile): trust/LLC (owner name) + value + absentee
(best-effort from PSTLADRESS) are the signals. Situs ZIP native (ZIPCODE) so
filtered by ZIP directly. No returnCentroid -> lat/lng from exterior-ring centroid.

  services3.arcgis.com/n6uYoouQZW75n5WI/.../Wisconsin_Statewide_Parcels_DB/FeatureServer/0
  OWNERNME1, SITEADRESS, ZIPCODE, ESTFMKVALUE/CNTASSDVALUE, PROPCLASS (1=residential),
  PSTLADRESS (owner mailing -> absentee).

USAGE: python3 scripts/build_wi_owners.py  |  ZIPS=53211 python3 ...
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request

BASE = os.environ.get("WI_URL",
    "https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0")
PAGE = 1000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
ZIP_CONFIG = {
    "53211": ("Whitefish Bay", {"WHITEFISH BAY", "MILWAUKEE", "SHOREWOOD"}),
    "53217": ("Fox Point",     {"FOX POINT", "RIVER HILLS", "BAYSIDE", "GLENDALE", "MILWAUKEE"}),
    "53122": ("Elm Grove",     {"ELM GROVE"}),
    "53092": ("Mequon",        {"MEQUON", "BAYSIDE"}),
    "53045": ("Brookfield",    {"BROOKFIELD"}),
    # WI statewide trophy expansion (2026-07-31) — Madison, Door County, Lake Country.
    "53705": ("Madison",       {"MADISON", "MAPLE BLUFF", "SHOREWOOD HILLS"}),
    "54235": ("Sturgeon Bay",  {"STURGEON BAY", "SEVASTOPOL"}),
    "54212": ("Fish Creek",    {"FISH CREEK", "BAILEYS HARBOR", "GIBRALTAR", "EGG HARBOR"}),
    "54234": ("Sister Bay",    {"SISTER BAY", "GIBRALTAR", "LIBERTY GROVE"}),
    "53066": ("Oconomowoc",    {"OCONOMOWOC", "LAC LA BELLE"}),
    "53018": ("Delafield",     {"DELAFIELD"}),
    "53012": ("Cedarburg",     {"CEDARBURG"}),
    "53562": ("Middleton",     {"MIDDLETON"}),
    "53213": ("Wauwatosa",     {"WAUWATOSA"}),
    "54016": ("Hudson",        {"HUDSON", "NORTH HUDSON"}),
    "54548": ("Minocqua",      {"MINOCQUA", "WOODRUFF", "ARBOR VITAE"}),
    "54521": ("Eagle River",   {"EAGLE RIVER", "LINCOLN", "WASHINGTON"}),
    "53058": ("Nashotah",      {"NASHOTAH", "CHENEQUA", "MERTON"}),
    "53072": ("Pewaukee",      {"PEWAUKEE"}),
}
FIELDS = "OWNERNME1,OWNERNME2,SITEADRESS,ZIPCODE,PLACENAME,ESTFMKVALUE,CNTASSDVALUE,PROPCLASS,PSTLADRESS"


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
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSOCIATION", " CITY OF", " COUNTY", " VILLAGE OF", " TOWN OF", " STATE OF", " CHURCH", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " FOUNDATION", " SCHOOL")): return "company"
    return "individual"


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG: raise SystemExit(f"no config {z}")
    for z in target:
        city, local = ZIP_CONFIG[z]
        rows, off = [], 0
        while True:
            d = gj({"where": f"ZIPCODE='{z}'", "outFields": FIELDS, "returnGeometry": "true",
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
            owner = (a.get("OWNERNME1") or "").strip()
            addr = (a.get("SITEADRESS") or "").strip()
            if not owner or not addr: continue
            pin = f"{z}-{addr}-{i}".replace(" ", "")[:60]
            pc = (a.get("PROPCLASS") or "").strip()
            pt = "R" if pc == "1" else (pc or "R")[:20]
            try: val = int(float(a.get("ESTFMKVALUE") or a.get("CNTASSDVALUE") or 0))
            except (ValueError, TypeError): val = 0
            # absentee: PSTLADRESS is a full mailing string; flag if it ends in a non-WI state token
            mail = (a.get("PSTLADRESS") or "").upper()
            oos = bool(mail) and " WI " not in f" {mail} " and not mail.rstrip().rstrip("0123456789 -").endswith("WI")
            lat, lng = centroid(f.get("geometry"))
            items[pin] = {"apn": pin, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val,
                "tenure_years": None, "last_transfer_date": None, "prop_type": pt,
                "owner_state": None, "owner_city": None,
                "is_out_of_state": oos,
                "is_absentee": oos,
                "legal_description": "", "lat": lat, "lng": lng}
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/wi-milwaukee-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tr = sum(1 for i in items.values() if i["owner_type"] in ("trust", "llc"))
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, trust/llc {tr/max(len(items),1)*100:.0f}%, R {rk/max(len(items),1)*100:.0f}% (tenure-exempt) -> {p}", flush=True)


if __name__ == "__main__":
    main()
