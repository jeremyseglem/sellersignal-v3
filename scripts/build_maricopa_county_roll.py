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

import concurrent.futures
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


def fetch_page(offset: int):
    d = get_json({"where": "1=1", "outFields": FIELDS,
                  "returnGeometry": "false", "resultOffset": str(offset),
                  "resultRecordCount": str(PAGE),
                  "orderByFields": "APN_DASH", "f": "json"})
    rows = []
    for f in d.get("features", []):
        a = f.get("attributes") or {}
        apn = (a.get("APN_DASH") or "").strip()
        owner = (a.get("OWNER_NAME") or "").strip()
        if not apn or not owner:
            continue
        rows.append([apn, owner,
                     (a.get("PHYSICAL_ADDRESS") or "").strip(),
                     str(a.get("PHYSICAL_ZIP") or "").strip()[:5],
                     (a.get("MAIL_CITY") or "").strip(),
                     str(a.get("PUC") or "").strip()])
    return offset, rows


def main():
    # 2026-06-13: parallelized. Sequential resultOffset pagination over 1.76M
    # parcels was ~9-11s/page (worse at deep offsets) ≈ 5+ hours, which blew the
    # 350-min job timeout — the run got cancelled, the weekly cache (saved only
    # on success) never warmed, and every subsequent run rebuilt from scratch
    # and died the same way. A bounded thread pool brings it well under timeout
    # so the run completes and the cache finally sticks.
    total = get_json({"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count", 0)
    offsets = list(range(0, total, PAGE))
    workers = int(os.environ.get("ROLL_WORKERS", "10"))
    print(f"[roll] county parcels: {total:,}  pages={len(offsets)}  workers={workers}", flush=True)

    results, done = {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_page, o): o for o in offsets}
        for fut in concurrent.futures.as_completed(futs):
            off, rows = fut.result()
            results[off] = rows
            done += 1
            if done % 100 == 0 or done == len(offsets):
                print(f"[roll] {done}/{len(offsets)} pages", flush=True)

    n = 0
    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["apn", "owner_name", "address", "zip", "city", "puc"])
        for off in sorted(results):
            for row in results[off]:
                w.writerow(row)
                n += 1
    print(f"[roll] wrote {n:,} rows -> {OUT}", flush=True)
    if n < total * 0.9:
        print(f"[roll] WARNING: wrote <90% of reported count", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
