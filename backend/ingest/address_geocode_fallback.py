"""
Address-geocode fallback — pins parcels that no county GIS source covers.

Built 2026-07-28 for Dallas condos (75219/75225): the City of Dallas
parcel layer collapses condo buildings into single ACCT='MULTIPLE'
polygons, so per-unit accounts have no geometry and no derivable parent
linkage (unlike KC, where the bulk condo extract + Major+'0000' complex
parcels solved this exactly). These units DO carry street addresses, so
the fallback is the U.S. Census Bureau batch geocoder — free, no key,
up to 10k addresses per POST. All units of one building geocode to the
same street point, matching the KC building-pin convention.

Market-agnostic on purpose: any parcel with NULL lat/lng and a usable
address qualifies, so this also mops up the small non-condo residuals
anywhere in the fleet if pointed at them.

Unit suffixes ("#7J", "APT 4", "UNIT B") are stripped before geocoding —
the Census matcher wants the street address; the unit doesn't move the
rooftop.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

import httpx

CENSUS_BATCH_URL = ("https://geocoding.geo.census.gov/geocoder/"
                    "locations/addressbatch")
_UNIT_RE = re.compile(r"\s+(#|APT\b|UNIT\b|STE\b|SUITE\b).*$", re.I)


def _street_only(addr: str) -> str:
    return _UNIT_RE.sub("", (addr or "").strip())


def geocode_fallback_for_zip(supa, zip_code: str,
                             dry_run: bool = False) -> dict:
    # 1. parcels needing a pin, with an address to geocode
    rows, off = [], 0
    while True:
        page = (supa.table("parcels_v3")
                    .select("pin,address,city,state,lat,lng")
                    .eq("zip_code", zip_code)
                    .is_("lat", "null")
                    .range(off, off + 999)
                    .execute().data) or []
        rows.extend(page)
        if len(page) < 1000:
            break
        off += 1000
    todo = [r for r in rows if (r.get("address") or "").strip()]
    if not todo:
        return {"zip_code": zip_code, "candidates": 0, "matched": 0,
                "updated": 0, "dry_run": dry_run}

    # 2. one Census batch (cap 10k; our residuals are far under)
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in todo[:9500]:
        w.writerow([str(r["pin"]), _street_only(r["address"]),
                    r.get("city") or "", r.get("state") or "", zip_code])
    files = {"addressFile": ("batch.csv", buf.getvalue(), "text/csv")}
    data = {"benchmark": "Public_AR_Current"}
    with httpx.Client(timeout=420) as c:
        resp = c.post(CENSUS_BATCH_URL, data=data, files=files)
        resp.raise_for_status()

    # 3. parse result CSV: id, input, Match/No_Match/Tie, Exact/...,
    #    matched addr, "lng,lat", tigerline, side
    coords: dict[str, tuple[float, float]] = {}
    for row in csv.reader(io.StringIO(resp.text)):
        if len(row) < 6 or row[2] != "Match":
            continue
        try:
            lng_s, lat_s = row[5].split(",")
            coords[row[0].strip()] = (float(lat_s), float(lng_s))
        except Exception:
            continue

    matched = len(coords)
    if dry_run:
        return {"zip_code": zip_code, "candidates": len(todo),
                "matched": matched, "updated": 0, "dry_run": True}

    # 4. batch updates grouped by identical coordinates (buildings)
    by_coord: dict[tuple, list[str]] = defaultdict(list)
    for pin, ll in coords.items():
        by_coord[ll].append(pin)
    updated = 0
    for (lat, lng), pins in by_coord.items():
        for i in range(0, len(pins), 200):
            chunk = pins[i:i + 200]
            supa.table("parcels_v3").update({"lat": lat, "lng": lng}) \
                .in_("pin", chunk).execute()
            updated += len(chunk)

    return {"zip_code": zip_code, "candidates": len(todo),
            "matched": matched, "updated": updated, "dry_run": False}
