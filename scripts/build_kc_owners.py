#!/usr/bin/env python3
"""
Build wa-king-{ZIP}-owners.json from King County bulk assessor data.

This is the canonical seed-file builder for adding a new King County
ZIP to SellerSignal. The orchestrator at
backend/tasks/zip_onboarding.py reads the file this script produces as
its `seed` step, which is what populates owner_name, address,
tenure_years, sale_price, value, and owner_type in parcels_v3.

────────────────────────────────────────────────────────────────────────
HISTORY / WHY THIS SCRIPT EXISTS IN THE REPO
────────────────────────────────────────────────────────────────────────
The 21 currently-live KC ZIPs were each seeded from a wa-king-{zip}-
owners.json file. The script that GENERATED those files was never
committed — it lived in an ephemeral container and was rewritten ad-hoc
for each batch. A bug in one of those ad-hoc rewrites (May 10, 2026)
produced six seed files with 0% address coverage; the bug was patched
in production by re-running ArcGIS ingest on top of the bad seeds, but
the seed files themselves were never regenerated. Anyone re-onboarding
those ZIPs from the repo would re-create the original bug.

This script is the committed, tested replacement. It includes an
address-coverage self-check at the end and exits non-zero if coverage
falls below the threshold for the ZIP — making the May 10 bug shape
impossible to ship silently.

────────────────────────────────────────────────────────────────────────
DATA SOURCES — public KC bulk assessor downloads
────────────────────────────────────────────────────────────────────────
  EXTR_RPSale.csv          — sales history (sellers, buyers, dates, prices)
    URL: https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip
    Size: ~150 MB zipped, ~600 MB extracted
    Columns used: Major, Minor, DocumentDate, SalePrice, BuyerName

  EXTR_RPAcct_NoName.csv   — parcel accounts (addresses, valuations)
    URL: https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Account.zip
    Size: ~19 MB zipped, ~117 MB extracted
    Columns used: Major, Minor, AddrLine, ZipCode, ApprLandVal, ApprImpsVal

Both files are public and updated roughly weekly. Owner names live in
RPSale (BuyerName on the most recent sale), NOT in RPAcct — King County
strips owner names from the RPAcct bulk download per RCW 42.56.070(8).

────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────
  # One-time prep: download and extract both CSVs into a working dir.
  mkdir -p /tmp/kc-data && cd /tmp/kc-data
  curl -sL -A "Mozilla/5.0" \\
    "https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip" \\
    -o RPSale.zip
  curl -sL -A "Mozilla/5.0" \\
    "https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Account.zip" \\
    -o RPAcct.zip
  unzip -o RPSale.zip
  unzip -o RPAcct.zip

  # Build a single ZIP:
  TARGET_ZIP=98034 KC_DATA=/tmp/kc-data python3 scripts/build_kc_owners.py

  # Build multiple ZIPs:
  for zip in 98034 98115 98117 98029 98053; do
    TARGET_ZIP=$zip KC_DATA=/tmp/kc-data \\
      python3 scripts/build_kc_owners.py || exit 1
  done

  # Output is written to data/seeds/wa-king-{ZIP}-owners.json.

────────────────────────────────────────────────────────────────────────
DOWNSTREAM PIPELINE
────────────────────────────────────────────────────────────────────────
After this script writes the seed file, commit it, deploy, and call:
  POST /api/admin/onboard-zip/{zip}
The orchestrator then runs register → seed → canonicalize → classify →
band → refresh_counts. See backend/tasks/zip_onboarding.py.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_ZIP = os.environ.get("TARGET_ZIP", "").strip()
if not TARGET_ZIP:
    print("ERROR: set TARGET_ZIP env var (e.g. TARGET_ZIP=98034)", file=sys.stderr)
    sys.exit(2)
if not (TARGET_ZIP.isdigit() and len(TARGET_ZIP) == 5):
    print(f"ERROR: TARGET_ZIP must be a 5-digit ZIP, got {TARGET_ZIP!r}", file=sys.stderr)
    sys.exit(2)

KC_DATA = Path(os.environ.get("KC_DATA", "/tmp/kc-data"))
RPACCT_CSV = KC_DATA / "EXTR_RPAcct_NoName.csv"
RPSALE_CSV = KC_DATA / "EXTR_RPSale.csv"

# Repo root is one parent up from this file (scripts/ -> repo).
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "seeds" / f"wa-king-{TARGET_ZIP}-owners.json"

# Address-coverage gate: refuse to write the seed file if too few
# parcels have addresses. This is the May 10 bug guard — the broken
# May 10 seeds had 0% address coverage; the canonical ZIPs have 95–100%.
# Condo-heavy areas (Queen Anne 98119) bottom out around 82%. The gate
# is intentionally generous to allow condo-heavy ZIPs while still
# blocking outright failures.
MIN_ADDRESS_COVERAGE = float(os.environ.get("MIN_ADDRESS_COVERAGE", "0.80"))

# Today, used to compute tenure_years.
TODAY = date.today()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def classify_owner_type(name: str) -> str:
    """
    Categorize an owner name into one of:
      individual / trust / llc / company / unknown

    Matches the classifier used by the original 98103 / 98136 / 98038
    build scripts that produced the 21 working seed files. Pattern
    list intentionally identical to the historical version — any
    change here would silently shift archetype assignments downstream.
    """
    n = (name or "").upper()
    if not n:
        return "unknown"
    if any(t in n for t in (
        "TRUST", " TR ", "TRUSTEE", "REV TR", "LIVING TR",
    )):
        return "trust"
    if any(t in n for t in (
        " LLC", " L L C", "LIMITED LIABILITY",
    )):
        return "llc"
    if any(t in n for t in (
        " INC", " CORP", " LP", " LLP", " LTD", " COMPANY",
        " HOLDINGS", " PROPERTIES", " INVESTMENTS", " PARTNERS",
        " GROUP", "INVESTMENT", "DEVELOPMENT", "ENTERPRISES",
        "REALTY", "CHURCH", "MINISTRY", "FOUNDATION",
        "ASSOCIATION", "CITY OF", "HOUSING AUTHORITY",
        "STATE OF", "UNITED STATES", "COUNTY OF",
        "DEPT OF", "DEPARTMENT OF", " USA ",
    )):
        return "company"
    return "individual"


def _pin(major: str, minor: str) -> str:
    """
    KC PIN convention: 6-digit Major + 4-digit Minor, zero-padded, no
    separator. Matches the 10-char PIN format used everywhere in
    parcels_v3 / raw_signal_matches_v3 / case_parties_v3.
    """
    return f"{major.strip().zfill(6)}{minor.strip().zfill(4)}"


def _parse_int(s: str) -> int:
    s = (s or "").strip()
    try:
        return int(s) if s else 0
    except ValueError:
        return 0


def _parse_date(s: str) -> date | None:
    """RPSale DocumentDate is MM/DD/YYYY (verified across multiple years)."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Validate inputs exist ─────────────────────────────────────────────────────

for p in (RPACCT_CSV, RPSALE_CSV):
    if not p.exists():
        print(
            f"ERROR: required CSV not found: {p}\n"
            f"Set KC_DATA to the directory containing the extracted "
            f"EXTR_RPAcct_NoName.csv and EXTR_RPSale.csv files, or "
            f"download/extract them per the module docstring.",
            file=sys.stderr,
        )
        sys.exit(2)


# ── 1. Load parcels for TARGET_ZIP from RPAcct ────────────────────────────────

_log(f"loading parcels for ZIP {TARGET_ZIP} from RPAcct...")
parcels: dict[str, dict] = {}  # PIN -> {major, minor, address, value}
with open(RPACCT_CSV, encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    for row in reader:
        # RPAcct ZipCode field sometimes has '98103-1234' or '98103   '
        zc = (row.get("ZipCode") or "").strip()
        if not zc.startswith(TARGET_ZIP):
            continue
        major = (row.get("Major") or "").strip()
        minor = (row.get("Minor") or "").strip()
        if not major or not minor:
            continue
        pin = _pin(major, minor)
        addr = (row.get("AddrLine") or "").strip()
        appr_land = _parse_int(row.get("ApprLandVal", ""))
        appr_imps = _parse_int(row.get("ApprImpsVal", ""))
        parcels[pin] = {
            "major":   major,
            "minor":   minor,
            "address": addr,
            "value":   appr_land + appr_imps,
        }

_log(f"  loaded {len(parcels):,} parcels for ZIP {TARGET_ZIP}")
if not parcels:
    print(f"ERROR: no parcels found for ZIP {TARGET_ZIP}. "
          f"Check ZipCode field in RPAcct or confirm the ZIP exists in KC.",
          file=sys.stderr)
    sys.exit(1)

# Index parcels by (Major, Minor) for the RPSale join.
key_set = {(p["major"], p["minor"]) for p in parcels.values()}


# ── 2. Find most-recent sale per (Major, Minor) from RPSale ───────────────────

_log("scanning RPSale for latest sale per parcel...")
latest_sale: dict[tuple[str, str], dict] = {}
n_scanned = 0
with open(RPSALE_CSV, encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    for row in reader:
        n_scanned += 1
        if n_scanned % 500_000 == 0:
            _log(f"  scanned {n_scanned:,} sale rows...")
        major = (row.get("Major") or "").strip()
        minor = (row.get("Minor") or "").strip()
        if (major, minor) not in key_set:
            continue
        d = _parse_date(row.get("DocumentDate", ""))
        if not d:
            continue
        prev = latest_sale.get((major, minor))
        if prev and prev["date"] >= d:
            continue
        latest_sale[(major, minor)] = {
            "date":  d,
            "buyer": (row.get("BuyerName") or "").strip(),
            "price": (row.get("SalePrice") or "0").strip() or "0",
        }
_log(f"  matched {len(latest_sale):,} of {len(parcels):,} parcels to a sale "
     f"({100*len(latest_sale)//max(1,len(parcels))}%)")


# ── 3. Build the output JSON ──────────────────────────────────────────────────

out: dict[str, dict] = {}
no_sale_count = 0
for pin, p in parcels.items():
    sale = latest_sale.get((p["major"], p["minor"]))
    if sale:
        owner_name = sale["buyer"]
        last_xfer  = sale["date"].isoformat()
        tenure     = round((TODAY - sale["date"]).days / 365.25, 1)
        price_str  = sale["price"]
    else:
        # Parcel exists in RPAcct but no sale record found — preserve
        # the parcel but mark unknown. Downstream classify routes these
        # to "unknown" archetype, which is correct.
        owner_name = ""
        last_xfer  = None
        tenure     = None
        price_str  = "0"
        no_sale_count += 1
    out[pin] = {
        "owner_name":         owner_name,
        "last_transfer_date": last_xfer,
        "tenure_years":       tenure,
        "sale_price":         price_str,
        "address":            p["address"],
        "value":              p["value"],
        "owner_type":         classify_owner_type(owner_name),
    }


# ── 4. Self-check: address coverage must clear the floor ──────────────────────

with_address = sum(1 for v in out.values() if (v.get("address") or "").strip())
coverage = with_address / len(out) if out else 0.0
_log(f"address coverage: {with_address:,}/{len(out):,} = {coverage:.1%}")

if coverage < MIN_ADDRESS_COVERAGE:
    print(
        f"\nERROR: address coverage {coverage:.1%} is below the minimum "
        f"({MIN_ADDRESS_COVERAGE:.0%}) for {TARGET_ZIP}. This is the "
        f"May 10 bug shape — refusing to write a broken seed file.\n"
        f"Likely causes:\n"
        f"  - AddrLine column name changed in EXTR_RPAcct_NoName.csv\n"
        f"  - ZipCode filter is matching the wrong rows\n"
        f"  - CSV encoding scrambled the address values\n"
        f"Inspect the RPAcct CSV manually before re-running.",
        file=sys.stderr,
    )
    sys.exit(1)


# ── 5. Write the seed file ────────────────────────────────────────────────────

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

_log(f"wrote {OUT_PATH}")


# ── 6. Summary stats ──────────────────────────────────────────────────────────

type_dist = Counter(v["owner_type"] for v in out.values())
tenures = [v["tenure_years"] for v in out.values() if v["tenure_years"] is not None]
long_tenure = sum(1 for t in tenures if t >= 15)
median_tenure = sorted(tenures)[len(tenures)//2] if tenures else None

print()
print(f"  ZIP:                 {TARGET_ZIP}")
print(f"  Total PINs:          {len(out):,}")
print(f"  Address coverage:    {coverage:.1%}")
print(f"  Parcels with sale:   {len(out) - no_sale_count:,}")
print(f"  Parcels w/o sale:    {no_sale_count:,}")
print(f"  Owner-type dist:     " + ", ".join(
    f"{t}={n:,}" for t, n in type_dist.most_common()
))
if median_tenure is not None:
    print(f"  Median tenure:       {median_tenure:.1f} years")
print(f"  Tenure ≥ 15 years:   {long_tenure:,}")
print(f"  Output:              {OUT_PATH}")
