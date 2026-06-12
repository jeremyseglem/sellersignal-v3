#!/usr/bin/env python3
"""
Scheduled runner for the TOPICs statewide probate-citation harvester.

Cursor-free design: each run finds the live edge of the sequential ID space
(binary probe), then walks BACKWARD collecting records until publication
dates fall older than SINCE_DAYS (with tolerance for slight out-of-order
posting). Dedupe on (source_type, document_ref=cause_number) makes re-scans
idempotent, so no cursor persistence is needed and overlapping windows are
harmless.

Plain HTTP (requests + pypdf) — no browser. txcourts.gov has no edge gate.

ENV:
  SUPABASE_URL / SUPABASE_SERVICE_KEY   (write creds — GitHub secrets)
  WRITE        "1" to write; default dry run
  SINCE_DAYS   lookback window (default 7)
  EDGE_HINT    starting hint for live-edge probe (default 105000; harmless
               if stale — the probe walks from wherever it lands)
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topics_citations as tc  # noqa: E402
import requests  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
SINCE_DAYS = int(os.environ.get("SINCE_DAYS", "7"))
EDGE_HINT = int(os.environ.get("EDGE_HINT", "105000"))
# County-wide decedent->parcel resolution (the inversion, 2026-06-11).
# Point DCAD_ZIP at the bulk Data Products zip to enable; empty disables
# (signals still write, just without resolved_parcels).
DCAD_ZIP = os.environ.get("DCAD_ZIP", "")
TABLE = "raw_signals_v3"
SOURCE = "tx_topics_citations"
POLITE = 0.35
OLD_STREAK_STOP = 40  # stop after this many consecutive too-old records


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=_headers(),
                     params={"source_type": f"eq.{SOURCE}",
                             "select": "document_ref"}, timeout=90)
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


def main():
    cutoff = (datetime.now().date() - timedelta(days=SINCE_DAYS)).isoformat()
    seen = existing_refs() if WRITE else set()
    s = requests.Session()

    # Per-county owner indexes. TOPICs is statewide — a citation must be
    # resolved against ITS OWN county's roll, never another's (resolving a
    # Travis decedent against the Dallas roll = guaranteed false positives).
    # Counties without a loaded roll get no marker, so the matcher's fuzzy
    # fallback still applies to them.
    from lib_county_resolve import CountyOwnerIndex
    owner_indexes = {}
    if DCAD_ZIP and os.path.exists(DCAD_ZIP):
        owner_indexes["Dallas"] = CountyOwnerIndex.from_dcad_zip(DCAD_ZIP)
        print(f"[topics] Dallas owner index: {owner_indexes['Dallas'].total:,} accounts")
    TCAD_ROLL = os.environ.get("TCAD_ROLL", "")
    if TCAD_ROLL and os.path.exists(TCAD_ROLL):
        owner_indexes["Travis"] = CountyOwnerIndex.from_tcad_roll(TCAD_ROLL)
        print(f"[topics] Travis owner index: {owner_indexes['Travis'].total:,} accounts")
    COLLIN_ROLL = os.environ.get("COLLIN_ROLL", "")
    if COLLIN_ROLL and os.path.exists(COLLIN_ROLL):
        # Collin roll builder emits the Maricopa CSV schema deliberately —
        # one loader serves both counties.
        owner_indexes["Collin"] = CountyOwnerIndex.from_maricopa_roll(COLLIN_ROLL)
        print(f"[topics] Collin owner index: {owner_indexes['Collin'].total:,} accounts")
    if not owner_indexes:
        print("[topics] no county rolls — skipping county-wide resolution")

    edge = tc.find_live_edge(s, start_hint=EDGE_HINT)
    print(f"[topics] live edge id={edge}  cutoff pub_start>={cutoff}  "
          f"write={WRITE} already_in_db={len(seen)}")

    scanned = probate_n = in_market = 0
    rows, old_streak, gaps = [], 0, 0
    tid = edge
    while tid > 0 and old_streak < OLD_STREAK_STOP and gaps < 60:
        rec = tc.fetch_detail(s, tid)
        tid -= 1
        time.sleep(POLITE)
        if rec is None:
            gaps += 1
            continue
        gaps = 0
        scanned += 1
        ps = rec.get("pub_start")
        if ps and ps < cutoff:
            old_streak += 1
            continue
        old_streak = 0
        if not tc.is_probate(rec):
            continue
        probate_n += 1
        if rec.get("county") not in tc.COUNTY_MARKETS:
            continue
        in_market += 1
        pdf_text = tc.fetch_attachment_text(s, rec["topics_id"])
        applicant, filed = tc.extract_applicant(pdf_text)
        sig = tc.to_signal_row(rec, applicant, filed)
        if not sig:
            time.sleep(POLITE)
            continue
        # County-wide inversion: resolve the decedent against the FULL
        # county roll and attach what they own. property_hint gets the best
        # resolved address (used downstream); resolved_parcels carries the
        # full list (live-ZIP hits power parcel-identity matching; non-live
        # hits are expansion intel).
        owner_index = owner_indexes.get(rec.get("county") or "")
        if owner_index:
            sig["raw_data"]["county_resolution_ran"] = True
            resolved = owner_index.resolve(sig["raw_data"]["decedent"])
            if resolved:
                sig["raw_data"]["resolved_parcels"] = resolved
                best = resolved[0]
                sig["property_hint"] = (f"{best['address']}, {best['city']} "
                                        f"{best['zip']}").strip(", ")
            # Heir/applicant resolution: if the named applicant (future PR)
            # owns county property, that's a probate_heir contact lead —
            # weak by doctrine (the link is inference, not court record).
            applicant_name = sig["raw_data"].get("applicant")
            if applicant_name:
                heir_hits = owner_index.resolve(applicant_name)
                if heir_hits:
                    sig["raw_data"]["resolved_heir_parcels"] = heir_hits
        # NOTE: dedupe-skip removed for upsert semantics — re-writing an
        # existing cause_number UPDATES it (merge-duplicates), which is how
        # previously-written signals gain resolved_parcels on re-runs.
        rows.append(sig)
        time.sleep(POLITE)

    n_resolved = sum(1 for r in rows if (r.get("raw_data") or {}).get("resolved_parcels"))
    n_live_hits = 0
    print(f"[topics] scanned={scanned} probate={probate_n} "
          f"in_market={in_market} new_rows={len(rows)} county_resolved={n_resolved}")
    for r in rows:
        for rp in (r.get("raw_data") or {}).get("resolved_parcels") or []:
            print(f"  RESOLVED: {r['raw_data']['decedent'][:30]:30} -> "
                  f"{rp['owner_name'][:36]:36} {rp['city'][:16]:16} {rp['zip']} "
                  f"{rp['strength']}{' EST' if rp['est_of'] else ''}")

    if WRITE:
        if not (SUPABASE_URL and SERVICE_KEY):
            print("  WRITE requested but creds missing — aborting.")
            sys.exit(1)
        n = 0
        for i in range(0, len(rows), 100):
            n += write_rows(rows[i:i + 100])
        print(f"[topics] WROTE {n} signals to {TABLE}")
    else:
        print("[topics] DRY RUN — sample rows:")
        for row in rows[:4]:
            print(json.dumps(row, indent=1)[:600])
        print(f"(total {len(rows)} rows would be written)")


if __name__ == "__main__":
    main()
