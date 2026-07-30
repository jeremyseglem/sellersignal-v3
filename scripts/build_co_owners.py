#!/usr/bin/env python3
"""
Aspen / Pitkin County CO seed builder — wave 1 (market_key CO_PITKIN).

Pulls Pitkin County's own hosted parcel layer (full assessor join, owner
names published — Colorado is an owner-publishing state):
  maps.pitkincounty.com/arcgis/rest/services/Hosted/Parcels/FeatureServer/0

No situs-ZIP column → envelope spatial query + ZCTA point-in-polygon against
data/zip_polygons/co.json (CT/MT/FL/MA pattern). CO uses the MA-style
per-county market pattern (CO_ZIP_MARKET / CO_MARKET_SLUG) so Boulder etc.
can slot in later without rework.

Pitkin specifics:
  - pin           = pin column (numeric state PIN)
  - owner_name    = owner_name (+ businessname when owner blank)
  - value         = final_actual_value
  - tenure_years  = years since sale_date (epoch ms; ~90% fill)
  - prop_type     = 'R' account_type RESIDENTIAL / COMM-RES(?) no — RESIDENTIAL
                    only; 'K' CONDO; else raw account_type (matcher default
                    treats CO_* like WA_SNOHOMISH)
  - is_absentee   = owner_state != 'CO', or owner mail city outside local set
                    (Aspen is absentee-central: NYC/LA/Chicago owners the norm)
  - lat/lng       = parcel centroid (returnCentroid, outSR=4326)

USAGE:
  python3 scripts/build_co_owners.py
  ZIPS=81611 python3 scripts/build_co_owners.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "CO_PITKIN_PARCELS_URL",
    "https://maps.pitkincounty.com/arcgis/rest/services/Hosted/Parcels/FeatureServer/0",
)
POLY_PATH = os.environ.get("CO_POLYGONS", "data/zip_polygons/co.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# ZIP -> (USPS locality, local mail-city set, market_key)
ZIP_CONFIG = {
    "81611": ("Aspen",           {"ASPEN"},                       "CO_PITKIN"),
    "81615": ("Snowmass Village", {"SNOWMASS VILLAGE", "ASPEN"},  "CO_PITKIN"),
    "81654": ("Snowmass",        {"SNOWMASS", "ASPEN", "BASALT"}, "CO_PITKIN"),
}

FIELDS = ("pin,owner_name,businessname,owner_city,owner_state,situs_address,"
          "city,final_actual_value,sale_price,sale_date,actual_yr_built,"
          "account_type,legal,platted_acres")


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
    rings = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in rings:
        if point_in_ring(x, y, poly[0]):
            if any(point_in_ring(x, y, hole) for hole in poly[1:]):
                continue
            return True
    return False


def geom_bbox(geom):
    xs, ys = [], []
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def classify_owner_type(name: str) -> str:
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE", " REV ",
                            " LIVING TRUST", " FAMILY TRUST", " QPRT")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " TOWN OF", " COUNTY", " STATE OF",
                            " UNITED STATES", " SCHOOL", " DISTRICT",
                            " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM",
                            " FOUNDATION", " UNIVERSITY", " AUTHORITY")):
        return "company"
    return "individual"


def fetch_envelope(geom) -> list[dict]:
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
                "orderByFields": "objectid",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"FeatureServer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] envelope fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break
    return rows


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] \
        or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG:
            raise SystemExit(f"ZIP {z} has no ZIP_CONFIG entry.")
    polys = json.load(open(POLY_PATH))
    zone = {(f["properties"] or {}).get("zip"): f["geometry"]
            for f in polys["features"]}
    missing = [z for z in target if z not in zone]
    if missing:
        raise SystemExit(f"ZIPs missing from {POLY_PATH}: {missing}")

    now = datetime.now(timezone.utc)
    for z in target:
        city, local_cities, market_key = ZIP_CONFIG[z]
        geom = zone[z]
        rows = fetch_envelope(geom)
        items: dict[str, dict] = {}
        outside = no_owner = 0
        for f in rows:
            a = f.get("attributes") or {}
            c = f.get("centroid") or {}
            x, y = c.get("x"), c.get("y")
            if x is None or y is None or not point_in_geom(x, y, geom):
                outside += 1
                continue
            owner = (a.get("owner_name") or "").strip() or \
                    (a.get("businessname") or "").strip()
            if not owner:
                no_owner += 1
                continue
            pin = str(a.get("pin") or "").strip()
            if not pin or pin == "None":
                continue
            sale_ms = a.get("sale_date")
            tenure = sale_iso = None
            if sale_ms:
                try:
                    dt = datetime.fromtimestamp(sale_ms / 1000, tz=timezone.utc)
                    if dt.year >= 1900:
                        tenure = round((now - dt).days / 365.25, 1)
                        sale_iso = dt.date().isoformat()
                except (ValueError, OSError):
                    pass
            at = (a.get("account_type") or "").strip().upper()
            if at == "CONDO":
                prop_type = "K"
            elif at == "RESIDENTIAL":
                prop_type = "R"
            else:
                prop_type = (at or "R")[:40]
            mail_city = (a.get("owner_city") or "").strip().upper()
            mail_state = (a.get("owner_state") or "").strip().upper()
            items[pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": (a.get("situs_address") or "").strip(),
                "value": int(a.get("final_actual_value") or 0),
                "tenure_years": tenure,
                "last_transfer_date": sale_iso,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("owner_city") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "CO"),
                "is_absentee": bool(mail_state and mail_state != "CO")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": (a.get("legal") or "").strip()[:200],
                "lat": y, "lng": x,
            }
        path = f"data/seeds/co-pitkin-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        ten = sum(1 for i in items.values() if i["tenure_years"] is not None)
        oos = sum(1 for i in items.values() if i["is_out_of_state"])
        print(f"[seed] {z} ({city}): {len(items):,} parcels (env {len(rows):,}, "
              f"outside {outside:,}, no_owner {no_owner}), addr {cov:.0f}%, "
              f"tenure {ten/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}%, "
              f"OOS {oos/max(len(items),1)*100:.0f}% -> {path}", flush=True)


if __name__ == "__main__":
    main()
