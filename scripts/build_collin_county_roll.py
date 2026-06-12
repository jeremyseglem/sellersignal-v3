#!/usr/bin/env python3
"""
Collin County (TX) county-wide owner roll builder — pulls ALL parcels from
the CCAD public Parcels FeatureServer into the same gzipped CSV schema the
Maricopa roll uses, so `CountyOwnerIndex.from_maricopa_roll` loads it
unchanged (acct, owner_name, address, zip, city, puc).

acct = propID (== parcels_v3.pin for TX_COLLIN). puc column carries '01'
for residential (propCategoryCode A*) so the loader's RES-first ordering
works, else the raw category code.

USAGE:
  OUT=/tmp/collin-roll.csv.gz python3 scripts/build_collin_county_roll.py
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get(
    "CCAD_PARCELS_URL",
    "https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/rest/services/"
    "CCAD_Parcel_Feature_Set/FeatureServer/4",
)
OUT = os.environ.get("OUT", "/tmp/collin-roll.csv.gz")
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Roll/1.0"}
FIELDS = "propID,ownerName,situsConcatShort,situsZip,situsCity,propCategoryCode"


def gj(params: dict) -> dict:
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    total = gj({"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count", 0)
    print(f"[roll] collin parcels: {total:,}", flush=True)
    n = 0
    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["apn", "owner_name", "address", "zip", "city", "puc"])
        offset = 0
        while True:
            d = gj({"where": "1=1", "outFields": FIELDS, "returnGeometry": "false",
                    "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                    "orderByFields": "propID", "f": "json"})
            feats = d.get("features", [])
            if not feats:
                break
            for f in feats:
                a = f.get("attributes") or {}
                apn = str(a.get("propID") or "").strip()
                owner = (a.get("ownerName") or "").strip()
                if not apn or not owner:
                    continue
                cat = (a.get("propCategoryCode") or "").strip()
                w.writerow([apn, owner,
                            (a.get("situsConcatShort") or "").strip(),
                            str(a.get("situsZip") or "").strip()[:5],
                            (a.get("situsCity") or "").strip(),
                            "01" if cat.upper().startswith("A") else (cat or "OTH")])
                n += 1
            offset += len(feats)
            if offset % 50000 < PAGE:
                print(f"[roll] {offset:,}/{total:,}", flush=True)
            if len(feats) < PAGE:
                break
    print(f"[roll] wrote {n:,} rows -> {OUT}", flush=True)
    if n < total * 0.85:
        print("[roll] WARNING: wrote <85% of reported count", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
