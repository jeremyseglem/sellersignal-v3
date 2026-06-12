#!/usr/bin/env python3
"""
Collin County (TX) per-ZIP seed builder — pulls the CCAD public Parcels
FeatureServer (free, no auth, includes owner names + mailing address +
deed dates + centroids) and emits standard seed JSON.

Residential filter: propCategoryCode LIKE 'A%' (TX PTAD: A1 single family,
A2 mobile home on land, etc.). Centroids ride along, so AZ-style: no
separate geometry backfill needed.

USAGE:
  TARGET_ZIPS=75093,75034 OUT_DIR=data/seeds python3 scripts/build_collin_owners.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get(
    "CCAD_PARCELS_URL",
    "https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/rest/services/"
    "CCAD_Parcel_Feature_Set/FeatureServer/4",
)
TARGET_ZIPS = [z.strip() for z in os.environ.get("TARGET_ZIPS", "").split(",") if z.strip()]
OUT_DIR = Path(os.environ.get("OUT_DIR", "data/seeds"))
PAGE = 2000
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Collin-Seed/1.0"}

OUT_FIELDS = ",".join([
    "propID", "ownerName", "situsConcatShort", "situsCity", "situsZip",
    "currValMarket", "deedEffDate", "deedFileDate", "propCategoryCode",
    "legalDescription", "ownerAddrCity", "ownerAddrState", "ownerAddrZip",
])

ENTITY_RE = re.compile(
    r"\b(LLC|L L C|INC|CORP|LTD|LP|L P|COMPANY|PARTNERS(HIP)?|HOLDINGS|"
    r"PROPERTIES|INVESTMENTS?|VENTURES|GROUP|BANK|CHURCH|CITY OF|COUNTY|"
    r"ISD|HOA|ASSOC|ASSN|FOUNDATION|FUND)\b", re.I)
TRUST_RE = re.compile(r"\b(TRUST|TR\b|TRUSTEE|LIVING TR|REV(OCABLE)? TR|FAMILY TR)\b", re.I)


def classify_owner(name: str) -> str:
    u = (name or "").upper()
    if TRUST_RE.search(u):
        return "trust"
    if re.search(r"\bLLC\b", u):
        return "llc"
    if ENTITY_RE.search(u):
        return "company"
    return "individual"


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


def build_zip(z: str) -> None:
    where = f"situsZip = '{z}' AND propCategoryCode LIKE 'A%'"
    out: dict = {}
    offset = 0
    now = datetime.now(timezone.utc)
    while True:
        d = gj({"where": where, "outFields": OUT_FIELDS, "returnGeometry": "true",
                "returnCentroid": "true", "outSR": "4326",
                "resultOffset": str(offset), "resultRecordCount": str(PAGE),
                "orderByFields": "propID", "f": "json"})
        feats = d.get("features", [])
        if not feats:
            break
        for f in feats:
            a = f.get("attributes") or {}
            pin = str(a.get("propID") or "").strip()
            owner = (a.get("ownerName") or "").strip()
            if not pin or not owner:
                continue
            deed_ms = a.get("deedEffDate") or a.get("deedFileDate")
            ltd, tenure = None, None
            if deed_ms:
                try:
                    dt = datetime.fromtimestamp(deed_ms / 1000, tz=timezone.utc)
                    ltd = dt.strftime("%Y-%m-%d")
                    tenure = round((now - dt).days / 365.25, 1)
                except Exception:
                    pass
            o_state = (a.get("ownerAddrState") or "").strip().upper()
            oos = bool(o_state) and len(o_state) == 2 and o_state.isalpha() and o_state != "TX"
            # absentee: out-of-state OR mailing city differs from situs city
            o_city = (a.get("ownerAddrCity") or "").strip()
            s_city = (a.get("situsCity") or "").strip()
            absentee = oos or (bool(o_city) and bool(s_city)
                               and o_city.upper() != s_city.upper())
            c = f.get("centroid") or {}
            rec = {
                "owner_name": owner,
                "last_transfer_date": ltd,
                "tenure_years": tenure,
                "address": (a.get("situsConcatShort") or "").strip(),
                "value": int(a.get("currValMarket") or 0),
                "owner_type": classify_owner(owner),
                "owner_city": o_city,
                "owner_state": o_state or "TX",
                "is_out_of_state": oos,
                "is_absentee": absentee,
                "prop_type": "R",
                "legal_description": (a.get("legalDescription") or "")[:250],
                "apn": pin,
            }
            if c.get("y") is not None and c.get("x") is not None:
                rec["lat"] = round(c["y"], 7)
                rec["lng"] = round(c["x"], 7)
            out[pin] = rec
        offset += len(feats)
        if len(feats) < PAGE:
            break
    addr_pct = 100 * sum(1 for r in out.values() if r["address"]) / max(len(out), 1)
    geom_pct = 100 * sum(1 for r in out.values() if "lat" in r) / max(len(out), 1)
    if addr_pct < 80:
        print(f"{z}: REFUSING to write — address coverage {addr_pct:.0f}% < 80%", file=sys.stderr)
        sys.exit(1)
    path = OUT_DIR / f"tx-collin-{z}-owners.json"
    json.dump(out, open(path, "w"))
    from collections import Counter
    ot = Counter(r["owner_type"] for r in out.values())
    print(f"{z}: {len(out):,} parcels  addr={addr_pct:.1f}%  geom={geom_pct:.1f}%")
    print(f"  owner_types={dict(ot)}")
    print(f"  absentee={sum(1 for r in out.values() if r['is_absentee']):,}  "
          f"long_tenure(>=15y)={sum(1 for r in out.values() if (r['tenure_years'] or 0) >= 15):,}")


if __name__ == "__main__":
    if not TARGET_ZIPS:
        print("Set TARGET_ZIPS=75093,75034,...", file=sys.stderr)
        sys.exit(2)
    for z in TARGET_ZIPS:
        build_zip(z)
