#!/usr/bin/env python3
"""
Massachusetts seed builder — Greater Boston wave 1 (market_key MA_MIDDLESEX /
MA_NORFOLK; see TOWN_CONFIG for per-town market_key + county).

Pulls the MassGIS statewide Level-3 standardized parcel layer (assessor data
already joined — the CT-grade "one source, every town" win):
  arcgisserver.digital.mass.gov/.../AGOL/L3_Parcels_FeatureService_4326/
  FeatureServer/1   (WGS84 — no reprojection; 2000/page)

The layer is town-keyed (CITY), and its situs ZIP column is NULL statewide,
so ZIP territories are assigned by parcel-centroid point-in-polygon against
the Census ZCTA boundaries in data/zip_polygons/ma.json — same pattern as the
CT / MT / FL builders. Per-ZIP seed JSONs compatible with seed-from-json.

MA specifics encoded here:
  - pin            = PROP_ID (assessor parcel id, town-unique) — prefixed with
                     TOWN_ID to guarantee cross-town uniqueness in parcels_v3
                     (two towns can both have PROP_ID '37-32')
  - owner_name     = OWNER1 (joint owners inline, "Stokes, Michael C & Kimberly B"
                     / trustee markers "Libenson, M & Muto, L, Trustees")
  - value          = TOTAL_VAL (assessor total; FY-stamped)
  - tenure_years   = years since LS_DATE (YYYYMMDD string; 96% fill in sample)
  - prop_type      = prefix-matched on MA DOR residential codes. Towns use
                     EITHER 3-digit (Dover: 101/102) OR 4-digit local variants
                     (Weston/Concord: 1010/1020/1021), so match by prefix:
                     '102*' -> 'K' (condo, feeds condo bucket / V3.1 buyers),
                     '101*'/'103*'/'104*'/'105*'/'109*'/'111*'/'112*'/'1013' ->
                     'R'. Everything else stays raw (matcher's market-aware
                     default treats MA_* like WA_SNOHOMISH: unrecognized truthy
                     -> 'R'; _is_eligible_prop_type filters commercial/exempt)
  - is_absentee    = OWN_STATE != 'MA', or owner mail city outside the ZIP's
                     local USPS locality set
  - lat/lng        = parcel centroid (returnCentroid=true, outSR=4326) — rides
                     into parcels_v3 at seed, 100% map geometry, no backfill

USAGE:
  python3 scripts/build_ma_owners.py                 # all wave-1 ZIPs
  ZIPS=02481,02482 python3 scripts/build_ma_owners.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "MA_PARCELS_URL",
    "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/"
    "AGOL/L3_Parcels_FeatureService_4326/FeatureServer/1",
)
POLY_PATH = os.environ.get("MA_POLYGONS", "data/zip_polygons/ma.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# ZIP -> (town query key [CITY value, uppercase], USPS locality for letter
# copy, local mail-city set for absentee, market_key). One town can map to
# several ZIPs (Wellesley -> 02481/02482); the CITY query is the same, the
# ZCTA polygon splits them.
ZIP_CONFIG = {
    "02481": ("WELLESLEY", "Wellesley",       {"WELLESLEY", "WELLESLEY HILLS"}, "MA_NORFOLK"),
    "02482": ("WELLESLEY", "Wellesley Hills", {"WELLESLEY", "WELLESLEY HILLS"}, "MA_NORFOLK"),
    "02493": ("WESTON",    "Weston",          {"WESTON"},                       "MA_MIDDLESEX"),
    "02030": ("DOVER",     "Dover",           {"DOVER"},                        "MA_NORFOLK"),
    "01773": ("LINCOLN",   "Lincoln",         {"LINCOLN", "LINCOLN CENTER"},    "MA_MIDDLESEX"),
    "01742": ("CONCORD",   "Concord",         {"CONCORD", "WEST CONCORD"},      "MA_MIDDLESEX"),
    # ---- wave 2 (2026-07-30) ----
    # Newton is one town (CITY='NEWTON') spanning many village ZIPs; the ZCTA
    # split assigns each. All Middlesex.
    "02468": ("NEWTON",    "Chestnut Hill",     {"NEWTON", "CHESTNUT HILL"},   "MA_MIDDLESEX"),
    "02459": ("NEWTON",    "Newton Center",     {"NEWTON", "NEWTON CENTER", "NEWTON CENTRE"}, "MA_MIDDLESEX"),
    "02465": ("NEWTON",    "West Newton",       {"NEWTON", "WEST NEWTON"},     "MA_MIDDLESEX"),
    "02461": ("NEWTON",    "Newton Highlands",  {"NEWTON", "NEWTON HIGHLANDS"}, "MA_MIDDLESEX"),
    "02458": ("NEWTON",    "Newton",            {"NEWTON", "NEWTON CORNER"},   "MA_MIDDLESEX"),
    "02460": ("NEWTON",    "Newtonville",       {"NEWTON", "NEWTONVILLE"},     "MA_MIDDLESEX"),
    # Brookline is one town spanning 02445/02446. Norfolk County.
    "02445": ("BROOKLINE", "Brookline",         {"BROOKLINE"},                 "MA_NORFOLK"),
    "02446": ("BROOKLINE", "Brookline",         {"BROOKLINE"},                 "MA_NORFOLK"),
    # Lexington (Middlesex), Winchester (Middlesex)
    "02420": ("LEXINGTON", "Lexington",         {"LEXINGTON"},                 "MA_MIDDLESEX"),
    "02421": ("LEXINGTON", "Lexington",         {"LEXINGTON"},                 "MA_MIDDLESEX"),
    "01890": ("WINCHESTER","Winchester",        {"WINCHESTER"},                "MA_MIDDLESEX"),
    # Westwood, Dedham, Needham (Norfolk)
    "02090": ("WESTWOOD",  "Westwood",          {"WESTWOOD"},                  "MA_NORFOLK"),
    "02026": ("DEDHAM",    "Dedham",            {"DEDHAM"},                    "MA_NORFOLK"),
    "02492": ("NEEDHAM",   "Needham",           {"NEEDHAM", "NEEDHAM HEIGHTS"}, "MA_NORFOLK"),
    "02494": ("NEEDHAM",   "Needham Heights",   {"NEEDHAM", "NEEDHAM HEIGHTS"}, "MA_NORFOLK"),
    # ---- wave 3 (2026-07-30) — Middlesex + Norfolk only, no new-county wiring ----
    "02478": ("BELMONT",   "Belmont",           {"BELMONT"},                   "MA_MIDDLESEX"),
    "02474": ("ARLINGTON", "Arlington",         {"ARLINGTON"},                 "MA_MIDDLESEX"),
    "02476": ("ARLINGTON", "Arlington",         {"ARLINGTON"},                 "MA_MIDDLESEX"),
    "01776": ("SUDBURY",   "Sudbury",           {"SUDBURY"},                   "MA_MIDDLESEX"),
    "01778": ("WAYLAND",   "Wayland",           {"WAYLAND"},                   "MA_MIDDLESEX"),
    "01770": ("SHERBORN",  "Sherborn",          {"SHERBORN"},                  "MA_MIDDLESEX"),
    "01741": ("CARLISLE",  "Carlisle",          {"CARLISLE"},                  "MA_MIDDLESEX"),
    "02186": ("MILTON",    "Milton",            {"MILTON"},                    "MA_NORFOLK"),
    "02052": ("MEDFIELD",  "Medfield",          {"MEDFIELD"},                  "MA_NORFOLK"),
    "02025": ("COHASSET",  "Cohasset",          {"COHASSET"},                  "MA_NORFOLK"),
    "02067": ("SHARON",    "Sharon",            {"SHARON"},                    "MA_NORFOLK"),
    # ---- wave 4 (2026-07-30) — coastal; NEW counties Essex + Plymouth ----
    "01945": ("MARBLEHEAD", "Marblehead",           {"MARBLEHEAD"},            "MA_ESSEX"),
    "01944": ("MANCHESTER", "Manchester-by-the-Sea", {"MANCHESTER", "MANCHESTER-BY-THE-SEA"}, "MA_ESSEX"),
    "01907": ("SWAMPSCOTT", "Swampscott",           {"SWAMPSCOTT"},            "MA_ESSEX"),
    "01908": ("NAHANT",     "Nahant",               {"NAHANT"},                "MA_ESSEX"),
    "02043": ("HINGHAM",    "Hingham",              {"HINGHAM"},               "MA_PLYMOUTH"),
    "02332": ("DUXBURY",    "Duxbury",              {"DUXBURY"},               "MA_PLYMOUTH"),
    "02066": ("SCITUATE",   "Scituate",             {"SCITUATE"},              "MA_PLYMOUTH"),
    "02061": ("NORWELL",    "Norwell",              {"NORWELL"},               "MA_PLYMOUTH"),
}

FIELDS = ("PROP_ID,TOWN_ID,OWNER1,SITE_ADDR,CITY,ZIP,OWN_STATE,OWN_CITY,"
          "LS_DATE,LS_PRICE,TOTAL_VAL,USE_CODE,YEAR_BUILT,LS_BOOK,LS_PAGE")

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


def classify_owner_type(name: str) -> str:
    """Four-way taxonomy the bucket selector keys on. Same marker set as
    the MT/FL builders (USA word-boundary lesson included). MA suburbs are
    heavy trust country — nominee/realty trusts are the norm."""
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE",
                            " LIVING TRUST", " FAMILY TRUST", " NOMINEE",
                            " REALTY TRUST")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " TOWN OF", " COUNTY OF", " STATE OF",
                            " UNITED STATES", " SCHOOL", " DISTRICT",
                            " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM",
                            " FOUNDATION", " UNIVERSITY", " COLLEGE")):
        return "company"
    return "individual"


def fetch_town(town: str) -> list[dict]:
    """Page one town through the layer with centroids."""
    rows, offset = [], 0
    while True:
        d = gj({"where": f"CITY='{town}'", "outFields": FIELDS,
                "returnGeometry": "false", "returnCentroid": "true",
                "outSR": "4326", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"{town}: FeatureServer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] {town} fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break
    return rows


def tenure_from(ls_date: str):
    """LS_DATE is a YYYYMMDD string. Return (tenure_years, iso_date)."""
    s = (ls_date or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None, None
    try:
        dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=timezone.utc)
    except ValueError:
        return None, None
    if dt.year < 1900:
        return None, None
    yrs = round((datetime.now(timezone.utc) - dt).days / 365.25, 1)
    return yrs, dt.date().isoformat()


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] \
        or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG:
            raise SystemExit(f"ZIP {z} has no ZIP_CONFIG entry — add it first.")
    polys = json.load(open(POLY_PATH))
    zone = {(f["properties"] or {}).get("zip"): f["geometry"]
            for f in polys["features"]}
    missing = [z for z in target if z not in zone]
    if missing:
        raise SystemExit(f"ZIPs missing from {POLY_PATH}: {missing}")

    # Fetch each distinct town once, reuse across its ZIPs.
    towns = sorted({ZIP_CONFIG[z][0] for z in target})
    town_rows = {t: fetch_town(t) for t in towns}

    for z in target:
        town, city, local_cities, market_key = ZIP_CONFIG[z]
        geom = zone[z]
        rows = town_rows[town]
        items: dict[str, dict] = {}
        outside = no_owner = 0
        for f in rows:
            a = f.get("attributes") or {}
            c = f.get("centroid") or {}
            x, y = c.get("x"), c.get("y")
            if x is None or y is None or not point_in_geom(x, y, geom):
                outside += 1
                continue
            owner = (a.get("OWNER1") or "").strip()
            if not owner:
                no_owner += 1
                continue
            tenure, sale_iso = tenure_from(a.get("LS_DATE"))
            use = (a.get("USE_CODE") or "").strip()
            if use.startswith("102"):
                prop_type = "K"          # condo (3- or 4-digit: 102, 1020, 1021)
            elif use.startswith(("101", "103", "104", "105", "109",
                                 "111", "112", "1013")):
                prop_type = "R"          # residential family variants
            else:
                prop_type = (use or "R")[:40]
            mail_city = (a.get("OWN_CITY") or "").strip().upper()
            mail_state = (a.get("OWN_STATE") or "").strip().upper()
            raw_pin = str(a.get("PROP_ID") or "").strip()
            if not raw_pin:
                continue
            town_id = str(a.get("TOWN_ID") or town[:4]).strip()
            pin = f"{town_id}-{raw_pin}"   # cross-town-unique
            book = str(a.get("LS_BOOK") or "").strip()
            page = str(a.get("LS_PAGE") or "").strip()
            items[pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": (a.get("SITE_ADDR") or "").strip(),
                "value": int(a.get("TOTAL_VAL") or 0),
                "tenure_years": tenure,
                "last_transfer_date": sale_iso,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("OWN_CITY") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "MA"),
                "is_absentee": bool(mail_state and mail_state != "MA")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": (f"BK {book} PG {page}" if book and page else ""),
                "lat": y, "lng": x,
            }
        path = f"data/seeds/ma-{market_key.split('_')[1].lower()}-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        ten = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}, {market_key}): {len(items):,} parcels "
              f"(town {len(rows):,}, outside {outside:,}, no_owner {no_owner}), "
              f"addr {cov:.0f}%, tenure {ten/max(len(items),1)*100:.0f}%, "
              f"R/K {rk/max(len(items),1)*100:.0f}% -> {path}", flush=True)


if __name__ == "__main__":
    main()
