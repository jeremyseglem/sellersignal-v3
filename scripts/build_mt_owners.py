#!/usr/bin/env python3
"""
Montana seed builder — Gallatin / Madison / Flathead Phase 1
(market_keys MT_GALLATIN, MT_MADISON, MT_FLATHEAD; Big Sky spans two).

Pulls the Montana State Library statewide Cadastral FeatureServer (DOR ORION
attributes, monthly refresh) county-by-county, assigns each parcel a ZIP via
centroid point-in-polygon against Census ZCTA boundaries in
data/zip_polygons/mt.json — the layer's own CityStateZip field is unreliable
(DOR labels nearly all of Bozeman "59715"; 59718 shows 626 by field vs
16,460 spatially, verified 2026-07-23) — and writes per-ZIP seed JSONs
compatible with seed-from-json.

MT specifics encoded here:
  - pin            = PARCELID (17-digit DOR geocode; Geocode field identical)
  - owner_name     = OwnerName (single field; joint owners inline
                     "HANSON BART W & CHERYL K" style, same as Snohomish)
  - value          = TotalValue (DOR ORION market total)
  - tenure_years   = None at seed. The FeatureServer/CAMA extract carries no
                     transfer date; the ORION Deed table (DeedDate/RecordedDate/
                     DocType) ships only inside per-county SQL Server .mdf
                     archives. Tenure backfills later via an MT
                     property-record-card task (snohomish_scopi precedent).
  - prop_type      = 'R' for {'Improved Property','Townhouse'}, else the raw
                     DOR string (matcher's market-aware default must treat
                     MT_* like WA_SNOHOMISH: unrecognized truthy -> 'R').
                     'Vacant Land', 'Exempt Property' etc. stay raw and are
                     filtered by _is_eligible_prop_type.
  - is_absentee    = OwnerState != 'MT', or owner mail city outside the
                     ZIP's local mail-city set (resort markets: this is the
                     dominant signal family)
  - lat/lng        = parcel centroid (returnCentroid=true, outSR=4326) ->
                     rides into parcels_v3 at seed time, 100% map geometry,
                     no backfill step
  - county scope   = COUNTYCD 6 (Gallatin), 25 (Madison), 7 (Flathead).
                     Big Sky 59716 straddles 6+25 (verified ~7:1 Madison).

USAGE:
  python3 scripts/build_mt_owners.py                 # all six ZIPs
  ZIPS=59716 python3 scripts/build_mt_owners.py      # subset
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

BASE = os.environ.get(
    "MT_PARCELS_URL",
    "https://gis.dnrc.mt.gov/arcgis/rest/services/DNRALL/Cadastral/FeatureServer/0",
)
POLY_PATH = os.environ.get("MT_POLYGONS", "data/zip_polygons/mt.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# ZIP -> (city, market_key hint, county codes to query, local mail-city set)
ZIP_CONFIG = {
    "59715": ("Bozeman",          [6],     {"BOZEMAN"}),
    "59718": ("Bozeman",          [6],     {"BOZEMAN"}),
    "59714": ("Belgrade",         [6],     {"BELGRADE", "BOZEMAN"}),
    "59730": ("Gallatin Gateway", [6],     {"GALLATIN GATEWAY", "BOZEMAN"}),
    "59716": ("Big Sky",          [6, 25], {"BIG SKY", "GALLATIN GATEWAY", "BOZEMAN"}),
    "59937": ("Whitefish",        [7],     {"WHITEFISH"}),
    # Flathead Lake trophy cluster (2026-07-31) — Flathead county (7)
    "59911": ("Bigfork",          [7],     {"BIGFORK"}),
    "59922": ("Lakeside",         [7],     {"LAKESIDE"}),
    "59901": ("Kalispell",        [7],     {"KALISPELL"}),
    "59912": ("Columbia Falls",   [7],     {"COLUMBIA FALLS"}),
    # New MT counties (2026-07-31) — trophy resort/valley towns
    "59047": ("Livingston",       [49],    {"LIVINGSTON", "PARADISE VALLEY", "PRAY", "EMIGRANT"}),  # Park / Paradise Valley
    "59840": ("Hamilton",         [13],    {"HAMILTON", "CORVALLIS", "VICTOR"}),   # Ravalli / Bitterroot
    "59860": ("Polson",           [15],    {"POLSON", "BIGFORK", "ROLLINS"}),      # Lake / Flathead Lake S
    "59068": ("Red Lodge",        [10],    {"RED LODGE", "ROBERTS"}),              # Carbon
    "59729": ("Ennis",            [25],    {"ENNIS", "MCALLISTER", "VIRGINIA CITY"}),  # Madison
    # Paradise Valley / Park county (49) (2026-07-31)
    "59047": ("Livingston",       [49],    {"LIVINGSTON"}),
    "59027": ("Emigrant",         [49],    {"EMIGRANT", "PRAY"}),
    "59030": ("Gardiner",         [49],    {"GARDINER"}),
}
ELIGIBLE_RES = {"IMPROVED PROPERTY", "TOWNHOUSE"}

FIELDS = ("PARCELID,OwnerName,OwnerCity,OwnerState,OwnerZipCode,"
          "AddressLine1,AddressLine2,CityStateZip,PropType,TotalValue,"
          "TotalLandValue,TotalAcres,COUNTYCD")


def gj(params: dict) -> dict:
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=110))
        except Exception:
            if attempt == 4:
                raise
            time.sleep(4 * (attempt + 1))


def point_in_ring(x, y, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geom(x, y, geom) -> bool:
    rings = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in rings:
        if point_in_ring(x, y, poly[0]):
            if any(point_in_ring(x, y, hole) for hole in poly[1:]):
                continue
            return True
    return False


def classify_owner_type(name: str) -> str:
    """Same four-way taxonomy as the CT/Snohomish builders (trust / llc /
    company / individual), USA word-boundary lesson (commit a2b1dee)
    included. Montana resort ground is trust + LLC country."""
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE",
                            " LIVING TRUST", " FAMILY TRUST")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " COUNTY OF", " STATE OF",
                            " UNITED STATES", " SCHOOL", " DISTRICT",
                            " PARTNERSHIP", " HOMEOWNERS", " CONDO",
                            " RANCH INC", " FOUNDATION", " UNIVERSITY")):
        return "company"
    return "individual"


def fetch_county(county_cd: int) -> list[dict]:
    """Page the full county through the FeatureServer with centroids."""
    rows: list[dict] = []
    offset = 0
    while True:
        d = gj({
            "where": f"COUNTYCD = {county_cd}",
            "outFields": FIELDS,
            "returnGeometry": "false",
            "returnCentroid": "true",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": PAGE,
            "orderByFields": "OBJECTID",
            "f": "json",
        })
        feats = d.get("features", [])
        rows.extend(feats)
        if len(feats) < PAGE:
            break
        offset += PAGE
        if offset % 20000 == 0:
            print(f"    county {county_cd}: {offset:,} rows...")
    print(f"  county {county_cd}: {len(rows):,} parcels fetched")
    return rows


def main():
    target_zips = [z for z in os.environ.get("ZIPS", ",".join(ZIP_CONFIG)).split(",")
                   if z.strip() in ZIP_CONFIG]
    poly = json.load(open(POLY_PATH))
    zones = [(f["properties"]["zip"], f["geometry"]) for f in poly["features"]
             if f["properties"]["zip"] in target_zips]
    counties = sorted({c for z in target_zips for c in ZIP_CONFIG[z][1]})
    print(f"[seed] ZIPs {target_zips} -> counties {counties}")

    county_rows: dict[int, list] = {c: fetch_county(c) for c in counties}

    by_zip: dict[str, dict] = {z: {} for z in target_zips}
    no_owner = unzoned = 0
    for c, rows in county_rows.items():
        for f in rows:
            a = f.get("attributes") or {}
            cen = f.get("centroid") or {}
            owner = (a.get("OwnerName") or "").strip()
            if not owner:
                no_owner += 1
                continue
            x, y = cen.get("x"), cen.get("y")
            if x is None or y is None:
                unzoned += 1
                continue
            zip_code = None
            for z, geom in zones:
                if c in ZIP_CONFIG[z][1] and point_in_geom(x, y, geom):
                    zip_code = z
                    break
            if not zip_code:
                unzoned += 1
                continue
            raw_type = (a.get("PropType") or "").strip()
            prop_type = "R" if raw_type.upper() in ELIGIBLE_RES else (raw_type or "R")
            mail_state = (a.get("OwnerState") or "").strip().upper()
            mail_city = (a.get("OwnerCity") or "").strip().upper()
            local_cities = ZIP_CONFIG[zip_code][2]
            addr = " ".join(p for p in ((a.get("AddressLine1") or "").strip(),
                                        (a.get("AddressLine2") or "").strip()) if p)
            pin = str(a.get("PARCELID") or "").strip()
            if not pin:
                continue
            by_zip[zip_code][pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": addr,
                "value": int(a.get("TotalValue") or 0),
                "tenure_years": None,
                "last_transfer_date": None,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("OwnerCity") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "MT"),
                "is_absentee": bool(mail_state and mail_state != "MT")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": "",
                "lat": y, "lng": x,
            }

    print(f"[seed] no_owner={no_owner} outside_target_zctas={unzoned}")
    for z in target_zips:
        items = by_zip[z]
        city = ZIP_CONFIG[z][0]
        path = f"data/seeds/mt-{z}-owners.json"
        res = [i for i in items.values() if i["prop_type"] == "R"]
        with_addr = sum(1 for i in res if i["address"])
        cov = (with_addr / len(res) * 100) if res else 0
        # Gate on RESIDENTIAL coverage: resort ZIPs carry heavy Vacant Land /
        # Exempt fractions that legitimately lack situs addresses (59716
        # measured R=84% vs all-parcels=70%, 2026-07-23). The gate's job is
        # catching broken builders (May 10 0%-bug shape), not real gaps.
        if res and cov < 80:
            raise SystemExit(f"{z}: residential address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        n_abs = sum(1 for i in items.values() if i["is_absentee"])
        n_trust = sum(1 for i in items.values() if i["owner_type"] == "trust")
        n_llc = sum(1 for i in items.values() if i["owner_type"] == "llc")
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, "
              f"absentee {n_abs:,}, trust {n_trust:,}, llc {n_llc:,} -> {path}")


if __name__ == "__main__":
    main()
