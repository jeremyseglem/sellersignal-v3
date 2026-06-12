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


def main():
    end = datetime.now()
    begin = end - timedelta(days=DAYS)
    bstr, estr = begin.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
    seen = existing_refs() if WRITE else set()
    print(f"[maricopa_recorder] window {bstr}..{estr} codes={CODES} "
          f"write={WRITE} already_in_db={len(seen)}")

    op = mr.new_session()
    rows, ocr_ct, err_ct = [], 0, 0
    for code in CODES:
        if code not in mr.PARSERS:
            print(f"  skip {code}: no parser")
            continue
        dated = mr.discover_dated(op, code, bstr, estr)
        if os.environ.get("RESOLVE_BACKFILL", "0") != "1":
            # Normal daily mode: skip recordings already in DB. Set
            # RESOLVE_BACKFILL=1 to re-OCR + upsert (merge-duplicates)
            # existing signals so they gain resolved_parcels retroactively.
            dated = [(rec, dt) for rec, dt in dated if rec not in seen]
        print(f"  {code}: {len(dated)} new recordings to OCR")
        for rec, rec_date in dated:
            try:
                parsed = mr.PARSERS[code](mr.ocr_pdf(mr.fetch_pdf(op, rec)))
                parsed["recording_number"] = rec
                parsed["event_date"] = rec_date
                ocr_ct += 1
                row = mr.to_signal_row(parsed)
                if row:
                    rows.append(row)
            except Exception as e:
                err_ct += 1
                print(f"    {rec} ERR {type(e).__name__}: {e}")
            time.sleep(0.7)

    print(f"[maricopa_recorder] OCR'd={ocr_ct} errors={err_ct} mappable_signals={len(rows)}")

    # ── County-wide inversion (2026-06-12, Dallas/Travis pattern) ──────────
    # Resolve every decedent (and the PR as heir-channel) against the FULL
    # Maricopa Assessor roll, attaching resolved parcels to raw_data. The
    # matcher's Layer 0 / 0.5 turn live-ZIP hits into identity matches;
    # everything else is expansion intel. Without this, AZ probate matching
    # was fuzzy-in-ZIP only — ~9% county coverage = near-zero leads (the
    # exact failure Dallas had pre-inversion).
    MARICOPA_ROLL = os.environ.get("MARICOPA_ROLL", "")
    if MARICOPA_ROLL and os.path.exists(MARICOPA_ROLL) and rows:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib_county_resolve import CountyOwnerIndex
        idx = CountyOwnerIndex.from_maricopa_roll(MARICOPA_ROLL)
        print(f"[recorder] county owner index: {idx.total:,} parcels")
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
        print(f"[recorder] county_resolved={n_res}/{len(rows)}")
    elif rows:
        print("[recorder] no MARICOPA_ROLL — skipping county-wide resolution")

    if WRITE:
        if not (SUPABASE_URL and SERVICE_KEY):
            print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
            sys.exit(1)
        n = 0
        for i in range(0, len(rows), 100):
            n += write_rows(rows[i:i + 100])
        print(f"[maricopa_recorder] WROTE {n} probate signals to {TABLE}")
    else:
        print("[maricopa_recorder] DRY RUN — no writes. Sample rows:")
        for row in rows[:3]:
            print(json.dumps(row, indent=2))
        print(f"(total {len(rows)} rows would be written)")


if __name__ == "__main__":
    main()
