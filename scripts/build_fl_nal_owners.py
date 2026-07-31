#!/usr/bin/env python3
"""
Florida statewide NAL seed builder — ONE adapter for all 67 FL counties.

Florida DOR publishes the NAL (Name-Address-Legal) tax roll per county with
owner + situs + value + sale date + use code — a MassGIS-equivalent statewide
unlock. This builder turns any county's NAL CSV into SellerSignal seeds.

  Source: floridarevenue.com data portal, Tax Roll Data Files / NAL / {year}
  Download (SharePoint): https://floridarevenue.com{ServerRelativeUrl}  (follow redirects)
  Columns used: PARCEL_ID, DOR_UC (use), JV (just/market value),
    SALE_YR1/SALE_MO1 (most-recent sale -> tenure), OWN_NAME, OWN_CITY,
    OWN_STATE (absentee), PHY_ADDR1 (situs), PHY_CITY, PHY_ZIPCD (situs ZIP, native).
  NOT in NAL: geometry. Seeds carry no lat/lng — map pins backfill via the
  county ArcGIS parcel layer (PARCEL_ID join) as a follow-up. Lead data is complete.

CONFIG: register a county in COUNTY_CONFIG (slug, NAL csv path, ZIP->city/localset).
USAGE:
  FL_NAL_CSV=/tmp/fldor/NAL21P202602.csv COUNTY=collier python3 scripts/build_fl_nal_owners.py
  COUNTY=collier ZIPS=34102 python3 scripts/build_fl_nal_owners.py
"""
from __future__ import annotations
import csv, json, os
from datetime import date

csv.field_size_limit(10 * 1024 * 1024)

# Florida statewide parcel-centroid layer (FDOR Cadastral Centroids) — ONE geometry
# source for all 67 counties, keyed by CO_NO (DOR county number) + PARCEL_ID, both
# matching the NAL exactly. Filterable by PHY_ZIPCD (situs ZIP). Replaces per-county
# geometry hunting. Verified join on Collier 2026-07-30.
FL_STATEWIDE_CENTROIDS = ("https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/"
                          "services/Florida_Statewide_Parcel_Centroid_Version/FeatureServer/0")

# co_no = DOR county number (also the NAL filename number). Trophy ZIPs per county.
COUNTY_CONFIG = {
    "collier": {"slug": "collier", "market": "FL_COLLIER", "co_no": 21,
        "geom_url": "https://services2.arcgis.com/SlIq32SqARUHIhSx/arcgis/rest/services/Parcel/FeatureServer/2",
        "geom_id_field": "Folio", "geom_zip_field": "SiteZipCode", "zips": {
        "34102": ("Naples", {"NAPLES"}), "34103": ("Naples", {"NAPLES"}),
        "34108": ("Naples", {"NAPLES"}), "34105": ("Naples", {"NAPLES"}),
        "34110": ("Naples", {"NAPLES"})}},
    "miamidade": {"slug": "miamidade", "market": "FL_MIAMIDADE", "co_no": 23, "zips": {
        "33109": ("Miami Beach", {"MIAMI BEACH"}),      # Fisher Island
        "33139": ("Miami Beach", {"MIAMI BEACH"}),      # South Beach
        "33149": ("Key Biscayne", {"KEY BISCAYNE"}),    # Key Biscayne
        "33156": ("Pinecrest", {"PINECREST", "MIAMI"}), # Pinecrest
        "33154": ("Bal Harbour", {"BAL HARBOUR", "MIAMI BEACH", "SURFSIDE"})}},
    "broward": {"slug": "broward", "market": "FL_BROWARD", "co_no": 16,
        "geom_url": "https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0",
        "geom_id_field": "FOLIO", "geom_zip_field": "ZIP", "zips": {
        "33301": ("Fort Lauderdale", {"FORT LAUDERDALE"}),   # Las Olas
        "33308": ("Fort Lauderdale", {"FORT LAUDERDALE"}),   # Lauderdale beach
        "33316": ("Fort Lauderdale", {"FORT LAUDERDALE"}),   # Harbor Beach
        "33062": ("Pompano Beach", {"POMPANO BEACH"}),
        "33004": ("Hollywood", {"HOLLYWOOD", "DANIA BEACH"})}},  # Harbor Islands
    "sarasota": {"slug": "sarasota", "market": "FL_SARASOTA", "co_no": 68, "zips": {
        "34236": ("Sarasota", {"SARASOTA"}),        # downtown / Bird Key
        "34228": ("Longboat Key", {"LONGBOAT KEY"}),
        "34242": ("Siesta Key", {"SARASOTA", "SIESTA KEY"}),
        "34239": ("Sarasota", {"SARASOTA"}),
        "34231": ("Sarasota", {"SARASOTA"})}},
    "martin": {"slug": "martin", "market": "FL_MARTIN", "co_no": 53, "zips": {
        "33455": ("Hobe Sound", {"HOBE SOUND"}),           # Jupiter Island
        "34996": ("Stuart", {"STUART", "SEWALLS POINT"}),  # Sewall's Point
        "34994": ("Stuart", {"STUART"}),
        "34997": ("Stuart", {"STUART"}),
        "33469": ("Jupiter", {"JUPITER", "TEQUESTA"})}},   # Jupiter Island north
    "monroe": {"slug": "monroe", "market": "FL_MONROE", "co_no": 54, "zips": {
        "33040": ("Key West", {"KEY WEST"}),
        "33037": ("Key Largo", {"KEY LARGO"}),
        "33036": ("Islamorada", {"ISLAMORADA"}),
        "33050": ("Marathon", {"MARATHON"}),
        "33070": ("Tavernier", {"TAVERNIER"})}},
    "lee": {"slug": "lee", "market": "FL_LEE", "co_no": 46, "zips": {
        "33957": ("Sanibel", {"SANIBEL"}),
        "34134": ("Bonita Springs", {"BONITA SPRINGS", "ESTERO"}),
        "33908": ("Fort Myers", {"FORT MYERS", "FORT MYERS BEACH"}),
        "34135": ("Bonita Springs", {"BONITA SPRINGS"}),
        "33931": ("Fort Myers Beach", {"FORT MYERS BEACH"})}},
}


def _bbox_for_zip(z):
    """Bounding box (xmin,ymin,xmax,ymax) from the ZCTA polygon in fl.json."""
    import glob
    for path in ("data/zip_polygons/fl.json",):
        try:
            fc = json.load(open(path))
        except Exception:
            continue
        for f in fc["features"]:
            if (f.get("properties") or {}).get("zip") == z:
                xs, ys = [], []
                g = f["geometry"]
                polys = g["coordinates"] if g["type"] == "Polygon" else [r for mp in g["coordinates"] for r in mp]
                for ring in polys:
                    for pt in ring:
                        xs.append(pt[0]); ys.append(pt[1])
                if xs:
                    return (min(xs), min(ys), max(xs), max(ys))
    return None


def fetch_geom_county(cfg, z):
    """Fast path: query the county's own parcel layer (filter by situs ZIP,
    returnCentroid). Requires geom_url/geom_id_field/geom_zip_field in cfg.
    Returns {parcel_id: (lat,lng)}. Much faster than the 12M-row statewide layer."""
    import urllib.parse, urllib.request, time
    url = cfg["geom_url"]; idf = cfg["geom_id_field"]; zf = cfg["geom_zip_field"]
    ua = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
    geom, off = {}, 0
    while True:
        p = {"where": f"{zf}='{z}' OR {zf} LIKE '{z}%'", "outFields": idf,
             "returnCentroid": "true", "returnGeometry": "false",
             "resultOffset": off, "resultRecordCount": 2000, "f": "json"}
        for a in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(
                    url + "/query?" + urllib.parse.urlencode(p), headers=ua), timeout=90)); break
            except Exception:
                if a == 3: raise
                time.sleep(3 * (a + 1))
        fs = d.get("features", [])
        if not fs: break
        for f in fs:
            c = f.get("centroid") or {}
            fo = f["attributes"].get(idf)
            if fo and c.get("x") is not None:
                geom[str(fo).strip()] = (c["y"], c["x"])
        off += len(fs)
        if len(fs) < 2000: break
    return geom


def fetch_geom(cfg, z):
    """County layer if configured (fast), else statewide bbox (slow, universal)."""
    if cfg.get("geom_url"):
        return fetch_geom_county(cfg, z)
    return fetch_geom_by_bbox(cfg["co_no"], z)


def fetch_geom_by_bbox(co_no, z):
    """Return {parcel_id: (lat,lng)} via a fast spatial envelope query on the FL
    statewide centroid layer, bounded by the ZIP's ZCTA bbox + CO_NO. Uses the
    spatial index (fast) instead of an IN-clause. One source, all 67 counties."""
    import urllib.parse, urllib.request, time
    bb = _bbox_for_zip(z)
    if not bb:
        return {}
    ua = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}
    env = {"xmin": bb[0], "ymin": bb[1], "xmax": bb[2], "ymax": bb[3],
           "spatialReference": {"wkid": 4326}}
    geom, off = {}, 0
    while True:
        p = {"where": f"CO_NO={co_no}", "geometry": json.dumps(env),
             "geometryType": "esriGeometryEnvelope", "inSR": "4326",
             "spatialRel": "esriSpatialRelIntersects", "outFields": "PARCEL_ID",
             "returnGeometry": "true", "outSR": "4326",
             "resultOffset": off, "resultRecordCount": 2000, "f": "json"}
        for a in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(
                    FL_STATEWIDE_CENTROIDS + "/query?" + urllib.parse.urlencode(p), headers=ua), timeout=90)); break
            except Exception:
                if a == 3: raise
                time.sleep(3 * (a + 1))
        fs = d.get("features", [])
        if not fs: break
        for f in fs:
            g = f.get("geometry") or {}
            pid = f["attributes"].get("PARCEL_ID")
            if pid and g.get("x") is not None:
                geom[str(pid).strip()] = (g["y"], g["x"])
        off += len(fs)
        if len(fs) < 2000: break
    return geom

_R_CODES = {"001", "002", "007", "008", "000", "003", "009"}  # residential
_K_CODES = {"004", "005"}  # condo / coop


def cls(name):
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " REVOCABLE", " IRREVOCABLE", " REV ", " LIVING TRUST", " FAMILY TRUST", " TR ")): return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")): return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " HOA", " ASSN", " ASSOCIATION", " CITY OF", " COUNTY", " STATE OF", " CHURCH", " AUTHORITY", " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM", " FOUNDATION", " MINISTRIES", " CLUB")): return "company"
    return "individual"


def tenure(yr, mo):
    try:
        yr = int(yr); mo = int(mo or 1)
        if yr < 1900 or yr > date.today().year: return None, None
        mo = mo if 1 <= mo <= 12 else 1
        d = date(yr, mo, 1)
        return round((date.today() - d).days / 365.25, 1), d.isoformat()
    except (ValueError, TypeError):
        return None, None


def main():
    county = os.environ["COUNTY"].lower()
    cfg = COUNTY_CONFIG[county]
    csv_path = os.environ.get("FL_NAL_CSV") or f"/tmp/fldor/{county}_NAL.csv"
    zips = cfg["zips"]
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] or list(zips)
    buckets = {z: {} for z in target}
    seen = 0
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            pz = (row.get("PHY_ZIPCD") or "")[:5]
            if pz not in buckets: continue
            seen += 1
            owner = (row.get("OWN_NAME") or "").strip()
            pid = (row.get("PARCEL_ID") or "").strip()
            if not owner or not pid: continue
            ten, iso = tenure(row.get("SALE_YR1"), row.get("SALE_MO1"))
            uc = (row.get("DOR_UC") or "").strip().zfill(3)
            pt = "K" if uc in _K_CODES else ("R" if uc in _R_CODES else uc)
            ms = (row.get("OWN_STATE") or "").strip().upper()
            mc = (row.get("OWN_CITY") or "").strip().upper()
            local = zips[pz][1]
            addr = (row.get("PHY_ADDR1") or "").strip()
            try: val = int(float(row.get("JV") or 0))
            except (ValueError, TypeError): val = 0
            buckets[pz][pid] = {
                "apn": pid, "owner_name": owner, "owner_type": cls(owner),
                "address": addr, "value": val, "tenure_years": ten, "last_transfer_date": iso,
                "prop_type": pt, "owner_state": ms or None, "owner_city": mc or None,
                "is_out_of_state": bool(ms and ms != "FL"),
                "is_absentee": bool(ms and ms != "FL") or bool(mc and mc not in local),
                "legal_description": "", "lat": None, "lng": None,
            }
    # geometry: county layer if configured (fast), else statewide bbox
    for z in target:
        geo = fetch_geom(cfg, z)
        hit = 0
        for pid, rec in buckets[z].items():
            ll = geo.get(pid)
            if ll:
                rec["lat"], rec["lng"] = ll[0], ll[1]; hit += 1
        print(f"[seed] {z} geometry: {hit:,}/{len(buckets[z]):,} matched", flush=True)
    for z in target:
        items = buckets[z]; city = zips[z][0]
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/fl-{cfg['slug']}-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        gm = sum(1 for i in items.values() if i["lat"] is not None)
        gcov = gm / max(len(items), 1) * 100
        if items and gcov < 90:
            print(f"[seed] WARNING {z} geometry only {gcov:.0f}% — check county layer join", flush=True)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, geom {gcov:.0f}%, "
              f"tenure {tn/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
