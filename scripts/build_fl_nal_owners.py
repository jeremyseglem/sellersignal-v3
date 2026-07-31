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

COUNTY_CONFIG = {
    "collier": {  # Naples
        "slug": "collier", "market": "FL_COLLIER",
        "zips": {
            "34102": ("Naples",        {"NAPLES"}),   # Old Naples / Port Royal
            "34103": ("Naples",        {"NAPLES"}),   # Moorings / Coquina Sands
            "34108": ("Naples",        {"NAPLES"}),   # Pelican Bay
            "34105": ("Naples",        {"NAPLES"}),
            "34110": ("Naples",        {"NAPLES"}),   # North Naples
        },
    },
}

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
    for z in target:
        items = buckets[z]; city = zips[z][0]
        cov = sum(1 for i in items.values() if i["address"]) / max(len(items), 1) * 100
        if items and cov < 80: raise SystemExit(f"{z}: addr {cov:.0f}% < 80%")
        p = f"data/seeds/fl-{cfg['slug']}-{z}-owners.json"; json.dump(items, open(p, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        tn = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels, addr {cov:.0f}%, tenure {tn/max(len(items),1)*100:.0f}%, R/K {rk/max(len(items),1)*100:.0f}% -> {p}", flush=True)


if __name__ == "__main__":
    main()
