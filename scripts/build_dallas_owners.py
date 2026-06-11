#!/usr/bin/env python3
"""
Dallas County (TX) seed builder — produces data/seeds/tx-dallas-{zip}-owners.json
for the onboarding orchestrator's `seed` step (owner_name, address,
tenure_years, value, owner_type, plus owner_state/city/zip + absentee flags +
prop_type so the absentee bucket populates without a later reingest).

SOURCE: DCAD bulk "Data Products" ZIP (free, comma-delimited, refreshed weekly):
  https://www.dallascad.org/dataproducts.aspx -> DCAD{YEAR}_CURRENT.ZIP
Two files, joined on ACCOUNT_NUM:
  ACCOUNT_INFO.CSV        owner names, property address, owner mailing address,
                          DEED_TXFR_DATE (tenure), LEGAL1-5, GIS_PARCEL_ID,
                          DIVISION_CD (RES/COM/BPP), PROPERTY_ZIPCODE
  ACCOUNT_APPRL_YEAR.CSV  TOT_VAL / IMPR_VAL / LAND_VAL (banding)

Texas is a NON-DISCLOSURE state — no sale prices. `value` is the APPRAISED
TOT_VAL (the band model uses appraised value for TX markets); tenure comes from
DEED_TXFR_DATE. There is no sale_price field.

USAGE:
  TARGET_ZIP=75205 DCAD_DIR=/tmp/dcad python3 scripts/build_dallas_owners.py
  (DCAD_DIR holds the unzipped CSVs, OR set DCAD_ZIP=/path/to/DCAD2026_CURRENT.ZIP
   to stream the two needed CSVs directly out of the zip.)

Mirrors build_kc_owners.py: same classify_owner_type, same 80% address-coverage
gate, same output schema keyed by parcel id.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import zipfile
from collections import Counter
from datetime import date, datetime

csv.field_size_limit(10_000_000)

TARGET_ZIP = os.environ.get("TARGET_ZIP", "").strip()
DCAD_DIR = os.environ.get("DCAD_DIR", "/tmp/dcad")
DCAD_ZIP = os.environ.get("DCAD_ZIP", "")
OUT_DIR = os.environ.get("OUT_DIR", "data/seeds")
MIN_ADDRESS_COVERAGE = float(os.environ.get("MIN_ADDRESS_COVERAGE", "0.80"))
TODAY = date.today()
_VALID_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}
_STATE_FULL = {"TEXAS": "TX", "CALIFORNIA": "CA", "FLORIDA": "FL", "NEW YORK": "NY",
               "OKLAHOMA": "OK", "LOUISIANA": "LA", "ARKANSAS": "AR", "COLORADO": "CO",
               "ARIZONA": "AZ", "NEW MEXICO": "NM"}


def _log(m): print(m, file=sys.stderr)


def classify_owner_type(name: str) -> str:
    """Identical taxonomy to build_kc_owners.classify_owner_type."""
    n = (name or "").upper()
    if not n:
        return "unknown"
    if any(t in n for t in ("TRUST", " TR ", "TRUSTEE", "REV TR", "LIVING TR")):
        return "trust"
    if any(t in n for t in (" LLC", " L L C", "LIMITED LIABILITY")):
        return "llc"
    if any(t in n for t in (
        " INC", " CORP", " LP", " LLP", " LTD", " COMPANY",
        " HOLDINGS", " PROPERTIES", " INVESTMENTS", " PARTNERS",
        " GROUP", "INVESTMENT", "DEVELOPMENT", "ENTERPRISES",
        "REALTY", "CHURCH", "MINISTRY", "FOUNDATION",
        "ASSOCIATION", "CITY OF", "HOUSING AUTHORITY",
        "STATE OF", "UNITED STATES", "COUNTY OF",
        "DEPT OF", "DEPARTMENT OF",
    )):
        return "company"
    return "individual"


def _norm_state(raw: str) -> str:
    s = (raw or "").strip().upper()
    if s in _VALID_US_STATES:
        return s
    return _STATE_FULL.get(s, s[:2] if len(s) >= 2 else "")


def _parse_date(s: str):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _open_csv(name: str):
    """Yield rows from a DCAD CSV, from the unzipped dir or directly from the zip."""
    if DCAD_ZIP:
        zf = zipfile.ZipFile(DCAD_ZIP)
        f = zf.open(name)
        import io
        return csv.reader(io.TextIOWrapper(f, encoding="latin-1", newline=""))
    path = os.path.join(DCAD_DIR, name)
    return csv.reader(open(path, encoding="latin-1", newline=""))


def main():
    if not TARGET_ZIP:
        _log("ERROR: set TARGET_ZIP"); sys.exit(2)

    # ── 1. ACCOUNT_INFO: collect residential parcels in the target ZIP ──────
    info = {}  # account_num -> dict
    r = _open_csv("ACCOUNT_INFO.CSV")
    hdr = next(r); ix = {h: i for i, h in enumerate(hdr)}
    for row in r:
        if len(row) < len(hdr):
            continue
        if row[ix["DIVISION_CD"]].strip() != "RES":
            continue
        z = (row[ix["PROPERTY_ZIPCODE"]] or "").strip()[:5]
        if z != TARGET_ZIP:
            continue
        acct = row[ix["ACCOUNT_NUM"]].strip()
        owner = (row[ix["OWNER_NAME1"]] or "").strip()
        name2 = (row[ix["OWNER_NAME2"]] or "").strip()
        if name2:
            owner = f"{owner} & {name2}" if owner else name2
        snum = (row[ix["STREET_NUM"]] or "").strip()
        sname = (row[ix["FULL_STREET_NAME"]] or "").strip()
        unit = (row[ix["UNIT_ID"]] or "").strip()
        addr = " ".join(p for p in [snum, sname] if p).strip()
        if unit:
            addr = f"{addr} #{unit}"
        legal = " ".join((row[ix[f"LEGAL{i}"]] or "").strip() for i in range(1, 6)).strip()
        ostate = _norm_state(row[ix["OWNER_STATE"]])
        ocity = (row[ix["OWNER_CITY"]] or "").strip().title()
        ozip = (row[ix["OWNER_ZIPCODE"]] or "").strip()[:5]
        info[acct] = {
            "owner_name": owner,
            "address": addr,
            "legal_description": legal,
            "last_transfer_date": (_parse_date(row[ix["DEED_TXFR_DATE"]]).isoformat()
                                   if _parse_date(row[ix["DEED_TXFR_DATE"]]) else None),
            "apn": (row[ix["GIS_PARCEL_ID"]] or "").strip(),
            "owner_city": ocity,
            "owner_state": ostate,
            "owner_zip": ozip,
        }
    _log(f"ACCOUNT_INFO: {len(info):,} residential parcels in {TARGET_ZIP}")
    if not info:
        _log("ERROR: no parcels — wrong ZIP or DIVISION filter?"); sys.exit(1)

    # ── 2. ACCOUNT_APPRL_YEAR: join TOT_VAL ─────────────────────────────────
    r = _open_csv("ACCOUNT_APPRL_YEAR.CSV")
    hdr = next(r); ix = {h: i for i, h in enumerate(hdr)}
    for row in r:
        if len(row) < len(hdr):
            continue
        acct = row[ix["ACCOUNT_NUM"]].strip()
        if acct in info:
            try:
                info[acct]["value"] = int(float(row[ix["TOT_VAL"]]))
            except (ValueError, KeyError):
                info[acct]["value"] = 0

    # ── 3. assemble output ──────────────────────────────────────────────────
    out = {}
    for acct, p in info.items():
        owner = p["owner_name"]
        xfer = _parse_date(p["last_transfer_date"]) if p["last_transfer_date"] else None
        tenure = round((TODAY - xfer).days / 365.25, 1) if xfer else None
        ostate = p["owner_state"]
        is_oos = bool(ostate and ostate in _VALID_US_STATES and ostate != "TX")
        # absentee: owner mailing city differs from property city/zip
        is_absentee = bool(ostate and ostate != "TX") or (
            p["owner_zip"] and p["owner_zip"] != TARGET_ZIP and is_oos)
        out[acct] = {
            "owner_name": owner,
            "last_transfer_date": p["last_transfer_date"],
            "tenure_years": tenure,
            "address": p["address"],
            "value": p.get("value", 0),
            "owner_type": classify_owner_type(owner),
            "owner_city": p["owner_city"],
            "owner_state": ostate,
            "is_out_of_state": is_oos,
            "is_absentee": is_absentee,
            "prop_type": "R",
            "legal_description": p["legal_description"],
            "apn": p["apn"],
        }

    # ── 4. address-coverage gate (May-10 bug guard) ─────────────────────────
    with_addr = sum(1 for v in out.values() if (v.get("address") or "").strip())
    cov = with_addr / len(out) if out else 0.0
    _log(f"address coverage: {with_addr:,}/{len(out):,} = {cov:.1%}")
    if cov < MIN_ADDRESS_COVERAGE:
        _log(f"ERROR: address coverage {cov:.1%} below {MIN_ADDRESS_COVERAGE:.0%} — aborting.")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"tx-dallas-{TARGET_ZIP}-owners.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    types = Counter(v["owner_type"] for v in out.values())
    tenures = [v["tenure_years"] for v in out.values() if v["tenure_years"] is not None]
    vals = sorted(v["value"] for v in out.values() if v["value"])
    med = vals[len(vals)//2] if vals else 0
    _log(f"WROTE {out_path}")
    _log(f"  parcels={len(out):,}  median_value=${med:,}")
    _log(f"  owner_types={dict(types)}")
    _log(f"  absentee={sum(1 for v in out.values() if v['is_absentee']):,}  "
         f"oos={sum(1 for v in out.values() if v['is_out_of_state']):,}")
    _log(f"  long_tenure(>=15y)={sum(1 for t in tenures if t >= 15):,}")


if __name__ == "__main__":
    main()
