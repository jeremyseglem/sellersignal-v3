#!/usr/bin/env python3
"""
Maricopa County (AZ) county-wide owner roll builder — produces a compact
gzipped CSV of EVERY parcel's owner for the county-wide decedent inversion
(the same architecture that fixed Dallas's zero-probate-leads coverage math).

SOURCE: the Maricopa Assessor's public Parcels MapServer (same layer the
per-ZIP seed builder uses), paginated county-wide with a minimal field set.
~1.6M parcels at 1000/page ≈ 1,600 requests; runs in a GitHub Action and is
cached weekly (the roll drifts slowly).

OUTPUT columns: apn (APN_DASH — matches parcels_v3.pin for AZ_MARICOPA),
owner_name, address, city, zip, puc.

USAGE:
  OUT=/tmp/maricopa-roll.csv.gz python3 scripts/build_maricopa_county_roll.py
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

PARCELS_URL = os.environ.get(
    "PARCELS_URL",
    "https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0",
)
OUT = os.environ.get("OUT", "/tmp/maricopa-roll.csv.gz")
PAGE = int(os.environ.get("PAGE_SIZE", "1000"))
FIELDS = "APN_DASH,OWNER_NAME,PHYSICAL_ADDRESS,PHYSICAL_ZIP,MAIL_CITY,PUC"
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Roll/1.0"}


def get_json(params: dict) -> dict:
    url = f"{PARCELS_URL}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    total = get_json({"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count", 0)
    print(f"[roll] county parcels: {total:,}", flush=True)
    n = 0
    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["apn", "owner_name", "address", "zip", "city", "puc"])
        offset = 0
        while True:
            d = get_json({"where": "1=1", "outFields": FIELDS,
                          "returnGeometry": "false", "resultOffset": str(offset),
                          "resultRecordCount": str(PAGE),
                          "orderByFields": "APN_DASH", "f": "json"})
            feats = d.get("features", [])
            if not feats:
                break
            for f in feats:
                a = f.get("attributes") or {}
                apn = (a.get("APN_DASH") or "").strip()
                owner = (a.get("OWNER_NAME") or "").strip()
                if not apn or not owner:
                    continue
                w.writerow([apn, owner,
                            (a.get("PHYSICAL_ADDRESS") or "").strip(),
                            str(a.get("PHYSICAL_ZIP") or "").strip()[:5],
                            (a.get("MAIL_CITY") or "").strip(),
                            str(a.get("PUC") or "").strip()])
                n += 1
            offset += len(feats)
            if offset % 50000 < PAGE:
                print(f"[roll] {offset:,}/{total:,}", flush=True)
            if len(feats) < PAGE:
                break
    print(f"[roll] wrote {n:,} rows -> {OUT}", flush=True)
    if n < total * 0.9:
        print(f"[roll] WARNING: wrote <90% of reported count", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
