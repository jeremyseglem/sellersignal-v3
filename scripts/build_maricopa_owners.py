#!/usr/bin/env python3
"""
Build az-maricopa-{ZIP}-owners.json from the Maricopa County Assessor's
Parcels map service.

Canonical seed-file builder for adding a Maricopa County (AZ) ZIP to
SellerSignal. Mirrors scripts/build_snohomish_owners.py and
scripts/build_kc_owners.py — SAME output JSON shape, SAME owner-type
classifier, SAME address-coverage gate. The orchestrator at
backend/tasks/zip_onboarding.py reads the file this produces as its
`seed` step.

────────────────────────────────────────────────────────────────────────
DATA SOURCE — Maricopa County Assessor, Parcels map service (verified
2026-06-06 against the live endpoint)
────────────────────────────────────────────────────────────────────────
  REST endpoint:
    https://gis.mcassessor.maricopa.gov/arcgis/rest/services/
      Parcels/MapServer/0/query

  Unlike KC (RPSale+RPAcct split) and Snohomish (no inline tenure), the
  Maricopa Parcels layer carries EVERYTHING we need in one layer:

    seed field            Maricopa Parcels/0 field
    ──────────────────    ──────────────────────────────────────────
    pin                   APN_DASH        (e.g. "167-42-185")
    owner_name            OWNER_NAME      (owner of record, not last buyer)
    address               PHYSICAL_STREET_* components (composed)
    (situs zip filter)    PHYSICAL_ZIP
    value                 FCV_CUR         (Full Cash Value; string w/ commas)
    last_transfer_date    SALE_DATE       (when populated)
    sale_price            SALE_PRICE      (when populated)
    owner_type            classify_owner_type(OWNER_NAME)

  Also inline (NOT consumed by this builder, but available downstream so
  Maricopa needs NO separate geometry backfill or property-detail reingest):
    LONGITUDE / LATITUDE  — geometry as columns (SR 102100 / Web Mercator
                            on the layer, but lat/lng exposed in WGS84)
    MAIL_STATE / MAIL_ZIP — absentee detection (mail vs PHYSICAL)
    PUC / LC_CUR          — property-use code + legal class (prop_type
                            eligibility). NB: the matcher's prop_type
                            filter MUST get an AZ_MARICOPA market-aware
                            default in _load_owners_db — same lesson as
                            Snohomish (May 21): PUC codes are 4-digit
                            ("0131"=SFR), NOT KC's R/K, so an unguarded
                            filter rejects every parcel.

────────────────────────────────────────────────────────────────────────
TENURE
────────────────────────────────────────────────────────────────────────
SALE_DATE / SALE_PRICE are present on the layer but sparsely populated.
This builder parses them WHEN present (computing tenure_years) and writes
null otherwise — the classify/band steps route null-tenure parcels to the
"unknown_tenure" archetype (Build Now), same as KC/Snohomish.

────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────
  TARGET_ZIP=85254 python3 scripts/build_maricopa_owners.py
  # Output: data/seeds/az-maricopa-{ZIP}-owners.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_ZIP = os.environ.get("TARGET_ZIP", "").strip()
if not TARGET_ZIP:
    print("ERROR: set TARGET_ZIP env var (e.g. TARGET_ZIP=85254)", file=sys.stderr)
    sys.exit(2)
if not (TARGET_ZIP.isdigit() and len(TARGET_ZIP) == 5):
    print(f"ERROR: TARGET_ZIP must be a 5-digit ZIP, got {TARGET_ZIP!r}", file=sys.stderr)
    sys.exit(2)

PARCELS_URL = os.environ.get(
    "PARCELS_URL",
    "https://gis.mcassessor.maricopa.gov/arcgis/rest/services/"
    "Parcels/MapServer/0",
)
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "1000"))   # Maricopa maxRecordCount
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "60"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "seeds" / f"az-maricopa-{TARGET_ZIP}-owners.json"

MIN_ADDRESS_COVERAGE = float(os.environ.get("MIN_ADDRESS_COVERAGE", "0.80"))
USER_AGENT = "SellerSignal-Maricopa-Seed-Builder/1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def classify_owner_type(name: str) -> str:
    """
    INTENTIONALLY IDENTICAL to scripts/build_snohomish_owners.py and
    scripts/build_kc_owners.py. Do not diverge per-market.
    """
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
        "DEPT OF", "DEPARTMENT OF", " USA ",
    )):
        return "company"
    return "individual"


def compose_situs_address(attrs: dict) -> str:
    """
    Compose a clean street line from the Maricopa PHYSICAL_STREET_*
    components. PHYSICAL_ADDRESS exists pre-built but bundles city+zip
    with irregular spacing (e.g. "4819 E POINSETTIA DR   SCOTTSDALE  85254"),
    so we build just the street line from parts, mirroring the Snohomish
    compose pattern. Order: num dir name type suffix postdir suite.
    """
    parts = [
        (attrs.get("PHYSICAL_STREET_NUM")     or "").strip(),
        (attrs.get("PHYSICAL_STREET_DIR")     or "").strip(),
        (attrs.get("PHYSICAL_STREET_NAME")    or "").strip(),
        (attrs.get("PHYSICAL_STREET_TYPE")    or "").strip(),
        (attrs.get("PHYSICAL_STREET_SUFFIX")  or "").strip(),
        (attrs.get("PHYSICAL_STREET_POSTDIR") or "").strip(),
        (attrs.get("PHYSICAL_SUITE")          or "").strip(),
    ]
    line = " ".join(p for p in parts if p)
    if line:
        return line
    # Fallback: strip city/zip tail off the bundled PHYSICAL_ADDRESS.
    bundled = (attrs.get("PHYSICAL_ADDRESS") or "").strip()
    if bundled:
        # Street portion is everything before the run of 3+ spaces that
        # precedes the city name in the bundled string.
        return bundled.split("   ")[0].strip()
    return ""


def parse_value(raw) -> int:
    """FCV_CUR comes as a right-justified string with commas: '   611,200'."""
    if raw is None:
        return 0
    s = str(raw).replace(",", "").strip()
    if not s or not s.lstrip("-").isdigit():
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


def parse_sale(attrs: dict) -> tuple[str | None, str, float | None]:
    """
    Return (last_transfer_date_iso_or_None, sale_price_str, tenure_years_or_None).
    SALE_DATE/SALE_PRICE are sparsely populated strings; parse defensively.
    """
    raw_date = (attrs.get("SALE_DATE") or "").strip()
    raw_price = (attrs.get("SALE_PRICE") or "").strip().replace(",", "")
    sale_price = raw_price if raw_price.isdigit() else "0"

    iso_date: str | None = None
    tenure: float | None = None
    if raw_date:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%Y%m%d"):
            try:
                dt = datetime.strptime(raw_date, fmt)
                iso_date = dt.strftime("%Y-%m-%d")
                tenure = round((datetime.now() - dt).days / 365.25, 1)
                break
            except ValueError:
                continue
    return iso_date, sale_price, tenure


def http_get_json(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_exc = e
            _log(f"  http attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"http failed after {MAX_RETRIES} attempts: {last_exc}")


# ── 1. Fetch all parcels for TARGET_ZIP ───────────────────────────────────────

OUT_FIELDS = ",".join([
    "APN_DASH", "OWNER_NAME",
    "PHYSICAL_STREET_NUM", "PHYSICAL_STREET_DIR", "PHYSICAL_STREET_NAME",
    "PHYSICAL_STREET_TYPE", "PHYSICAL_STREET_SUFFIX", "PHYSICAL_STREET_POSTDIR",
    "PHYSICAL_SUITE", "PHYSICAL_ADDRESS", "PHYSICAL_ZIP",
    "MAIL_CITY", "MAIL_STATE", "MAIL_ZIP",
    "FCV_CUR", "SALE_DATE", "SALE_PRICE",
    "PUC", "LC_CUR", "CONST_YEAR",
])
WHERE = f"PHYSICAL_ZIP='{TARGET_ZIP}'"

_log(f"fetching parcels for ZIP {TARGET_ZIP} from Maricopa Parcels MapServer...")

count_resp = http_get_json(f"{PARCELS_URL}/query", {
    "where": WHERE, "returnCountOnly": "true", "f": "json",
})
total_count = count_resp.get("count", 0)
_log(f"  service reports {total_count:,} parcels for ZIP {TARGET_ZIP}")
if total_count == 0:
    print(f"ERROR: no parcels for ZIP {TARGET_ZIP}. Confirm PHYSICAL_ZIP filter "
          f"and that PARCELS_URL is current.", file=sys.stderr)
    sys.exit(1)

all_features: list[dict] = []
offset = 0
page_no = 0
while True:
    page_no += 1
    resp = http_get_json(f"{PARCELS_URL}/query", {
        "where": WHERE,
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "orderByFields": "APN_DASH",
        "f": "json",
    })
    feats = resp.get("features", [])
    if not feats:
        break
    all_features.extend(feats)
    _log(f"  page {page_no}: +{len(feats):,} (cumulative {len(all_features):,}/{total_count:,})")
    if len(feats) < PAGE_SIZE:
        break
    offset += PAGE_SIZE
    if len(all_features) > total_count * 1.1:
        print(f"ERROR: fetched {len(all_features):,} > reported {total_count:,} — "
              f"pagination drift. Inspect resultOffset behavior.", file=sys.stderr)
        sys.exit(1)

_log(f"  fetched {len(all_features):,} total parcel records")


# ── 2. Map to seed JSON shape ─────────────────────────────────────────────────

out: dict[str, dict] = {}
skipped_no_pin = 0
sale_date_present = 0
for feat in all_features:
    attrs = feat.get("attributes", {}) or {}
    pin = (attrs.get("APN_DASH") or "").strip()
    if not pin:
        skipped_no_pin += 1
        continue
    owner_name = (attrs.get("OWNER_NAME") or "").strip()
    address = compose_situs_address(attrs)
    value = parse_value(attrs.get("FCV_CUR"))
    last_transfer_date, sale_price, tenure_years = parse_sale(attrs)
    if last_transfer_date:
        sale_date_present += 1

    out[pin] = {
        "owner_name":         owner_name,
        "last_transfer_date": last_transfer_date,
        "tenure_years":       tenure_years,
        "sale_price":         sale_price,
        "address":            address,
        "value":              value,
        "owner_type":         classify_owner_type(owner_name),
    }

if skipped_no_pin:
    _log(f"  skipped {skipped_no_pin:,} rows with empty APN_DASH")
_log(f"  mapped {len(out):,} parcels into seed shape")


# ── 3. Address-coverage gate ──────────────────────────────────────────────────

with_address = sum(1 for v in out.values() if (v.get("address") or "").strip())
coverage = with_address / len(out) if out else 0.0
_log(f"address coverage: {with_address:,}/{len(out):,} = {coverage:.1%}")
if coverage < MIN_ADDRESS_COVERAGE:
    print(f"\nERROR: address coverage {coverage:.1%} below minimum "
          f"({MIN_ADDRESS_COVERAGE:.0%}) — refusing to write a broken seed "
          f"file (the May 10 bug shape). Inspect a sample row via "
          f"/query?outFields=* before re-running.", file=sys.stderr)
    sys.exit(1)


# ── 4. Write seed file ────────────────────────────────────────────────────────

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
_log(f"wrote {OUT_PATH}")


# ── 5. Summary stats (+ price×velocity×SFH signal for ZIP-formula review) ─────

type_dist = Counter(v["owner_type"] for v in out.values())
no_owner = sum(1 for v in out.values() if not (v.get("owner_name") or "").strip())
values = sorted(v["value"] for v in out.values() if v["value"] > 0)
median_val = values[len(values) // 2] if values else 0

# SFH / prop-type signal: report PUC + legal-class distribution from the raw
# features (PUC not stored in the seed; needed to build the AZ_MARICOPA
# PUC→prop_type map and to confirm SFH dominance for the ZIP-selection formula).
puc_dist = Counter((f.get("attributes", {}).get("PUC") or "").strip()
                   for f in all_features)
lc_dist = Counter(((f.get("attributes", {}).get("LC_CUR") or "").strip() or "?")[:1]
                  for f in all_features)
sfr_0131 = puc_dist.get("0131", 0)

print()
print(f"  ZIP:                 {TARGET_ZIP}")
print(f"  Total PINs:          {len(out):,}")
print(f"  Address coverage:    {coverage:.1%}")
print(f"  Parcels with owner:  {len(out) - no_owner:,}")
print(f"  Median value (FCV):  ${median_val:,}")
print(f"  Owner-type dist:     " + ", ".join(f"{t}={n:,}" for t, n in type_dist.most_common()))
print(f"  Sale-date present:   {sale_date_present:,}/{len(out):,} ({sale_date_present/len(out):.1%}) [tenure/velocity]")
print(f"  PUC 0131 (SFR):      {sfr_0131:,} ({sfr_0131/len(all_features):.1%})")
print(f"  Top PUC codes:       " + ", ".join(f"{c or '(blank)'}={n:,}" for c, n in puc_dist.most_common(8)))
print(f"  Legal-class first:   " + ", ".join(f"{c}={n:,}" for c, n in lc_dist.most_common()))
print(f"  Output:              {OUT_PATH}")
