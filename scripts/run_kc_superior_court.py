#!/usr/bin/env python3
"""
King County Superior Court harvester runner — probate + divorce.

Since ~2026-04-23 KC's records portal requires a logged-in session for
case search (KC_PORTAL_USER / KC_PORTAL_PASS env). The harvester
(backend/harvesters/kc_superior_court.py) handles login + the redesigned
search form; this runner drives it over a date window and persists
RawSignals to raw_signals_v3 via merge-duplicate upsert (idempotent on
source_type + document_ref).

Env:
  SUPABASE_URL           https://eeqsbvizgpuehphiaslo.supabase.co
  SUPABASE_SERVICE_KEY   service-role key (write)
  KC_PORTAL_USER/PASS    portal login (read by the harvester)
  WRITE                  "1" to write; else dry run (default)
  SINCE_DAYS             lookback window in days (default 30). The
                         backlog drain uses a large value once
                         (e.g. 120 to cover the April→now gap).
  CASE_TYPES             comma list: probate,divorce (default both)
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.harvesters.kc_superior_court import KCSuperiorCourtHarvester  # noqa: E402
import requests  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
SINCE_DAYS = int(os.environ.get("SINCE_DAYS") or "30")
CASE_TYPES = [c.strip() for c in
              (os.environ.get("CASE_TYPES") or "probate,divorce").split(",")
              if c.strip()]
TABLE = "raw_signals_v3"


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def write_rows(rows: list) -> int:
    if not rows:
        return 0
    # dedupe within the batch on (source_type, document_ref)
    seen = {}
    for r in rows:
        seen[(r["source_type"], r["document_ref"])] = r
    deduped = list(seen.values())
    CHUNK = 200
    written = 0
    for i in range(0, len(deduped), CHUNK):
        batch = deduped[i:i + CHUNK]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**_headers(),
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            params={"on_conflict": "source_type,document_ref"},
            json=batch, timeout=180)
        if not resp.ok:
            print(f"  WRITE ERROR {resp.status_code}: {resp.text[:300]}")
            resp.raise_for_status()
        written += len(batch)
    return written


def main():
    end = date.today()
    start = end - timedelta(days=SINCE_DAYS)
    print(f"[kc_superior_court] window {start} → {end} "
          f"case_types={CASE_TYPES} write={WRITE}")

    harvester = KCSuperiorCourtHarvester(case_types=CASE_TYPES)
    rows = []
    by_type = {}
    for sig in harvester.harvest(since=start, until=end):
        d = sig.to_row()
        rows.append(d)
        by_type[d["signal_type"]] = by_type.get(d["signal_type"], 0) + 1

    print(f"[kc_superior_court] harvested {len(rows)} signals {by_type}")
    if not rows:
        # Zero across a multi-day window on a logged-in session is
        # suspicious (login or form break) — fail loudly so the cron alarms.
        print("[kc_superior_court] FATAL: zero signals harvested — "
              "failing loudly (login/form regression?)")
        sys.exit(1)

    if WRITE:
        n = write_rows(rows)
        print(f"[kc_superior_court] wrote {n} signals")
    else:
        print(f"[kc_superior_court] DRY RUN — would write {len(rows)}")


if __name__ == "__main__":
    main()
