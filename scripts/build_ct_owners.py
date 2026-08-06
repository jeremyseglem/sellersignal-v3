#!/usr/bin/env python3
"""
Connecticut seed builder — Greenwich Phase 1 (market_key CT_FAIRFIELD).

Pulls the CT OPM statewide parcel+CAMA FeatureServer filtered to one town,
assigns each parcel a ZIP via point-in-polygon against the Census ZCTA
boundaries in data/zip_polygons/ct.json (the statewide layer has no ZIP
column — town-keyed; the spatial join makes it ZIP-first like every other
market), and writes per-ZIP seed JSONs compatible with seed-from-json.

CT specifics encoded here:
  - pin            = Link (town-prefixed unique assessor code, e.g. 33620-10-2288)
  - owner_name     = Owner (+ ' & ' + Co_Owner when present; joint owners
                     often already inline like 'GREENBERG NED & LESLIE W/S')
  - value          = Appraised_Land + Appraised_Building (market), falling
                     back to Assessed_Total / 0.70 (CT assesses at 70%)
  - tenure_years   = years since Sale_Date (epoch ms)
  - prop_type      = 'R' when State_Use starts with '1' (101 single family,
                     102 condo, 103/107/109 multi/res variants), else the
                     raw code (matcher's market-aware default handles edge
                     codes; Greenwich top codes verified 2026-06-12)
  - city           = USPS locality per ZIP (Old Greenwich / Riverside /
                     Cos Cob / Greenwich) — matters for letter copy
  - is_absentee    = mailing state != CT, or mailing city not the situs
                     locality set (Manhattan owners are the norm here)
  - lat/lng        = parcel centroid (outSR=4326), rides into parcels_v3
                     at seed time -> 100% map geometry, no backfill step

USAGE:
  TOWN=Greenwich python3 scripts/build_ct_owners.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "CT_PARCELS_URL",
    "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/"
    "Connecticut_State_Parcel_Layer_2023/FeatureServer/0",
)
TOWN = os.environ.get("TOWN", "Greenwich")
POLY_PATH = os.environ.get("CT_POLYGONS", "data/zip_polygons/ct.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

_TOWN_CONFIG = {
    # town -> (ZIP_CITY map, local USPS mail-city set for absentee logic)
    "Greenwich": (
        {"06830": "Greenwich", "06831": "Greenwich", "06870": "Old Greenwich",
         "06878": "Riverside", "06807": "Cos Cob"},
        {"GREENWICH", "OLD GREENWICH", "RIVERSIDE", "COS COB"},
    ),
    "Darien":     ({"06820": "Darien"},     {"DARIEN", "NOROTON", "NOROTON HEIGHTS"}),
    "New Canaan": ({"06840": "New Canaan"}, {"NEW CANAAN"}),
    "Westport":   ({"06880": "Westport"},   {"WESTPORT"}),
    "Wilton":     ({"06897": "Wilton"},     {"WILTON"}),
    "Weston":     ({"06883": "Weston"},     {"WESTON"}),
    # Fairfield County expansion (2026-07-31) — trophy towns, statewide layer,
    # addr>=99% verified. Southport (06890) is the trophy pocket of Fairfield.
    "Fairfield":  ({"06824": "Fairfield", "06825": "Fairfield", "06890": "Southport"},
                   {"FAIRFIELD", "SOUTHPORT"}),
    "Ridgefield": ({"06877": "Ridgefield"}, {"RIDGEFIELD"}),
    "Easton":     ({"06612": "Easton"},     {"EASTON"}),
}
if TOWN not in _TOWN_CONFIG:
    raise SystemExit(f"TOWN={TOWN!r} has no _TOWN_CONFIG entry — add its "
                     f"ZIP_CITY map and local mail-city set before running.")
ZIP_CITY, LOCAL_MAIL_CITIES = _TOWN_CONFIG[TOWN]
FIELDS = ("Link,Owner,Co_Owner,Location,Mailing_City,Mailing_State,"
          "Assessed_Total,Appraised_Land,Appraised_Building,Sale_Date,State_Use")


def gj(params: dict) -> dict:
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=90))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def point_in_ring(x, y, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_in_geom(x, y, geom) -> bool:
    if geom["type"] == "Polygon":
        rings = [geom["coordinates"]]
    else:  # MultiPolygon
        rings = geom["coordinates"]
    for poly in rings:
        if point_in_ring(x, y, poly[0]):
            # outer ring hit; respect holes
            if any(point_in_ring(x, y, hole) for hole in poly[1:]):
                continue
            return True
    return False


def classify_owner_type(name: str) -> str:
    """Four-way taxonomy the bucket selector keys on: trust / llc /
    company / individual. Greenwich is trust country — CT deeds carry
    TRUST / TRUSTEE(S) / TR / REV TRUST / LIVING TRUST markers heavily."""
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE",
                            " LIVING TR", " FAMILY TR")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LP ", " LLP", " LTD")):
        return "llc"
    company_markers = (" INC", " CORP", " CO ", " COMPANY", " PARTNERS",
                       " ASSOCIATES", " HOLDINGS", " BANK", " CHURCH",
                       " TOWN OF ", " STATE OF ", " CONDOMINIUM", " ASSN",
                       " ASSOCIATION")
    return "company" if any(m in n for m in company_markers) else "individual"


def main():
    polys = json.load(open(POLY_PATH))
    zones = [((f["properties"] or {}).get("zip"), f["geometry"])
             for f in polys["features"]
             if (f["properties"] or {}).get("zip") in ZIP_CITY]

    rows, offset = [], 0
    while True:
        d = gj({"where": f"Town_Name='{TOWN}'", "outFields": FIELDS,
                "returnGeometry": "false", "returnCentroid": "true",
                "outSR": "4326", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break

    now = datetime.now(timezone.utc)
    by_zip: dict[str, dict] = {z: {} for z in ZIP_CITY}
    unzoned = no_owner = 0
    for f in rows:
        a = f.get("attributes") or {}
        c = f.get("centroid") or {}
        owner = (a.get("Owner") or "").strip()
        if not owner:
            no_owner += 1
            continue
        co = (a.get("Co_Owner") or "").strip()
        if co and co.upper() not in owner.upper():
            owner = f"{owner} & {co}"
        x, y = c.get("x"), c.get("y")
        zip_code = None
        if x is not None and y is not None:
            for z, geom in zones:
                if point_in_geom(x, y, geom):
                    zip_code = z
                    break
        if not zip_code:
            unzoned += 1
            continue
        appraised = (a.get("Appraised_Land") or 0) + (a.get("Appraised_Building") or 0)
        if not appraised and a.get("Assessed_Total"):
            appraised = int(a["Assessed_Total"] / 0.70)
        sale_ms = a.get("Sale_Date")
        tenure = None
        if sale_ms:
            tenure = round((now - datetime.fromtimestamp(sale_ms / 1000, tz=timezone.utc)).days / 365.25, 1)
        use = (a.get("State_Use") or "").strip()
        mail_city = (a.get("Mailing_City") or "").strip().upper()
        mail_state = (a.get("Mailing_State") or "").strip().upper()
        pin = str(a.get("Link") or "").strip()
        by_zip[zip_code][pin] = {
            "apn": pin,
            "owner_name": owner,
            "owner_type": classify_owner_type(owner),
            "address": (a.get("Location") or "").strip(),
            "value": int(appraised or 0),
            "tenure_years": tenure,
            "last_transfer_date": (datetime.fromtimestamp(sale_ms / 1000, tz=timezone.utc).date().isoformat() if sale_ms else None),
            "prop_type": "R" if use.startswith("1") else (use or "R"),
            "owner_state": mail_state or None,
            "owner_city": (a.get("Mailing_City") or "").strip() or None,
            "is_out_of_state": bool(mail_state and mail_state != "CT"),
            "is_absentee": bool(mail_state and mail_state != "CT") or bool(mail_city and mail_city not in LOCAL_MAIL_CITIES),
            "legal_description": "",
            "lat": y, "lng": x,
        }

    print(f"[seed] town rows={len(rows):,} no_owner={no_owner} outside_zctas={unzoned}")
    for z, items in by_zip.items():
        path = f"data/seeds/ct-fairfield-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        print(f"[seed] {z} ({ZIP_CITY[z]}): {len(items):,} parcels, addr {cov:.0f}% -> {path}")


if __name__ == "__main__":
    main()
