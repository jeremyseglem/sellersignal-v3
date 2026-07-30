#!/usr/bin/env python3
"""
Boulder County CO seed builder — wave 1 (market_key CO_BOULDER).

Boulder splits its assessor data across REST + bulk CSV (unlike Denver's one
transfers layer), so this builder joins:
  - ParcelPropertyView (REST, CamaView): AccountNo(=strap), OwnerName,
    MailingAddress, PropertyAddress, city, AccountType, Latitude/Longitude
    -> owner + situs + prop_type + GEOMETRY (lat/lon inline, WGS84)
  - Sales.csv  (bulk): strap, Tdate, deed_type -> tenure (latest Tdate/parcel)
  - Values.csv (bulk): strap, totalActualVal -> value
  - Owner_Address.csv (bulk): strap, mailingState/mailingCity -> clean absentee
join key: REST AccountNo == CSV strap (e.g. 'R0008431').

No situs-ZIP column -> ZIP assigned by lat/lon point-in-polygon against the
Census ZCTA boundaries in data/zip_polygons/co.json (CT/MT/FL/MA pattern).

CSVs default to /tmp/boco/{Sales,Values,Owner_Address}.csv (downloaded from
https://assessor.boco.solutions/ASR_PublicDataFiles/). Override dir with
BOCO_CSV_DIR.

USAGE:
  python3 scripts/build_boulder_owners.py
  ZIPS=80302 python3 scripts/build_boulder_owners.py
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PPV = os.environ.get(
    "CO_BOULDER_PPV_URL",
    "https://maps.bouldercounty.org/arcgis/rest/services/CamaView/"
    "ParcelPropertyView/MapServer/0",
)
CSV_DIR = os.environ.get("BOCO_CSV_DIR", "/tmp/boco")
POLY_PATH = os.environ.get("CO_POLYGONS", "data/zip_polygons/co.json")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# All Boulder city ZIPs; query cities cover them. local mail-city set per ZIP.
ZIP_CONFIG = {
    "80302": ("Boulder", {"BOULDER"}),   # Chautauqua / Mapleton Hill / foothills
    "80304": ("Boulder", {"BOULDER"}),   # North Boulder
    "80305": ("Boulder", {"BOULDER"}),   # South Boulder / Table Mesa
    "80303": ("Boulder", {"BOULDER", "GUNBARREL"}),  # East Boulder / Gunbarrel
    "80301": ("Boulder", {"BOULDER", "GUNBARREL"}),  # Northeast Boulder
}
QUERY_CITIES = ["BOULDER"]

csv.field_size_limit(10 * 1024 * 1024)


def _f(name):
    return os.path.join(CSV_DIR, name)


def point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_in_geom(x, y, geom):
    rings = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in rings:
        if point_in_ring(x, y, poly[0]):
            if any(point_in_ring(x, y, h) for h in poly[1:]):
                continue
            return True
    return False


def classify_owner_type(name: str) -> str:
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ", " TR ",
                            " REVOCABLE", " IRREVOCABLE", " REV ",
                            " LIVING TRUST", " FAMILY TRUST", " QPRT")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " TOWN OF", " COUNTY", " STATE OF",
                            " UNITED STATES", " SCHOOL", " DISTRICT",
                            " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM",
                            " FOUNDATION", " UNIVERSITY", " REGENTS")):
        return "company"
    return "individual"


def load_values() -> dict:
    v = {}
    with open(_f("Values.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                v[r["strap"]] = int(float(r["totalActualVal"] or 0))
            except (ValueError, TypeError):
                pass
    return v


def load_latest_sales() -> dict:
    """strap -> (latest_date iso, tenure_years)."""
    latest = {}
    with open(_f("Sales.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            s = r["strap"]
            td = (r.get("Tdate") or "").split(" ")[0]
            try:
                dt = datetime.strptime(td, "%m/%d/%Y")
            except ValueError:
                continue
            if s not in latest or dt > latest[s]:
                latest[s] = dt
    now = datetime.now()
    return {s: (dt.date().isoformat(), round((now - dt).days / 365.25, 1))
            for s, dt in latest.items()}


def load_mail() -> dict:
    m = {}
    with open(_f("Owner_Address.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            # keep the primary owner role row (role_cd blank/O first-seen)
            s = r["strap"]
            if s not in m:
                m[s] = (r.get("mailingState", "").strip().upper(),
                        r.get("mailingCity", "").strip().upper())
    return m


def fetch_ppv(city: str):
    rows, offset = [], 0
    while True:
        qs = urllib.parse.urlencode({
            "where": f"city='{city}'",
            "outFields": "AccountNo,ParcelNo,OwnerName,PropertyAddress,city,"
                         "AccountType,Latitude,Longitude,MailingAddress",
            "returnGeometry": "false", "orderByFields": "OBJECTID",
            "resultOffset": str(offset), "resultRecordCount": str(PAGE),
            "f": "json"})
        req = urllib.request.Request(f"{PPV}/query?{qs}", headers=UA)
        for a in range(4):
            try:
                d = json.load(urllib.request.urlopen(req, timeout=120)); break
            except Exception:
                if a == 3:
                    raise
                time.sleep(3 * (a + 1))
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] PPV {city} fetched {offset:,}", flush=True)
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
    zone = {(f["properties"] or {}).get("zip"): f["geometry"] for f in polys["features"]}
    miss = [z for z in target if z not in zone]
    if miss:
        raise SystemExit(f"ZIPs missing from {POLY_PATH}: {miss}")

    print("[seed] loading CSVs...", flush=True)
    values = load_values()
    sales = load_latest_sales()
    mail = load_mail()
    print(f"[seed] values={len(values):,} sales={len(sales):,} mail={len(mail):,}", flush=True)

    ppv = []
    for c in QUERY_CITIES:
        ppv.extend(fetch_ppv(c))

    # bucket parcels into target ZIPs by lat/lon PIP
    buckets = {z: {} for z in target}
    outside = no_owner = 0
    for f in ppv:
        a = f["attributes"]
        try:
            x = float(a.get("Longitude")); y = float(a.get("Latitude"))
        except (TypeError, ValueError):
            outside += 1
            continue
        zc = next((z for z in target if point_in_geom(x, y, zone[z])), None)
        if not zc:
            outside += 1
            continue
        owner = (a.get("OwnerName") or "").strip()
        if not owner:
            no_owner += 1
            continue
        strap = (a.get("AccountNo") or "").strip()
        val = values.get(strap, 0)
        sale_iso, tenure = sales.get(strap, (None, None))
        mstate, mcity = mail.get(strap, ("", ""))
        at = (a.get("AccountType") or "").strip().upper()
        prop_type = "K" if "CONDO" in at else ("R" if at == "RESIDENTIAL" else (at or "R")[:40])
        city_local = ZIP_CONFIG[zc][1]
        buckets[zc][strap or a.get("ParcelNo")] = {
            "apn": strap or str(a.get("ParcelNo")),
            "owner_name": owner,
            "owner_type": classify_owner_type(owner),
            "address": (a.get("PropertyAddress") or "").strip(),
            "value": val,
            "tenure_years": tenure,
            "last_transfer_date": sale_iso,
            "prop_type": prop_type,
            "owner_state": mstate or None,
            "owner_city": mcity or None,
            "is_out_of_state": bool(mstate and mstate != "CO"),
            "is_absentee": bool(mstate and mstate != "CO")
                           or bool(mcity and mcity not in city_local),
            "legal_description": "",
            "lat": y, "lng": x,
        }

    for z in target:
        items = buckets[z]
        city = ZIP_CONFIG[z][0]
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: addr {cov:.0f}% < 80% — refusing")
        path = f"data/seeds/co-boulder-{z}-owners.json"
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        ten = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, "
              f"tenure {ten/max(len(items),1)*100:.0f}%, "
              f"R/K {rk/max(len(items),1)*100:.0f}% -> {path}", flush=True)
    print(f"[seed] outside_target_zips={outside:,} no_owner={no_owner}", flush=True)


if __name__ == "__main__":
    main()
