#!/usr/bin/env python3
"""
Nashville / Davidson County TN seed builder — wave 1 (market_key TN_DAVIDSON).

Pulls Metro Nashville's public Parcels_view hosted FeatureServer:
  services2.arcgis.com/HdTo6HJqh92wn4D8/.../Parcels_view/FeatureServer/0

Richest single-source layer after PBC — everything inline AND a real situs
ZIP column (PropZip), so unlike CT/MT/FL/MA this builder filters directly by
ZIP (no ZCTA point-in-polygon needed). data/zip_polygons/tn.json still holds
the ZCTA boundaries for the MAP's ZIP outline; parcel assignment is by the
assessor's own PropZip (authoritative).

Fields:
  - pin           = ParID (Metro parcel id)
  - owner_name    = Owner ("WHELAN, PATRICK M REVOCABLE TRUST, THE" — trust
                    markers inline; Nashville is trust-heavy, ~20%)
  - value         = TotlAppr (total appraised)
  - tenure_years  = years since OwnDate (epoch ms; 100% fill in sample)
  - prop_type     = 'R' SINGLE FAMILY / DUPLEX / ZERO LOT LINE / RESIDENTIAL
                    COMBO; 'K' RESIDENTIAL CONDO; else raw LUDesc truncated
                    (matcher market-aware default treats TN_DAVIDSON like
                    WA_SNOHOMISH: unrecognized truthy -> 'R')
  - is_absentee   = OwnState != TN, or owner mail city outside the ZIP's
                    local set
  - lat/lng       = Lat/Lon columns (already WGS84) — ride in at seed, 100%
                    map geometry, no backfill

USAGE:
  python3 scripts/build_tn_owners.py            # all wave-1 ZIPs
  ZIPS=37205 python3 scripts/build_tn_owners.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get(
    "TN_PARCELS_URL",
    "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/"
    "Parcels_view/FeatureServer/0",
)
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Seed/1.0"}

# ZIP -> (USPS locality for letter copy, local mail-city set for absentee).
# All Davidson (Metro Nashville) — mail city is overwhelmingly NASHVILLE.
ZIP_CONFIG = {
    "37205": ("Nashville", {"NASHVILLE", "BELLE MEADE"}),      # Belle Meade / West Meade
    "37215": ("Nashville", {"NASHVILLE", "FOREST HILLS", "OAK HILL"}),  # Green Hills / Forest Hills
    "37220": ("Nashville", {"NASHVILLE", "OAK HILL"}),          # Oak Hill / Crieve Hall
    "37204": ("Nashville", {"NASHVILLE"}),                      # 12South / Berry Hill
    "37212": ("Nashville", {"NASHVILLE"}),                      # Hillsboro / Belmont
    "37203": ("Nashville", {"NASHVILLE"}),                      # Gulch / Music Row (condos)
}

FIELDS = ("ParID,Owner,OwnDate,SalePrice,OwnAddr1,OwnCity,OwnState,OwnZip,"
          "PropAddr,PropZip,LUDesc,TotlAppr,Acres,LegalDesc,Lat,Lon")

_R_USES = {"SINGLE FAMILY", "DUPLEX", "ZERO LOT LINE", "RESIDENTIAL COMBO/MISC",
           "TRIPLEX", "QUADPLEX"}
_K_USES = {"RESIDENTIAL CONDO"}


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


def classify_owner_type(name: str) -> str:
    n = f" {(name or '').upper()} "
    if any(m in n for m in (" TRUST", " TRUSTEE", " TRUSTEES", " TRS ",
                            " TR ", " REVOCABLE", " IRREVOCABLE",
                            " LIVING TRUST", " FAMILY TRUST")):
        return "trust"
    if any(m in n for m in (" LLC", " L L C", " LLP", " LP ", " LTD")):
        return "llc"
    if any(m in n for m in (" INC", " CORP", " COMPANY", " CO ", " USA ",
                            " HOA", " ASSOCIATION", " ASSN", " CHURCH",
                            " CITY OF", " METRO", " COUNTY OF", " STATE OF",
                            " UNITED STATES", " SCHOOL", " DISTRICT",
                            " PARTNERSHIP", " HOMEOWNERS", " CONDOMINIUM",
                            " FOUNDATION", " UNIVERSITY", " PROPERTIES")):
        return "company"
    return "individual"


def fetch_zip(zip_code: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        d = gj({"where": f"PropZip='{zip_code}'", "outFields": FIELDS,
                "returnGeometry": "false", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "f": "json"})
        if "error" in d:
            raise SystemExit(f"{zip_code}: FeatureServer error: {d['error']}")
        feats = d.get("features", [])
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        print(f"[seed] {zip_code} fetched {offset:,}", flush=True)
        if len(feats) < PAGE:
            break
    return rows


def tenure_from(own_ms):
    if own_ms is None:
        return None, None
    try:
        dt = datetime.fromtimestamp(own_ms / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None, None
    if dt.year < 1900:
        return None, None
    return round((datetime.now(timezone.utc) - dt).days / 365.25, 1), dt.date().isoformat()


def main():
    target = [z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()] \
        or list(ZIP_CONFIG)
    for z in target:
        if z not in ZIP_CONFIG:
            raise SystemExit(f"ZIP {z} has no ZIP_CONFIG entry.")
    for z in target:
        city, local_cities = ZIP_CONFIG[z]
        rows = fetch_zip(z)
        items: dict[str, dict] = {}
        no_owner = no_pin = 0
        for f in rows:
            a = f.get("attributes") or {}
            owner = (a.get("Owner") or "").strip()
            if not owner:
                no_owner += 1
                continue
            pin = str(a.get("ParID") or "").strip()
            if not pin:
                no_pin += 1
                continue
            tenure, sale_iso = tenure_from(a.get("OwnDate"))
            use = (a.get("LUDesc") or "").strip().upper()
            if use in _K_USES:
                prop_type = "K"
            elif use in _R_USES:
                prop_type = "R"
            else:
                prop_type = (use or "R")[:40]
            mail_city = (a.get("OwnCity") or "").strip().upper()
            mail_state = (a.get("OwnState") or "").strip().upper()
            lat, lon = a.get("Lat"), a.get("Lon")
            items[pin] = {
                "apn": pin,
                "owner_name": owner,
                "owner_type": classify_owner_type(owner),
                "address": (a.get("PropAddr") or "").strip(),
                "value": int(a.get("TotlAppr") or 0),
                "tenure_years": tenure,
                "last_transfer_date": sale_iso,
                "prop_type": prop_type,
                "owner_state": mail_state or None,
                "owner_city": (a.get("OwnCity") or "").strip() or None,
                "is_out_of_state": bool(mail_state and mail_state != "TN"),
                "is_absentee": bool(mail_state and mail_state != "TN")
                               or bool(mail_city and mail_city not in local_cities),
                "legal_description": (a.get("LegalDesc") or "").strip(),
                "lat": lat, "lng": lon,
            }
        path = f"data/seeds/tn-davidson-{z}-owners.json"
        with_addr = sum(1 for i in items.values() if i["address"])
        cov = (with_addr / len(items) * 100) if items else 0
        if items and cov < 80:
            raise SystemExit(f"{z}: address coverage {cov:.0f}% < 80% — refusing to write")
        json.dump(items, open(path, "w"))
        rk = sum(1 for i in items.values() if i["prop_type"] in ("R", "K"))
        ten = sum(1 for i in items.values() if i["tenure_years"] is not None)
        print(f"[seed] {z} ({city}): {len(items):,} parcels (no_owner {no_owner}, "
              f"no_pin {no_pin}), addr {cov:.0f}%, tenure {ten/max(len(items),1)*100:.0f}%, "
              f"R/K {rk/max(len(items),1)*100:.0f}% -> {path}", flush=True)


if __name__ == "__main__":
    main()
