#!/usr/bin/env python3
"""
Palm Beach County FL seed builder — wave 1 (market_key FL_PALM_BEACH).

Pulls the PBC Property Appraiser's Parcels_and_Property_Details hosted
FeatureServer (single layer: owner names + mailing address + sale date +
market value + property use + condo flag + polygon geometry, all inline —
richest single-source layer of any market to date), filters spatially per
target ZIP via an envelope query + exact point-in-polygon against the
Census ZCTA boundaries in data/zip_polygons/fl.json (the layer has no
situs-ZIP column; ZIP1/ZIP2 are MAILING zips), and writes per-ZIP seed
JSONs compatible with seed-from-json.

PBC specifics encoded here:
  - pin            = PARCEL_NUMBER (17-digit PBC PCN)
  - owner_name     = OWNER_NAME1 (+ ' & ' + OWNER_NAME2 when present and
                     not duplicative)
  - value          = TOTAL_MARKET, falling back to TOTAL_VALUE
  - tenure_years   = years since SALE_DATE (epoch ms; negative = pre-1970,
                     handled)
  - prop_type      = 'R' for SINGLE FAMILY / TOWNHOUSE / MULTIFAMILY <5 /
                     MOBILE HOME; 'K' for CONDOMINIUM / COOPERATIVE; else
                     the raw use string truncated to 40 chars (rejected by
                     the matcher's _is_eligible_prop_type downstream —
                     that filter is doing legitimate work here: common
                     areas, commercial, government)
  - is_absentee    = mailing state != FL, or mailing city outside the
                     ZIP's local USPS locality set (Manhattan/Greenwich
                     owners are the norm on the island)
  - lat/lng        = parcel centroid (outSR=4326, returnCentroid=true),
                     rides into parcels_v3 at seed time -> 100% map
                     geometry, no backfill step (CT/MT pattern)
  - CONFID_FLG=Y rows (statutory owner redactions, ~0.1%) are skipped —
    no owner name to match or mail against.

USAGE:
  ZIPS=33480,33483 python3 scripts/build_pbc_owners.py      # subset
  python3 scripts/build_pbc_owners.py                        # all wave-1
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "PBC_PARCELS_URL",
    "https://services1.arcgis.com/ZWOoUZbtaYePLlPw/ArcGIS/rest/services/"
    "Parcels_and_Property_Details_WebMercator/FeatureServer/0",
)
POLY_PATH = os.environ.get("FL_POLYGONS", "data/zip_polygons/fl.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# ZIP -> (USPS locality for letter copy, local mail-city set for absentee)
ZIP_CONFIG = {
    "33480": ("Palm Beach",         {"PALM BEACH", "SOUTH PALM BEACH"}),
    "33483": ("Delray Beach",       {"DELRAY BEACH", "GULF STREAM"}),
    "33487": ("Boca Raton",         {"BOCA RATON", "HIGHLAND BEACH", "DELRAY BEACH"}),
    "33432": ("Boca Raton",         {"BOCA RATON"}),
    "33405": ("West Palm Beach",    {"WEST PALM BEACH"}),
    "33408": ("North Palm Beach",   {"NORTH PALM BEACH", "JUNO BEACH",
                                     "PALM BEACH GARDENS", "LAKE PARK"}),
    "33477": ("Jupiter",            {"JUPITER"}),
    "33410": ("Palm Beach Gardens", {"PALM BEACH GARDENS", "NORTH PALM BEACH"}),
}

FIELDS = ("PARCEL_NUMBER,OWNER_NAME1,OWNER_NAME2,SITE_ADDR_STR,MUNICIPALITY,"
          "CITYNAME,STATE,ZIP1,SALE_DATE,PRICE,TOTAL_MARKET,TOTAL_VALUE,"
          "PROPERTY_USE,CONDO,YRBLT,CONFID_FLG,LEGAL1")

_R_USES = {"SINGLE FAMILY", "TOWNHOUSE", "MULTIFAMILY < 5 UNITS",
           "MOBILE HOME/MANUFACTURED HOME"}
_K_USES = {"CONDOMINIUM", "COOPERATIVE"}


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
            if any(point_in_ring(x, y, hole) for hole in poly[1:]):
                continue
            return True
    return False


def geom_bbox(geom) -> tuple[float, float, float, float]:
    xs, ys = [], []
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def classify_owner_type(name: str) -> str:
    """Four-way taxonomy the bucket selector keys on (trust / llc /
    company / individual). Same marker set as the MT builder (USA
    word-boundary lesson, commit a2b1dee, included)."""
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
                            " FOUNDATION", " UNIVERSITY")):
        return "company"
    return "individual"


def fetch_zip(zip_code: str, geom) -> list[dict]:
    """Envelope spatial query for one ZCTA, paged, with centroids."""
    xmin, ymin, xmax, ymax = geom_bbox(geom)
    env = json.dumps({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                      "spatialReference": {"wkid": 4326}})
    rows, offset = [], 0
    while True:
        d = gj({"where": "1=1", "geometry": env,
                "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": FIELDS, "returnGeometry": "false",
                "returnCentroid": "true", "outSR": "4326",
                "orderByFields": "OBJECTID_1",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"{zip_code}: FeatureServer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] {zip_code} envelope fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break
    return rows


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] \
        or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG:
            raise SystemExit(f"ZIP {z} has no ZIP_CONFIG entry — add its "
                             f"locality + mail-city set before running.")
    polys = json.load(open(POLY_PATH))
    zone = {(f["properties"] or {}).get("zip"): f["geometry"]
            for f in polys["features"]}
    missing = [z for z in target if z not in zone]
    if missing:
        raise SystemExit(f"ZIPs missing from {POLY_PATH}: {missing}")

    now = datetime.now(timezone.utc)
    for z in target:
        city, local_cities = ZIP_CONFIG[z]
        geom = zone[z]
        rows = fetch_zip(z, geom)
        items: dict[str, dict] = {}
        outside = no_owner = confid = 0
        for f in rows:
            a = f.get("attributes") or {}
            c = f.get("centroid") or {}
            x, y = c.get("x"), c.get("y")
            if x is None or y is None or not point_in_geom(x, y, geom):
                outside += 1
                continue
            if (a.get("CONFID_FLG") or "").strip().upper() == "Y":
                confid += 1
                continue
            owner = (a.get("OWNER_NAME1") or "").strip()
            if not owner:
                no_owner += 1
                continue
            o2 = (a.get("OWNER_NAME2") or "").strip()
            if o2 and o2.upper() not in owner.upper() and "C/O" not in o2.upper():
                owner = f"{owner} & {o2}"
            sale_ms = a.get("SALE_DATE")
            tenure = None
            sale_iso = None
            if sale_ms is not None:
                sale_dt = datetime.fromtimestamp(sale_ms / 1000, tz=timezone.utc)
                tenure = round((now - sale_dt).days / 365.25, 1)
                sale_iso = sale_dt.date().isoformat()
            use = (a.get("PROPERTY_USE") or "").strip().upper()
            condo = (a.get("CONDO") or "").strip().upper() == "YES"
            if use in _K_USES or condo:
                prop_type = "K"
            elif use in _R_USES:
                prop_type = "R"
            else:
                prop_type = (use or "R")[:40]
            mail_city = (a.get("CITYNAME") or "").strip().upper()
            mail_state = (a.get("STATE") or "").strip().upper()
            value = a.get("TOTAL_MARKET") or a.get("TOTAL_VALUE") or 0
            pin = str(a.get("PARCEL_NUMBER") or "").strip()
            if not pin:
                continue
            items[pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": (a.get("SITE_ADDR_STR") or "").strip(),
                "value": int(value or 0),
                "tenure_years": tenure,
                "last_transfer_date": sale_iso,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("CITYNAME") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "FL"),
                "is_absentee": bool(mail_state and mail_state != "FL")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": (a.get("LEGAL1") or "").strip(),
                "lat": y, "lng": x,
            }
        path = f"data/seeds/fl-palmbeach-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        print(f"[seed] {z} ({city}): {len(items):,} parcels "
              f"(env {len(rows):,}, outside {outside:,}, no_owner {no_owner}, "
              f"confid {confid}), addr {cov:.0f}%, R/K {rk/len(items)*100:.0f}% "
              f"-> {path}", flush=True)


if __name__ == "__main__":
    main()
