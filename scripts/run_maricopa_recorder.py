#!/usr/bin/env python3
"""
Scheduled runner for the Maricopa County Recorder OCR harvester.

Runs OUTSIDE the main Railway app (in a GitHub Action) so the OCR system
dependencies (tesseract + poppler) never touch the production service. It
discovers recent probate Deeds of Distribution, OCRs + parses them, and writes
`probate` signals to raw_signals_v3 in Supabase. The main app's existing
matcher (rematch_autofill) then links them to parcels by decedent name — no
change to the live app required.

ENV:
  SUPABASE_URL           e.g. https://eeqsbvizgpuehphiaslo.supabase.co
  SUPABASE_SERVICE_KEY   service-role key (write access) — GitHub secret
  WRITE                  "1" to write to the DB; anything else = dry run (default)
  DAYS                   lookback window in days (default 14)
  CODES                  comma list of doc codes (default "PD")

Dependencies: tesseract-ocr, tesseract-ocr-eng, poppler-utils (apt) + requests (pip).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "harvesters"))
import maricopa_recorder as mr  # noqa: E402
import requests  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
DAYS = int(os.environ.get("DAYS", "14"))
END_OFFSET_DAYS = int(os.environ.get("END_OFFSET_DAYS", "0"))  # window ENDS this many days before now (for chunked deep backfill)
SUBWIN_DAYS = int(os.environ.get("SUBWIN_DAYS", "30"))         # flush granularity: OCR+write per sub-window so cancelled runs persist progress
CODES = [c.strip() for c in os.environ.get("CODES", "PD").split(",") if c.strip()]
TABLE = "raw_signals_v3"
SOURCE = "az_maricopa_recorder"


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    """document_refs already harvested, so we don't re-OCR them."""
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=_headers(),
                     params={"source_type": f"eq.{SOURCE}", "select": "document_ref"},
                     timeout=90)
    r.raise_for_status()
    return {row["document_ref"] for row in r.json()}


def write_rows(rows: list) -> int:
    """Upsert on (source_type, document_ref)."""
    if not rows:
        return 0
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE}",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "source_type,document_ref"},
                      json=rows, timeout=180)
    if not r.ok:
        print(f"  WRITE ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return len(rows)


def _load_county_index():
    """Load the full Maricopa Assessor roll once (county-wide inversion)."""
    roll = os.environ.get("MARICOPA_ROLL", "")
    if roll and os.path.exists(roll):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib_county_resolve import CountyOwnerIndex
        idx = CountyOwnerIndex.from_maricopa_roll(roll)
        print(f"[recorder] county owner index: {idx.total:,} parcels")
        return idx
    print("[recorder] no MARICOPA_ROLL — county-wide resolution disabled")
    return None


def _invert(rows, idx):
    """Attach resolved_parcels (decedent) + resolved_heir_parcels (PR) from the
    county roll. Same logic as the pre-2026-06-13 single-pass block, applied
    per sub-window so it runs before each incremental flush."""
    if not idx:
        return 0
    n_res = 0
    for sig in rows:
        rd = sig.setdefault("raw_data", {})
        rd["county_resolution_ran"] = True
        dec = rd.get("decedent")
        if dec:
            resolved = idx.resolve(dec)  # 'Estate of First Last' order
            if resolved:
                rd["resolved_parcels"] = resolved
                n_res += 1
                best = resolved[0]
                if not sig.get("property_hint"):
                    sig["property_hint"] = (f"{best['address']}, "
                                            f"{best['city']} {best['zip']}").strip(", ")
        pr = rd.get("pr_name")
        if pr:
            heir_hits = idx.resolve(pr)
            if heir_hits:
                rd["resolved_heir_parcels"] = heir_hits
    return n_res


def main():
    # 2026-06-13: walk the full window in SUBWIN_DAYS slices and write per slice.
    # The old single-final-write meant any run cancelled mid-OCR (every deep
    # backfill since 06-12) persisted NOTHING. Per-slice flush + the existing
    # skip-seen logic makes deep pulls cancellation-safe and resumable: re-run
    # the same dispatch and it continues from where the last one stopped.
    # 2026-06-13: CAPTURE mode — OCR a few docs of each code and dump the raw
    # text so new parsers (JP / affidavit instruments) can be written against
    # real samples. No roll, no parse, no DB write. Triggered by CAPTURE=1.
    if os.environ.get("CAPTURE", "0") == "1":
        cap_end = datetime.now() - timedelta(days=END_OFFSET_DAYS)
        cap_begin = cap_end - timedelta(days=DAYS)
        op = mr.new_session()
        n = int(os.environ.get("CAPTURE_N", "3"))
        for code in CODES:
            dated = mr.discover_dated(op, code, cap_begin.strftime("%m/%d/%Y"),
                                      cap_end.strftime("%m/%d/%Y"))
            print(f"[capture] {code}: {len(dated)} recordings in window", flush=True)
            for rec, dt in dated[:n]:
                try:
                    txt = mr.ocr_pdf(mr.fetch_pdf(op, rec))
                    print(f"\n===== CAPTURE code={code} rec={rec} date={dt} =====\n"
                          f"{txt[:4000]}\n===== END {rec} =====", flush=True)
                except Exception as e:
                    print(f"  capture {rec} ERR {type(e).__name__}: {e}", flush=True)
                time.sleep(0.7)
        return

    resolve_backfill = os.environ.get("RESOLVE_BACKFILL", "0") == "1"
    full_end = datetime.now() - timedelta(days=END_OFFSET_DAYS)
    full_begin = full_end - timedelta(days=DAYS)
    print(f"[maricopa_recorder] FULL window {full_begin:%m/%d/%Y}..{full_end:%m/%d/%Y} "
          f"codes={CODES} write={WRITE} resolve_backfill={resolve_backfill} "
          f"subwin={SUBWIN_DAYS}d offset={END_OFFSET_DAYS}d")
    # In resolve-backfill mode we intentionally re-OCR seen recordings; otherwise skip them.
    seen = existing_refs() if (WRITE and not resolve_backfill) else set()
    print(f"[maricopa_recorder] already_in_db={len(seen)}")

    op = mr.new_session()
    idx = _load_county_index()
    tot_ocr = tot_err = tot_written = tot_res = 0
    sample = []

    cur_end = full_end
    while cur_end > full_begin:
        cur_begin = max(full_begin, cur_end - timedelta(days=SUBWIN_DAYS))
        bstr, estr = cur_begin.strftime("%m/%d/%Y"), cur_end.strftime("%m/%d/%Y")
        rows = []
        for code in CODES:
            if code not in mr.PARSERS:
                print(f"  skip {code}: no parser")
                continue
            dated = mr.discover_dated(op, code, bstr, estr)
            if not resolve_backfill:
                dated = [(rec, dt) for rec, dt in dated if rec not in seen]
            print(f"  [{bstr}..{estr}] {code}: {len(dated)} recordings to OCR")
            for rec, rec_date in dated:
                try:
                    parsed = mr.PARSERS[code](mr.ocr_pdf(mr.fetch_pdf(op, rec)))
                    parsed["recording_number"] = rec
                    parsed["event_date"] = rec_date
                    tot_ocr += 1
                    row = mr.to_signal_row(parsed)
                    if row:
                        rows.append(row)
                except Exception as e:
                    tot_err += 1
                    print(f"    {rec} ERR {type(e).__name__}: {e}")
                time.sleep(0.7)

        tot_res += _invert(rows, idx)

        if WRITE:
            if not (SUPABASE_URL and SERVICE_KEY):
                print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
                sys.exit(1)
            n = 0
            for i in range(0, len(rows), 100):
                n += write_rows(rows[i:i + 100])
            tot_written += n
            seen |= {r["document_ref"] for r in rows if r.get("document_ref")}
            print(f"  [{bstr}..{estr}] WROTE {n}  (running total {tot_written})")
        else:
            sample.extend(rows[:3])
            print(f"  [{bstr}..{estr}] DRY: {len(rows)} rows would be written")

        cur_end = cur_begin

    print(f"[maricopa_recorder] DONE ocr={tot_ocr} errors={tot_err} "
          f"county_resolved={tot_res} written={tot_written}")
    if not WRITE:
        print("[maricopa_recorder] DRY RUN — sample rows:")
        for row in sample[:3]:
            print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
