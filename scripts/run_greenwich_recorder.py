#!/usr/bin/env python3
"""
Greenwich CT recorder harvester — clone of run_dallas_recorder.py
against greenwich.ct.publicsearch.us (verified 2026-06-12: HTTP 200, no
Cloudflare, DALLAS-GENERATION React frontend — unlike Travis's newer preact
build, so the URL-param search should auto-execute like Dallas).
source_type=ct_greenwich_recorder. County inversion uses the CCAD FeatureServer
roll (CT_ROLL env -> CountyOwnerIndex.from_maricopa_roll; the CT
roll builder emits the Maricopa CSV schema deliberately).
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import dallas_recorder as dr  # noqa: E402
# Point the shared neumo-platform module at the Greenwich subdomain. Everything
# else (grid iteration, doc-type needles, to_signal_row) is platform-generic.
dr.RESULTS_URL = "https://greenwich.ct.publicsearch.us/results"
dr.HOME_URL = "https://greenwich.ct.publicsearch.us/"
dr.UI_DRIVE = True  # this tenant does not auto-execute URL searches
# CT town-clerk vocabulary: probate certificates and fiduciary/devise
# instruments that the TX list doesn't carry. Appended so the shared
# classifier recognizes them (needle, signal_type) — same shape as
# DEATH_DOCTYPE_SIGNALS entries.
dr.DEATH_DOCTYPE_SIGNALS = list(dr.DEATH_DOCTYPE_SIGNALS) + [
    ("CERTIFICATE OF DEVISE", "probate"),
    ("CERT OF DEVISE", "probate"),
    ("PROBATE CERTIFICATE", "probate"),
    ("CERTIFICATE OF DESCENT", "probate"),
    ("FIDUCIARY DEED", "probate"),
    ("PROBATE", "probate"),
]

# Greenwich grid column order differs from both Dallas and Collin (captured
# 2026-06-12): DOC# | BOOK | PAGE | GRANTOR | GRANTEE | DOC TYPE |
# PROPERTY ADDRESS | RECORDED DATE | RELATED DOCS. Doc numbers are short
# per-volume sequences (e.g. 03101), so document_ref is composed as
# GW-{book}-{page}-{num} for uniqueness. PROPERTY ADDRESS lands in
# legal_description — a direct parcel-resolution gift the TX grids lack.
import re as _re
dr._ROW_RE = _re.compile(
    r"(?P<docnum>\d{3,8})\t(?P<bvp>\d+\t\d+)\t(?P<grantor>[^\t\n]+?)\t"
    r"(?P<grantee>[^\t\n]+?)\t(?P<doctype>[A-Z][A-Z '/&.-]+?)\t"
    r"(?P<legal>[^\t\n]*)\t(?P<recorded>\d{1,2}/\d{1,2}/20\d{2})(?P<town>)")
_orig_parse = dr.parse_rows_from_text
def _gw_parse(text):
    rows = _orig_parse(text)
    for r in rows:
        bvp = _re.sub(r"\s+", "-", (r.get("book_vol_page") or "").strip())
        r["doc_number"] = f"GW-{bvp}-{r['doc_number']}"
    return rows
dr.parse_rows_from_text = _gw_parse
dr.SOURCE_TYPE = "ct_greenwich_recorder"

import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
# County-wide decedent/heir resolution (the inversion). Set CT_ROLL to the
# bulk Data Products zip to enable; empty disables.
CT_ROLL = os.environ.get("CT_ROLL", "")  # CCAD county roll csv.gz
DAYS = int(os.environ.get("DAYS", "7"))
CHUNK_DAYS = int(os.environ.get("CHUNK_DAYS", "1"))
TABLE = "raw_signals_v3"
SOURCE = "ct_greenwich_recorder"


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=_headers(),
                     params={"source_type": f"eq.{SOURCE}", "select": "document_ref"},
                     timeout=90)
    r.raise_for_status()
    return {row["document_ref"] for row in r.json()}


def write_rows(rows: list) -> int:
    if not rows:
        return 0
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE}",
                      headers={**_headers(),
                               "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "source_type,document_ref"},
                      json=rows, timeout=180)
    if not r.ok:
        print(f"  WRITE ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return len(rows)


def daterange_chunks(begin, end, chunk_days):
    cur = begin
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def _resolve_rows(idx, rows):
    """County-wide resolution for ONE batch of signal rows (mutates in place).
    Returns the number of rows that resolved to >=1 parcel. No-op if idx is
    None. Pulled out so each chunk can be resolved + written immediately."""
    if not idx:
        return 0
    n_res = 0
    for sig in rows:
        rd = sig.get("raw_data") or {}
        sig["raw_data"] = rd
        rd["county_resolution_ran"] = True
        parties = sig.get("party_names") or []
        dec = parties[0].get("raw") if parties else None
        if dec:
            hits = idx.resolve(dec, order="last_first")
            if hits:
                rd["resolved_parcels"] = hits
                b0 = hits[0]
                sig["property_hint"] = sig.get("property_hint") or \
                    f"{b0['address']}, {b0['city']} {b0['zip']}".strip(", ")
                n_res += 1
        for pp in parties[1:]:
            if pp.get("role") == "personal_representative" and pp.get("raw"):
                hh = idx.resolve(pp["raw"], order="last_first")
                if hh:
                    rd["resolved_heir_parcels"] = hh
                break
    return n_res


def main():
    # Recordings post with a lag; trail the window end by LAG_DAYS so we only
    # harvest days that have actually posted. Window = [end-LAG-DAYS, end-LAG].
    lag = int(os.environ.get("LAG_DAYS", "10"))
    end = datetime.now().date() - timedelta(days=lag)
    begin = end - timedelta(days=DAYS)
    seen = existing_refs() if WRITE else set()
    print(f"[greenwich_recorder] window {begin}..{end} chunk={CHUNK_DAYS}d "
          f"write={WRITE} already_in_db={len(seen)}")

    # Load the county owner index ONCE up front so each chunk can be resolved
    # and written immediately (per-chunk flush): a long/cancelled run is now
    # cancellation-safe and resumable (everything written before a kill
    # persists; existing_refs/upsert dedupes on re-run). Replaces the old
    # accumulate-all-then-write-once pattern (the Maricopa loss mode).
    idx = None
    if CT_ROLL and os.path.exists(CT_ROLL):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib_county_resolve import CountyOwnerIndex
        idx = CountyOwnerIndex.from_maricopa_roll(CT_ROLL)
        print(f"[recorder] county owner index: {idx.total:,} accounts")
    else:
        print("[recorder] no CT_ROLL — skipping county-wide resolution")

    if WRITE and not (SUPABASE_URL and SERVICE_KEY):
        print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
        sys.exit(1)

    total_grid_rows, estate_rows, err, wrote, resolved = 0, 0, 0, 0, 0
    dry_samples = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=dr.UA,
                            viewport={"width": 1366, "height": 1100}, locale="en-US")
        page = ctx.new_page()
        # Clear the Cloudflare gate once on the site root.
        page.goto("https://greenwich.ct.publicsearch.us/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(10)

        for cstart, cend in daterange_chunks(begin, end, CHUNK_DAYS):
            try:
                chunk_rows = []
                grid_rows = 0
                for row in dr.iter_window_rows(page, cstart, cend):
                    grid_rows += 1
                    total_grid_rows += 1
                    sig = dr.to_signal_row(row)
                    if sig:
                        estate_rows += 1
                        chunk_rows.append(sig)
                # Resolve + flush THIS chunk immediately (durable progress).
                resolved += _resolve_rows(idx, chunk_rows)
                if WRITE and chunk_rows:
                    for i in range(0, len(chunk_rows), 100):
                        wrote += write_rows(chunk_rows[i:i + 100])
                elif not WRITE and len(dry_samples) < 5:
                    dry_samples.extend(chunk_rows[:5 - len(dry_samples)])
                print(f"  {cstart}..{cend}: {grid_rows} grid rows, {len(chunk_rows)} estate "
                      f"(flushed; wrote_total={wrote})")
            except Exception as e:
                err += 1
                print(f"  {cstart}..{cend} ERR {type(e).__name__}: {e}")
            time.sleep(1.5)
        b.close()

    print(f"[greenwich_recorder] grid_rows={total_grid_rows} estate_instruments={estate_rows} "
          f"resolved={resolved} errors={err}")
    if WRITE:
        print(f"[greenwich_recorder] WROTE {wrote} signals to {TABLE} (flushed per chunk)")
    else:
        print("[greenwich_recorder] DRY RUN — no writes. Sample rows:")
        for row in dry_samples:
            print(json.dumps(row, indent=2))
        print(f"(dry run — {estate_rows} estate rows would be written)")


if __name__ == "__main__":
    main()
