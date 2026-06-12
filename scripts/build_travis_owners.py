#!/usr/bin/env python3
"""
Travis County (TX) seed builder — produces data/seeds/tx-travis-{zip}-owners.json
for the onboarding orchestrator's `seed` step. Mirrors build_dallas_owners.py
(same output schema, same classify_owner_type, same 80% address gate).

SOURCE: TCAD "Preliminary/Certified Appraisal Roll Export" (free, posted at
  https://traviscad.org/publicinformation/ -> wp-content/largefiles/*.zip).
The export is the TrueProdigy "Legacy 8.0.32" fixed-width layout (layout zip
posted alongside). We read PROP.TXT (~4.8 GB, one row per property+owner).

Texas is a NON-DISCLOSURE state — `value` is appraised market_value; tenure
comes from deed_dt. Single-family residential = imprv_state_cd starting 'A'.

GEOMETRY: the City of Austin publishes TCAD parcels as an ESRI-hosted layer
(EXTERNAL_tcad_parcel, services.arcgis.com/0L95CJ0VTaxqcmED). We query it in
PROP_ID batches and write WGS84 centroid lat/lng into the seed (the Dallas
seed-time-geometry pattern — no post-onboarding backfill needed). Layer
PROP_ID is the roll's prop_id with leading zeros stripped; seed pins use the
stripped form so every downstream join (matcher Layer 0, county resolve,
geometry) shares one key format.

USAGE (multi-ZIP in one roll scan — the scan dominates runtime):
  TARGET_ZIPS=78746,78703 TCAD_ROLL=/tmp/tcad/roll2026.zip \
      OUT_DIR=data/seeds python3 scripts/build_travis_owners.py
  GEOM=0 skips the centroid fetch.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_dallas_owners import classify_owner_type, _VALID_US_STATES  # noqa: E402

TARGET_ZIPS = [z.strip() for z in os.environ.get("TARGET_ZIPS", "").split(",") if z.strip()]
TCAD_ROLL = os.environ.get("TCAD_ROLL", "/tmp/tcad/roll2026.zip")
OUT_DIR = os.environ.get("OUT_DIR", "data/seeds")
MIN_ADDRESS_COVERAGE = float(os.environ.get("MIN_ADDRESS_COVERAGE", "0.80"))
FETCH_GEOM = os.environ.get("GEOM", "1") != "0"
GEOM_LAYER = ("https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/"
              "services/EXTERNAL_tcad_parcel/FeatureServer/0/query")
TODAY = date.today()

# Legacy 8.0.32 PROP.TXT field positions (1-indexed inclusive; see
# TP_Legacy8.0.32-AppraisalExportLayout.xlsx "Property" sheet).
F = {
    "prop_id":      (1, 12),
    "yr":           (18, 22),
    "owner":        (609, 678),
    "o_city":       (874, 923),
    "o_state":      (924, 973),
    "o_zip":        (979, 983),
    "s_prefix":     (1040, 1049),
    "s_street":     (1050, 1099),
    "s_suffix":     (1100, 1109),
    "s_city":       (1110, 1139),
    "s_zip":        (1140, 1149),
    "legal":        (1150, 1404),
    "deed_dt":      (2034, 2058),
    "state_cd":     (2732, 2741),
    "market":       (4214, 4227),
    "s_num":        (4460, 4474),
    "s_unit":       (4475, 4479),
}


def _log(m):
    print(m, file=sys.stderr)


def fx(line: str, key: str) -> str:
    s, e = F[key]
    return line[s - 1:e].strip()


def _norm_state(raw: str) -> str:
    s = (raw or "").strip().upper()
    if len(s) == 2:
        return s
    full = {"TEXAS": "TX", "CALIFORNIA": "CA", "NEW YORK": "NY", "FLORIDA": "FL",
            "WASHINGTON": "WA", "COLORADO": "CO", "ARIZONA": "AZ", "ILLINOIS": "IL"}
    return full.get(s, s[:2] if s else "")


def _parse_deed(s: str):
    s = (s or "").strip()
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y", "%b %d %Y"):
        try:
            return datetime.strptime(s.split()[0] if " " in s else s, fmt).date()
        except (ValueError, IndexError):
            continue
    return None


def fetch_centroids(pins: list) -> dict:
    """PROP_ID-batch query against the hosted TCAD parcel layer; centroid =
    mean of the outer-ring vertices (sufficient for map pins)."""
    out = {}
    hdrs = {"User-Agent": "Mozilla/5.0"}
    B = 100
    for i in range(0, len(pins), B):
        batch = pins[i:i + B]
        where = urllib.request.quote(f"PROP_ID IN ({','.join(batch)})")
        url = (f"{GEOM_LAYER}?where={where}&outFields=PROP_ID"
               f"&returnGeometry=true&outSR=4326&f=json")
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=hdrs)
                d = json.load(urllib.request.urlopen(req, timeout=45))
                for f in d.get("features", []):
                    rings = (f.get("geometry") or {}).get("rings") or []
                    if not rings:
                        continue
                    ring = rings[0]
                    lng = sum(p[0] for p in ring) / len(ring)
                    lat = sum(p[1] for p in ring) / len(ring)
                    out[str(f["attributes"]["PROP_ID"])] = (round(lat, 7), round(lng, 7))
                break
            except Exception as e:
                if attempt == 2:
                    _log(f"  geom batch {i}: giving up ({type(e).__name__})")
                else:
                    time.sleep(2 * (attempt + 1))
        if i and i % 2000 == 0:
            _log(f"  geom progress: {len(out):,}/{i + B}")
    return out


def main():
    if not TARGET_ZIPS:
        _log("ERROR: set TARGET_ZIPS (comma-separated)")
        sys.exit(2)
    want = set(TARGET_ZIPS)
    rows: dict = {z: {} for z in want}   # zip -> pin -> seed row
    n = 0
    _log(f"scanning PROP.TXT for {sorted(want)} ...")
    with zipfile.ZipFile(TCAD_ROLL) as zf:
        with zf.open("PROP.TXT") as fh:
            for raw in fh:
                n += 1
                line = raw.decode("latin-1", "ignore")
                z = fx(line, "s_zip")[:5]
                if z not in want:
                    continue
                if not fx(line, "state_cd").upper().startswith("A"):
                    continue
                pin = fx(line, "prop_id").lstrip("0") or "0"
                if pin in rows[z]:
                    continue  # multi-owner duplicate prop_id rows — keep first
                owner = fx(line, "owner")
                addr = " ".join(p for p in [fx(line, "s_num"), fx(line, "s_prefix"),
                                            fx(line, "s_street"), fx(line, "s_suffix")] if p)
                unit = fx(line, "s_unit")
                if unit:
                    addr = f"{addr} #{unit}"
                try:
                    value = int(fx(line, "market") or 0)
                except ValueError:
                    value = 0
                xfer = _parse_deed(fx(line, "deed_dt"))
                tenure = round((TODAY - xfer).days / 365.25, 1) if xfer else None
                ostate = _norm_state(fx(line, "o_state"))
                is_oos = bool(ostate and ostate in _VALID_US_STATES and ostate != "TX")
                ozip = fx(line, "o_zip")[:5]
                is_absentee = is_oos or bool(ozip and ozip != z and is_oos)
                rows[z][pin] = {
                    "owner_name": owner,
                    "last_transfer_date": xfer.isoformat() if xfer else None,
                    "tenure_years": tenure,
                    "address": addr,
                    "value": value,
                    "owner_type": classify_owner_type(owner),
                    "owner_city": fx(line, "o_city").title(),
                    "owner_state": ostate,
                    "is_out_of_state": is_oos,
                    "is_absentee": is_absentee,
                    "prop_type": "R",
                    "legal_description": fx(line, "legal")[:200],
                    "apn": pin,
                }
    _log(f"scanned {n:,} roll rows")

    os.makedirs(OUT_DIR, exist_ok=True)
    for z in sorted(want):
        parcels = rows[z]
        if not parcels:
            _log(f"{z}: NO PARCELS — skipping")
            continue
        addr_cov = sum(1 for p in parcels.values() if p["address"]) / len(parcels)
        if addr_cov < MIN_ADDRESS_COVERAGE:
            _log(f"{z}: address coverage {addr_cov:.1%} < gate — REFUSING to write")
            continue
        if FETCH_GEOM:
            cents = fetch_centroids(list(parcels.keys()))
            for pin, c in cents.items():
                if pin in parcels:
                    parcels[pin]["lat"], parcels[pin]["lng"] = c
            geom_cov = len([1 for p in parcels.values() if p.get("lat")]) / len(parcels)
        else:
            geom_cov = 0.0
        path = os.path.join(OUT_DIR, f"tx-travis-{z}-owners.json")
        with open(path, "w") as f:
            json.dump(parcels, f)
        ot = Counter(p["owner_type"] for p in parcels.values())
        _log(f"{z}: {len(parcels):,} parcels  addr={addr_cov:.1%}  geom={geom_cov:.1%}")
        _log(f"  owner_types={dict(ot)}")
        _log(f"  absentee={sum(1 for p in parcels.values() if p['is_absentee'])}  "
             f"long_tenure(>=15y)={sum(1 for p in parcels.values() if (p['tenure_years'] or 0) >= 15):,}")


if __name__ == "__main__":
    main()
