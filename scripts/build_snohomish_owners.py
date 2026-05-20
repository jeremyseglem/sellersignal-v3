#!/usr/bin/env python3
"""
Build wa-snohomish-{ZIP}-owners.json from Snohomish County's Parcels
feature service.

This is the canonical seed-file builder for adding a new Snohomish
County ZIP to SellerSignal. Mirrors scripts/build_kc_owners.py — same
output JSON shape, same owner-type classifier, same address-coverage
gate. The orchestrator at backend/tasks/zip_onboarding.py reads the
file this script produces as its `seed` step.

────────────────────────────────────────────────────────────────────────
WHY THIS SCRIPT EXISTS
────────────────────────────────────────────────────────────────────────
The 98290 pilot (May 10, 2026) was built one-off without a committed
reproducer. This file is the committed, tested replacement that can
build seed files for any Snohomish ZIP and is the foundation for the
98020 / 98026 onboarding (May 19, 2026).

────────────────────────────────────────────────────────────────────────
DATA SOURCE — Snohomish County Open Data Portal, Parcels feature service
────────────────────────────────────────────────────────────────────────
  REST endpoint:
    https://services6.arcgis.com/z6WYi9VRHfgwgtyW/arcgis/rest/services/
      Parcels/FeatureServer/0

  Catalog discovery (in case the endpoint URL ever changes):
    https://snohomish-county-open-data-portal-snoco-gis.hub.arcgis.com/
      api/feed/dcat-us/1.1  ← DCAT JSON; search for dataset.title == "Parcels"

  Schema crosswalk from KC's RPSale+RPAcct split → single Snohomish
  feature service:

    KC                          Snohomish (Parcels FeatureServer/0)
    ────────────────────────    ────────────────────────────────────
    Major+Minor (zero-padded)   PARCEL_ID  (14-char, no split)
    BuyerName (from RPSale)     OWNERNAME  (joint owners on one line)
    AddrLine                    SITUSLINE1 (built address) or composed
                                from SITUSHOUSE/PREFX/STRT/TTYP/POSTD
    ZipCode                     SITUSZIP
    ApprLandVal+ApprImpsVal     MKTTL      (total market value)
    DocumentDate (RPSale)       NOT EXPOSED — see "Tenure" below
    SalePrice (RPSale)          NOT EXPOSED — see "Tenure" below

────────────────────────────────────────────────────────────────────────
TENURE / SALES — NOT POPULATED BY THIS SCRIPT
────────────────────────────────────────────────────────────────────────
Snohomish's open-data portal does not publish bulk sales history. The
existing 98290 pilot has only 20% tenure coverage (per the 5-year
Sales Excel that the SCOPI scraper handles).

Strategy: this script writes the seed file with last_transfer_date /
tenure_years / sale_price = null for every parcel. The existing
backend/tasks/snohomish_tenure_autofill.py background task then
backfills these fields from the per-parcel SCOPI portal (which has
full sales history going back decades). That task already runs in
production for 98290 and works correctly.

The orchestrator's classify and band steps handle null-tenure parcels
gracefully — they route to the "unknown_tenure" / "individual_long_
tenure_pending" archetypes which the dossier UI renders as Build Now
candidates pending SCOPI enrichment. This is the same shape as KC
parcels that haven't been canonicalized yet.

────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────
  # Build a single ZIP:
  TARGET_ZIP=98020 python3 scripts/build_snohomish_owners.py

  # Build multiple ZIPs:
  for zip in 98020 98026; do
    TARGET_ZIP=$zip python3 scripts/build_snohomish_owners.py || exit 1
  done

  # Optional override of the data source URL (in case the ArcGIS path
  # changes — re-confirm via the DCAT catalog above):
  TARGET_ZIP=98020 \\
    PARCELS_URL="https://services6.arcgis.com/.../Parcels/FeatureServer/0" \\
    python3 scripts/build_snohomish_owners.py

  # Output: data/seeds/wa-snohomish-{ZIP}-owners.json

────────────────────────────────────────────────────────────────────────
DOWNSTREAM PIPELINE
────────────────────────────────────────────────────────────────────────
After this script writes the seed file, commit it, deploy, and call:
  POST /api/admin/onboard-zip/{zip}?city=Edmonds  (or appropriate city)
The orchestrator runs the same canonical pipeline as KC. See the
MANIFESTO "Snohomish County onboarding pipeline" section for the full
list of plumbing additions (SNO_ZIP_TO_CITY map, market_key, etc.).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_ZIP = os.environ.get("TARGET_ZIP", "").strip()
if not TARGET_ZIP:
    print("ERROR: set TARGET_ZIP env var (e.g. TARGET_ZIP=98020)", file=sys.stderr)
    sys.exit(2)
if not (TARGET_ZIP.isdigit() and len(TARGET_ZIP) == 5):
    print(f"ERROR: TARGET_ZIP must be a 5-digit ZIP, got {TARGET_ZIP!r}", file=sys.stderr)
    sys.exit(2)

PARCELS_URL = os.environ.get(
    "PARCELS_URL",
    "https://services6.arcgis.com/z6WYi9VRHfgwgtyW/arcgis/rest/services/"
    "Parcels/FeatureServer/0",
)
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "2000"))  # ArcGIS max per request
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "60"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "seeds" / f"wa-snohomish-{TARGET_ZIP}-owners.json"

# Address-coverage gate — same shape as the KC builder's May 10 bug guard.
# Snohomish 98290 pilot showed 100% coverage, so 80% floor is generous.
MIN_ADDRESS_COVERAGE = float(os.environ.get("MIN_ADDRESS_COVERAGE", "0.80"))

USER_AGENT = "SellerSignal-Snohomish-Seed-Builder/1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def classify_owner_type(name: str) -> str:
    """
    Categorize an owner name into one of:
      individual / trust / llc / company / unknown

    INTENTIONALLY IDENTICAL to scripts/build_kc_owners.py.
    Same classifier, same pattern list. Any divergence here would
    shift archetype assignments between KC and Snohomish parcels for
    no good reason. If we want to evolve the classifier, do it in
    both files together.
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


def compose_situs_address(attrs: dict) -> str:
    """
    Build a situs address string from the Snohomish Parcels schema.

    The feature service exposes both a pre-built SITUSLINE1 (when
    available) AND the component fields. SITUSLINE1 is preferred
    because it matches the assessor's canonical address formatting,
    but it's occasionally blank for non-residential parcels. In those
    cases we reconstruct from the components.

    Examples:
      SITUSLINE1="13810 63RD PL SW"  → "13810 63RD PL SW"
      SITUSLINE1=""  +  SITUSHOUSE="13810" SITUSSTRT="63RD"
        SITUSTTYP="PL" SITUSPOSTD="SW"  → "13810 63RD PL SW"
    """
    line1 = (attrs.get("SITUSLINE1") or "").strip()
    if line1:
        return line1

    # Compose from parts. Order matches assessor's canonical form:
    #   {house} {direction-prefix} {street} {type} {direction-suffix} {unit}
    parts = [
        (attrs.get("SITUSHOUSE") or "").strip(),
        (attrs.get("SITUSPREFX") or "").strip(),
        (attrs.get("SITUSSTRT")  or "").strip(),
        (attrs.get("SITUSTTYP")  or "").strip(),
        (attrs.get("SITUSPOSTD") or "").strip(),
        (attrs.get("SITUSUNIT")  or "").strip(),
    ]
    return " ".join(p for p in parts if p)


def http_get_json(url: str, params: dict) -> dict:
    """
    GET an ArcGIS REST endpoint with retries on transient errors.
    Returns parsed JSON. Raises on persistent failure.
    """
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except Exception as e:
            last_exc = e
            _log(f"  http attempt {attempt}/{MAX_RETRIES} failed: "
                 f"{type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)  # 2, 4, 8 sec backoff
    raise RuntimeError(f"http failed after {MAX_RETRIES} attempts: {last_exc}")


# ── 1. Fetch all parcels for TARGET_ZIP via paginated REST query ──────────────

# All schema fields we need from the feature service. Explicitly named
# (rather than outFields=*) so a schema addition upstream can't silently
# inflate the payload size.
OUT_FIELDS = ",".join([
    "PARCEL_ID",
    "OWNERNAME",
    "TAXPRNAME",
    "SITUSLINE1", "SITUSHOUSE", "SITUSPREFX", "SITUSSTRT",
    "SITUSTTYP",  "SITUSPOSTD", "SITUSUNIT",
    "SITUSCITY",  "SITUSSTATE", "SITUSZIP",
    "OWNERLINE1", "OWNERCITY",  "OWNERSTATE", "OWNERZIP",
    "USECODE", "MKTTL", "MKIMP", "MKLND",
    "STATUS",
])

WHERE = f"SITUSZIP='{TARGET_ZIP}'"

_log(f"fetching parcels for ZIP {TARGET_ZIP} from Snohomish Parcels FeatureServer...")

# First, get a count so we know how many pages to expect.
count_resp = http_get_json(f"{PARCELS_URL}/query", {
    "where": WHERE,
    "returnCountOnly": "true",
    "f": "json",
})
total_count = count_resp.get("count", 0)
_log(f"  feature service reports {total_count:,} parcels for ZIP {TARGET_ZIP}")
if total_count == 0:
    print(
        f"ERROR: no parcels found for ZIP {TARGET_ZIP}. "
        f"Confirm the ZIP exists in Snohomish County (SITUSZIP field) "
        f"and that PARCELS_URL is current. Use the DCAT catalog to "
        f"re-resolve the feature service URL if needed.",
        file=sys.stderr,
    )
    sys.exit(1)

# Paginate using resultOffset / resultRecordCount.
all_features: list[dict] = []
offset = 0
page_no = 0
while True:
    page_no += 1
    resp = http_get_json(f"{PARCELS_URL}/query", {
        "where":              WHERE,
        "outFields":          OUT_FIELDS,
        "returnGeometry":     "false",
        "resultOffset":       str(offset),
        "resultRecordCount":  str(PAGE_SIZE),
        "orderByFields":      "PARCEL_ID",  # stable page ordering
        "f":                  "json",
    })
    feats = resp.get("features", [])
    if not feats:
        break
    all_features.extend(feats)
    _log(f"  page {page_no}: +{len(feats):,} (cumulative {len(all_features):,}/{total_count:,})")
    if len(feats) < PAGE_SIZE:
        break  # last page
    offset += PAGE_SIZE
    # Safety valve — abort if total fetched exceeds reported count by >10%
    # (would indicate pagination drift or duplicate rows).
    if len(all_features) > total_count * 1.1:
        print(
            f"ERROR: fetched {len(all_features):,} parcels but service "
            f"reported only {total_count:,} — pagination appears broken. "
            f"Inspect resultOffset behavior on the FeatureServer.",
            file=sys.stderr,
        )
        sys.exit(1)

_log(f"  fetched {len(all_features):,} total parcel records")


# ── 2. Map feature-service rows to seed JSON shape ────────────────────────────

out: dict[str, dict] = {}
skipped_no_pin = 0
skipped_retired = 0
for feat in all_features:
    attrs = feat.get("attributes", {}) or {}
    pin = (attrs.get("PARCEL_ID") or "").strip()
    if not pin:
        skipped_no_pin += 1
        continue

    # STATUS='A' = active; 'R' = retired. Skip retired parcels — they
    # represent old subdivision boundaries no longer in use.
    status = (attrs.get("STATUS") or "").strip().upper()
    if status and status != "A":
        skipped_retired += 1
        continue

    owner_name = (attrs.get("OWNERNAME") or "").strip()
    address    = compose_situs_address(attrs)
    value      = int(attrs.get("MKTTL") or 0)

    out[pin] = {
        "owner_name":         owner_name,
        # Tenure intentionally null — backfilled by
        # backend/tasks/snohomish_tenure_autofill.py from the per-parcel
        # SCOPI portal (already running in production for 98290).
        "last_transfer_date": None,
        "tenure_years":       None,
        "sale_price":         "0",
        "address":            address,
        "value":              value,
        "owner_type":         classify_owner_type(owner_name),
    }

if skipped_no_pin:
    _log(f"  skipped {skipped_no_pin:,} rows with empty PARCEL_ID")
if skipped_retired:
    _log(f"  skipped {skipped_retired:,} retired parcels (STATUS != 'A')")

_log(f"  mapped {len(out):,} active parcels into seed shape")


# ── 3. Self-check: address coverage must clear the floor ──────────────────────

with_address = sum(1 for v in out.values() if (v.get("address") or "").strip())
coverage = with_address / len(out) if out else 0.0
_log(f"address coverage: {with_address:,}/{len(out):,} = {coverage:.1%}")

if coverage < MIN_ADDRESS_COVERAGE:
    print(
        f"\nERROR: address coverage {coverage:.1%} is below the minimum "
        f"({MIN_ADDRESS_COVERAGE:.0%}) for {TARGET_ZIP}. This is the "
        f"May 10 bug shape — refusing to write a broken seed file.\n"
        f"Likely causes:\n"
        f"  - SITUSLINE1 field renamed or removed upstream\n"
        f"  - SITUSZIP filter matching wrong rows\n"
        f"  - Feature service returning truncated attribute set\n"
        f"Inspect a sample row manually via /query?outFields=* before "
        f"re-running.",
        file=sys.stderr,
    )
    sys.exit(1)


# ── 4. Write the seed file ────────────────────────────────────────────────────

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

_log(f"wrote {OUT_PATH}")


# ── 5. Summary stats (parity with build_kc_owners.py) ─────────────────────────

type_dist = Counter(v["owner_type"] for v in out.values())
no_owner_count = sum(1 for v in out.values() if not (v.get("owner_name") or "").strip())

print()
print(f"  ZIP:                 {TARGET_ZIP}")
print(f"  Total PINs:          {len(out):,}")
print(f"  Address coverage:    {coverage:.1%}")
print(f"  Parcels with owner:  {len(out) - no_owner_count:,}")
print(f"  Parcels w/o owner:   {no_owner_count:,}")
print(f"  Owner-type dist:     " + ", ".join(
    f"{t}={n:,}" for t, n in type_dist.most_common()
))
print(f"  Tenure data:         null for all — SCOPI autofill will backfill")
print(f"  Output:              {OUT_PATH}")
