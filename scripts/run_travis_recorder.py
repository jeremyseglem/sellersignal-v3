#!/usr/bin/env python3
"""
Travis County (TX) recorder harvester — clone of run_dallas_recorder.py
against travis.tx.publicsearch.us (same neumo platform; verified 2026-06-12:
HTTP 200, no Cloudflare challenge, same /results URL param shape).
source_type=tx_travis_recorder. County inversion uses the TCAD appraisal
roll (TCAD_ROLL env -> CountyOwnerIndex.from_tcad_roll).
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import dallas_recorder as dr  # noqa: E402
# Point the shared neumo-platform module at the Travis subdomain. Everything
# else (grid iteration, doc-type needles, to_signal_row) is platform-generic.
dr.RESULTS_URL = "https://travis.tx.publicsearch.us/results"
dr.HOME_URL = "https://travis.tx.publicsearch.us/"
dr.UI_DRIVE = True  # this tenant does not auto-execute URL searches
dr.SOURCE_TYPE = "tx_travis_recorder"

import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
# County-wide decedent/heir resolution (the inversion). Set DCAD_ZIP to the
# bulk Data Products zip to enable; empty disables.
DCAD_ZIP = os.environ.get("TCAD_ROLL", "")  # TCAD appraisal roll zip
DAYS = int(os.environ.get("DAYS", "7"))
CHUNK_DAYS = int(os.environ.get("CHUNK_DAYS", "1"))
TABLE = "raw_signals_v3"
SOURCE = "tx_travis_recorder"


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


def main():
    # Dallas recordings post with a lag — the index is typically "certified
    # through" ~5-7 days behind today, so windows ending at today return 0 rows
    # for the most recent days. Trail the end of the window by LAG_DAYS so we
    # harvest days that have actually posted. Window = [end-LAG-DAYS, end-LAG].
    # Travis's date control is a relative preset ("Last 1 Week"), NOT a
    # fillable range — so the window MUST be recent for the preset span to
    # overlap it. End at today (the preset already excludes un-posted very
    # recent days) and span 8 days so the client-side filter keeps the full
    # "Last 1 Week" grid with a day of margin. LAG_DAYS honored only if set
    # explicitly (legacy override).
    lag = int(os.environ.get("LAG_DAYS", "0"))
    days = int(os.environ.get("DAYS", "8"))
    end = datetime.now().date() - timedelta(days=lag)
    begin = end - timedelta(days=days)
    seen = existing_refs() if WRITE else set()
    print(f"[travis_recorder] preset-sweep window {begin}..{end} "
          f"preset_option={dr.TRAVIS_PRESET_OPTION} "
          f"write={WRITE} already_in_db={len(seen)}")

    all_rows, total_grid_rows, estate_rows, err = [], 0, 0, 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=dr.UA,
                            viewport={"width": 1366, "height": 1100}, locale="en-US")
        page = ctx.new_page()
        # Clear the Cloudflare gate once on the site root.
        page.goto("https://travis.tx.publicsearch.us/", wait_until="domcontentloaded",
                  timeout=60000)
        time.sleep(10)

        # Travis's date control is a react-downshift preset list (no
        # fillable date inputs), so we can't chunk arbitrary windows. Do
        # ONE preset sweep (dr.TRAVIS_PRESET_OPTION = "Last 1 Week") and
        # filter the returned grid to [begin, end] on recorded_date here.
        # begin/end passed to iter_window_rows are ignored by the preset
        # path but kept for signature compatibility.
        seen_refs = set()
        try:
            for row in dr.iter_window_rows(page, begin, end):
                total_grid_rows += 1
                rd = row.get("recorded_date")
                try:
                    rd_date = datetime.strptime(rd, "%m/%d/%Y").date() if rd else None
                except Exception:
                    rd_date = None
                # keep rows within the target window (or undated, to be safe)
                if rd_date is not None and not (begin <= rd_date <= end):
                    continue
                ref = row.get("doc_number") or row.get("document_ref")
                if ref and ref in seen_refs:
                    continue
                if ref:
                    seen_refs.add(ref)
                sig = dr.to_signal_row(row)
                if sig:
                    estate_rows += 1
                    all_rows.append(sig)
            print(f"  preset sweep {begin}..{end}: {total_grid_rows} grid rows, "
                  f"{estate_rows} estate (after date filter)")
        except Exception as e:
            err += 1
            print(f"  preset sweep ERR {type(e).__name__}: {e}")
        b.close()

    print(f"[travis_recorder] grid_rows={total_grid_rows} estate_instruments={estate_rows} "
          f"new_mappable={len(all_rows)} errors={err}")

    if DCAD_ZIP and os.path.exists(DCAD_ZIP):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib_county_resolve import CountyOwnerIndex
        idx = CountyOwnerIndex.from_tcad_roll(DCAD_ZIP)
        print(f"[recorder] county owner index: {idx.total:,} accounts")
        n_res = 0
        for sig in all_rows:
            rd = sig.get("raw_data") or {}
            sig["raw_data"] = rd
            rd["county_resolution_ran"] = True
            parties = sig.get("party_names") or []
            dec = parties[0].get("raw") if parties else None
            if dec:
                hits = idx.resolve(dec, order="last_first")
                if hits:
                    rd["resolved_parcels"] = hits
                    b = hits[0]
                    sig["property_hint"] = sig.get("property_hint") or                         f"{b['address']}, {b['city']} {b['zip']}".strip(", ")
                    n_res += 1
            for pp in parties[1:]:
                if pp.get("role") == "personal_representative" and pp.get("raw"):
                    hh = idx.resolve(pp["raw"], order="last_first")
                    if hh:
                        rd["resolved_heir_parcels"] = hh
                    break
        print(f"[recorder] county_resolved={n_res}/{len(all_rows)}")
    else:
        print("[recorder] no DCAD_ZIP — skipping county-wide resolution")

    if WRITE:
        if not (SUPABASE_URL and SERVICE_KEY):
            print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
            sys.exit(1)
        n = 0
        for i in range(0, len(all_rows), 100):
            n += write_rows(all_rows[i:i + 100])
        print(f"[travis_recorder] WROTE {n} signals to {TABLE}")
    else:
        print("[travis_recorder] DRY RUN — no writes. Sample rows:")
        for row in all_rows[:5]:
            print(json.dumps(row, indent=2))
        print(f"(total {len(all_rows)} rows would be written)")


if __name__ == "__main__":
    main()
