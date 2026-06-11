#!/usr/bin/env python3
"""
Scheduled runner for the Dallas County Recorder harvester.

Runs in a GitHub Action (NOT the Railway app) so the headless-browser
dependency stays out of production. It renders the neumo Official Records
results grid for a recent recorded-date window, parses death/estate
instruments, and writes `probate` / `transfer_on_death` / `death` signals to
raw_signals_v3 in Supabase. The app's existing matcher (rematch_autofill) links
them to parcels by decedent name — no app change required.

ENV:
  SUPABASE_URL           https://eeqsbvizgpuehphiaslo.supabase.co
  SUPABASE_SERVICE_KEY   service-role key (write) — GitHub secret
  WRITE                  "1" to write; anything else = dry run (default)
  DAYS                   lookback window in days (default 7)
  CHUNK_DAYS             sub-window size to page large date ranges (default 2)

Dependencies: playwright + chromium (installed in the Action), requests (pip).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import dallas_recorder as dr  # noqa: E402
import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
DAYS = int(os.environ.get("DAYS", "7"))
CHUNK_DAYS = int(os.environ.get("CHUNK_DAYS", "1"))
TABLE = "raw_signals_v3"
SOURCE = "tx_dallas_recorder"


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
    lag = int(os.environ.get("LAG_DAYS", "10"))
    end = datetime.now().date() - timedelta(days=lag)
    begin = end - timedelta(days=DAYS)
    seen = existing_refs() if WRITE else set()
    print(f"[dallas_recorder] window {begin}..{end} chunk={CHUNK_DAYS}d "
          f"write={WRITE} already_in_db={len(seen)}")

    all_rows, total_grid_rows, estate_rows, err = [], 0, 0, 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=dr.UA,
                            viewport={"width": 1366, "height": 1100}, locale="en-US")
        page = ctx.new_page()
        # Clear the Cloudflare gate once on the site root.
        page.goto("https://dallas.tx.publicsearch.us/", wait_until="domcontentloaded",
                  timeout=60000)
        time.sleep(10)

        for cstart, cend in daterange_chunks(begin, end, CHUNK_DAYS):
            try:
                grid_rows = 0
                estate_in_chunk = 0
                for row in dr.iter_window_rows(page, cstart, cend):
                    grid_rows += 1
                    total_grid_rows += 1
                    sig = dr.to_signal_row(row)
                    if sig:
                        estate_in_chunk += 1
                        estate_rows += 1
                        if sig["document_ref"] not in seen:
                            all_rows.append(sig)
                print(f"  {cstart}..{cend}: {grid_rows} grid rows, {estate_in_chunk} estate")
            except Exception as e:
                err += 1
                print(f"  {cstart}..{cend} ERR {type(e).__name__}: {e}")
            time.sleep(1.5)
        b.close()

    print(f"[dallas_recorder] grid_rows={total_grid_rows} estate_instruments={estate_rows} "
          f"new_mappable={len(all_rows)} errors={err}")

    if WRITE:
        if not (SUPABASE_URL and SERVICE_KEY):
            print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
            sys.exit(1)
        n = 0
        for i in range(0, len(all_rows), 100):
            n += write_rows(all_rows[i:i + 100])
        print(f"[dallas_recorder] WROTE {n} signals to {TABLE}")
    else:
        print("[dallas_recorder] DRY RUN — no writes. Sample rows:")
        for row in all_rows[:5]:
            print(json.dumps(row, indent=2))
        print(f"(total {len(all_rows)} rows would be written)")


if __name__ == "__main__":
    main()
