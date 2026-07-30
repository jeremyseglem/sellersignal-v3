#!/usr/bin/env python3
"""
Denver (City & County) CO recorder harvester — clone of run_collin_recorder.py
against denver.co.publicsearch.us (publicsearch.us / neumo platform — the SAME
family as Dallas/Collin/Travis, so the shared backend/harvesters/dallas_recorder.py
grid driver + parser + to_signal_row are reused wholesale).
source_type=co_denver_recorder.

⚠️ VALIDATION STATUS (2026-07-30): the tenant + search form were confirmed
(title "Official Record Search - Denver County, CO", aria 'Starting/Ending
Recorded Date' inputs present), BUT the results grid would not render rows from
the build sandbox's datacenter IP — it sat in a persistent "Attempting to
reconnect / Loading Results" state returning only page chrome. This is the same
edge-gate behavior dallas_recorder.py documents ("raw/datacenter access gets a
challenge; a real GitHub Actions runner clears it on navigation"). Therefore
FIRST-RUN VALIDATION MUST HAPPEN IN THE GITHUB ACTION (dry-run: write=0), not
locally. Do NOT flip the daily cron to write until a dry run there shows real
parsed rows. Two Denver-specific quirks are pre-handled below:
  1. Denver's Starting Recorded Date input ships with a garbage default
     (10/15/0991); a single fill() leaves React state on the default. The
     override clears via empty-fill then value-fill and submits with the
     Search button (matching the Dallas/Collin submit path).
  2. Denver has NO county owner roll wired yet (DENVER_ROLL optional/empty) —
     the harvester still writes raw_signals_v3 decedent rows; the existing
     rematch_autofill matcher resolves them against the Denver parcels_v3 rows
     already loaded for the 5 live Denver ZIPs. A county-wide roll (for
     out-of-territory heir resolution) can be added later like Collin's.

CO death->title recorded instruments (classify_doc_type already covers the
generic set; Colorado uses PERSONAL REPRESENTATIVE'S DEED as the workhorse):
  PERSONAL REPRESENTATIVE / EXECUTOR / ADMINISTRATOR DEED -> probate
  DEED OF DISTRIBUTION -> probate ; TRANSFER ON DEATH / BENEFICIARY DEED ->
  transfer_on_death ; DEATH CERTIFICATE -> death.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import dallas_recorder as dr  # noqa: E402

dr.RESULTS_URL = "https://denver.co.publicsearch.us/results"
dr.HOME_URL = "https://denver.co.publicsearch.us/"
dr.UI_DRIVE = True
dr.SOURCE_TYPE = "co_denver_recorder"

# Colorado's beneficiary-deed name for TOD — add to the doc-type needles so
# the CO transfer-on-death instrument is captured alongside the generic set.
if not any(n[0] == "BENEFICIARY DEED" for n in dr.DEATH_DOCTYPE_SIGNALS):
    dr.DEATH_DOCTYPE_SIGNALS.append(("BENEFICIARY DEED", "transfer_on_death"))


def _denver_ui_drive(page, begin, end):
    """Denver override: its Starting Recorded Date input ships with a garbage
    default (10/15/0991) that a single fill() doesn't clear in React state.
    Empty-fill then value-fill both inputs, then click Search."""
    page.goto(dr.HOME_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    try:
        dis = page.query_selector("button[aria-label='Dismiss announcement']")
        if dis:
            dis.click()
            time.sleep(1)
    except Exception:
        pass
    s = page.query_selector("input[aria-label='Starting Recorded Date']")
    e = page.query_selector("input[aria-label='Ending Recorded Date']")
    if not (s and e):
        raise RuntimeError("DENVER_UI_DRIVE: date inputs not found")
    for el, val in ((s, begin.strftime("%m/%d/%Y")), (e, end.strftime("%m/%d/%Y"))):
        el.fill("")
        el.fill(val)
    btn = page.query_selector("button[aria-label='Search']")
    submitted = False
    if btn:
        for click in (lambda: btn.click(timeout=8000),
                      lambda: btn.click(force=True, timeout=8000),
                      lambda: page.evaluate("el => el.click()", btn)):
            try:
                click()
                submitted = True
                break
            except Exception:
                continue
    if not submitted:
        e.press("Enter")
    time.sleep(9)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    try:
        print(f"    [denver_ui_drive] url={page.url[:120]}")
    except Exception:
        pass


# Monkeypatch the shared driver's UI-drive with the Denver-specific one.
dr._ui_drive_search = _denver_ui_drive

import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
DENVER_ROLL = os.environ.get("DENVER_ROLL", "")  # optional county-wide roll
DAYS = int(os.environ.get("DAYS", "7"))
CHUNK_DAYS = int(os.environ.get("CHUNK_DAYS", "1"))
TABLE = "raw_signals_v3"
SOURCE = "co_denver_recorder"


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
    lag = int(os.environ.get("LAG_DAYS", "10"))
    end = datetime.now().date() - timedelta(days=lag)
    begin = end - timedelta(days=DAYS)
    seen = existing_refs() if WRITE else set()
    print(f"[denver_recorder] window {begin}..{end} chunk={CHUNK_DAYS}d "
          f"write={WRITE} already_in_db={len(seen)}")

    idx = None
    if DENVER_ROLL and os.path.exists(DENVER_ROLL):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib_county_resolve import CountyOwnerIndex
        idx = CountyOwnerIndex.from_maricopa_roll(DENVER_ROLL)
        print(f"[recorder] county owner index: {idx.total:,} accounts")
    else:
        print("[recorder] no DENVER_ROLL — skipping county-wide resolution "
              "(rematch matcher resolves against loaded Denver parcels_v3)")

    if WRITE and not (SUPABASE_URL and SERVICE_KEY):
        print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
        sys.exit(1)

    total_grid_rows = estate_rows = err = wrote = 0
    dry_samples = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=dr.UA,
                            viewport={"width": 1366, "height": 1100}, locale="en-US")
        page = ctx.new_page()
        page.goto(dr.HOME_URL, wait_until="domcontentloaded", timeout=60000)
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
                        if len(dry_samples) < 8:
                            dry_samples.append(sig)
                print(f"  {cstart}..{cend}: grid={grid_rows} estate={len(chunk_rows)}")
                if idx:
                    from run_collin_recorder import _resolve_rows  # reuse
                    _resolve_rows(idx, chunk_rows)
                if WRITE and chunk_rows:
                    fresh = [s for s in chunk_rows if s["document_ref"] not in seen]
                    wrote += write_rows(fresh)
                    seen.update(s["document_ref"] for s in fresh)
            except Exception as ex:
                err += 1
                print(f"  {cstart}..{cend}: ERROR {repr(ex)[:160]}")

    print(f"[denver_recorder] grid_rows={total_grid_rows} estate={estate_rows} "
          f"wrote={wrote} errors={err}")
    if not WRITE:
        print("[denver_recorder] DRY RUN — sample signals:")
        for s in dry_samples:
            print("  ", json.dumps({k: s.get(k) for k in
                  ("signal_type", "document_ref", "party_names", "property_hint")},
                  default=str)[:220])
        if total_grid_rows == 0:
            print("  ⚠️ 0 grid rows — if this is the Actions runner, the tenant "
                  "grid failed to render; re-check the search-form drive. If this "
                  "is a local sandbox, that's expected (edge gate).")


if __name__ == "__main__":
    main()
