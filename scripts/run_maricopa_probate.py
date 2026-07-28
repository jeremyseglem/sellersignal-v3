#!/usr/bin/env python3
"""
Maricopa County Superior Court — Probate docket enumeration harvester.

Walks PB{year}-{seq:06d} case numbers, fetches each caseInfo.asp page,
parses the party table, and writes decedent-estate probate signals to
raw_signals_v3. Guardianship / conservatorship / minor cases (also filed
under PB) are classified out — only Decedent+contact estates become
signals. Mirrors run_mt_district_court.py's cursor/skip/fail-loud shape,
minus Playwright: the Maricopa docket is plain HTTP GET, no TSPD, no
captcha gating the search.

Env:
  SUPABASE_URL           https://eeqsbvizgpuehphiaslo.supabase.co
  SUPABASE_SERVICE_KEY   service-role key (write) — GitHub secret
  WRITE                  "1" to write; anything else = dry run (default)
  YEAR                   sequence year (default: current year)
  MAX_MISS               consecutive not-found before stopping (default 40)
  MAX_CASES              hard cap on lookups per run (default 600)
  FULL_SWEEP             "1" to start at seq 1 (gap recovery)
"""

import os
import sys
import time
import re
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend",
                                "harvesters"))
sys.path.insert(0, os.path.dirname(__file__))
import maricopa_probate_court as mp   # noqa: E402
import requests                        # noqa: E402
from lib_county_resolve import CountyOwnerIndex  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
YEAR = int(os.environ.get("YEAR") or datetime.now().year)
MAX_MISS = int(os.environ.get("MAX_MISS") or "40")
MAX_CASES = int(os.environ.get("MAX_CASES") or "600")
FULL_SWEEP = os.environ.get("FULL_SWEEP", "0") == "1"
ERR_ABORT = 10

TABLE = "raw_signals_v3"
SOURCE = "maricopa_probate_court"
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/125.0 Safari/537.36")}


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    out, off = set(), 0
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=_headers(),
                         params={"source_type": f"eq.{SOURCE}",
                                 "select": "document_ref",
                                 "offset": off, "limit": 1000}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        out.update(row["document_ref"] for row in rows)
        if len(rows) < 1000:
            break
        off += 1000
    return out


def start_sequence(refs: set, year: int) -> int:
    """1 + highest PB sequence already stored for this year. document_ref
    shape: PB2026-000123 → year 2026, seq 123."""
    hi = 0
    for ref in refs:
        m = re.match(r"PB(\d{4})-(\d{6})", ref)
        if m and m.group(1) == str(year):
            hi = max(hi, int(m.group(2)))
    return hi + 1


def write_rows(rows: list) -> int:
    if not rows:
        return 0
    seen = {}
    for row in rows:
        seen[(row["source_type"], row["document_ref"])] = row
    deduped = list(seen.values())
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE}",
                      headers={**_headers(),
                               "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "source_type,document_ref"},
                      json=deduped, timeout=180)
    if not r.ok:
        print(f"  WRITE ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return len(deduped)


def fetch_case(session: requests.Session, year: int, seq: int) -> str:
    cn = f"PB{year}-{seq:06d}"
    r = session.get(mp.CASE_INFO, params={"caseNumber": cn}, timeout=45)
    r.raise_for_status()
    return r.text


def build_or_load_roll() -> "CountyOwnerIndex | None":
    """Build the county-wide owner roll once per run (or reuse a cached
    copy). Resolution against the full ~1.6M-parcel Assessor roll is what
    makes probate matches ACCURATE for trust-owned luxury parcels: the
    county's own record ties 'Marsha Nitchman' to 'NITCHMAN FAMILY TRUST',
    so the app-side matcher matches by parcel identity — no fuzzy
    surname-only guessing, zero false positives. Without resolution the
    2-token name gate rejects every trust-owned estate."""
    import subprocess
    roll_path = os.environ.get("MARICOPA_ROLL", "/tmp/maricopa-roll.csv.gz")
    if not os.path.exists(roll_path):
        print(f"[maricopa_probate] building county roll → {roll_path} "
              f"(~1.6M parcels, one-time per run)")
        builder = os.path.join(os.path.dirname(__file__),
                               "build_maricopa_county_roll.py")
        env = {**os.environ, "OUT": roll_path}
        r = subprocess.run([sys.executable, builder], env=env,
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0 or not os.path.exists(roll_path):
            print(f"[maricopa_probate] roll build FAILED: {r.stderr[-400:]}")
            return None
    try:
        idx = CountyOwnerIndex.from_maricopa_roll(roll_path)
        print(f"[maricopa_probate] county roll loaded: {idx.total} owner rows")
        return idx
    except Exception as e:
        print(f"[maricopa_probate] roll load failed: {e}")
        return None


def attach_resolution(row: dict, roll: "CountyOwnerIndex | None") -> dict:
    """Resolve the decedent against the county roll and attach
    resolved_parcels in the shape the app matcher's Layer 0 reads
    (acct/est_of/strength). Sets county_resolution_ran so a surname
    coincidence in a live ZIP can never produce a fuzzy match — resolution
    is authoritative about what the decedent owns."""
    if roll is None:
        return row
    decedent = row["party_names"][0]["raw"]
    # Assessor owner names are surname-first; the resolver tokenizes both
    # orders but the decedent string here is "First [Middle] Last".
    hits = roll.resolve(decedent, order="first_last")
    resolved = [{"acct": h["acct"], "est_of": h["est_of"],
                 "strength": h["strength"], "zip": h.get("zip"),
                 "owner_name": h.get("owner_name")}
                for h in hits]
    row["raw_data"]["resolved_parcels"] = resolved
    row["raw_data"]["county_resolution_ran"] = True
    return row


def main():
    print(f"[maricopa_probate] year={YEAR} write={WRITE} "
          f"max_miss={MAX_MISS} max_cases={MAX_CASES} full_sweep={FULL_SWEEP}")
    refs = existing_refs()
    stored_seqs = {int(m.group(2)) for ref in refs
                   if (m := re.match(r"PB(\d{4})-(\d{6})", ref))
                   and m.group(1) == str(YEAR)}
    seq = 1 if FULL_SWEEP else start_sequence(refs, YEAR)
    print(f"[maricopa_probate] resume at PB{YEAR}-{seq:06d} "
          f"(refs_in_db={len(refs)}, stored_this_year={len(stored_seqs)})")

    session = requests.Session()
    session.headers.update(UA)
    session.headers["Referer"] = f"{mp.BASE}/caseSearch.asp"

    roll = build_or_load_roll()
    resolved_in_zips = 0

    miss_streak = err_streak = looked = wrote = estates = guardianships = 0
    retried = set()
    batch = []

    while miss_streak < MAX_MISS and looked < MAX_CASES:
        if err_streak >= ERR_ABORT:
            print(f"[maricopa_probate] ABORT: {err_streak} consecutive errors "
                  f"at PB{YEAR}-{seq:06d} — portal unhealthy, cursor preserved.")
            break
        if seq in stored_seqs:
            seq += 1
            continue
        looked += 1
        try:
            html = fetch_case(session, YEAR, seq)
        except Exception as e:
            print(f"  PB{YEAR}-{seq:06d} fetch ERR {type(e).__name__}: {e}")
            if seq not in retried:
                retried.add(seq)
                time.sleep(3.0)
                continue
            err_streak += 1
            seq += 1
            continue

        case = mp.parse_case_detail(html)
        if not case:
            # Not a viewable case → frontier evidence (beyond last filed).
            miss_streak += 1
            err_streak = 0
            seq += 1
            continue

        miss_streak = 0
        err_streak = 0
        kind = mp.classify(case)
        if kind == "decedent_estate":
            row = mp.to_signal_row(case)
            if row:
                estates += 1
                row = attach_resolution(row, roll)
                nres = len(row["raw_data"].get("resolved_parcels") or [])
                if nres:
                    resolved_in_zips += 1
                st = row["raw_data"]["pr_status"]
                print(f"  PB{YEAR}-{seq:06d} ESTATE dec={row['party_names'][0]['raw'][:24]} "
                      f"[{st}] {row['event_date']} resolved={nres}")
                batch.append(row)
        elif kind == "guardianship":
            guardianships += 1

        if len(batch) >= 50 and WRITE:
            wrote += write_rows(batch)
            batch = []
        seq += 1
        time.sleep(0.5)

    if WRITE and batch:
        wrote += write_rows(batch)

    print(f"\n[maricopa_probate] looked={looked} estates={estates} "
          f"guardianships={guardianships} resolved_to_county_parcels={resolved_in_zips} "
          f"wrote={wrote} stopped_at=PB{YEAR}-{seq:06d} miss_streak={miss_streak}")

    if looked == 0:
        print("[maricopa_probate] FATAL: zero cases looked at — failing loudly")
        sys.exit(1)
    if not WRITE:
        print(f"[maricopa_probate] DRY RUN — would write {estates} signals")


if __name__ == "__main__":
    main()
