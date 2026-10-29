#!/usr/bin/env python3
"""
Load King County's public sales file into sales_history_v3 (Harvester
queue #10). DRY RUN BY DEFAULT — WRITE=1 is a founder go.

  1. Download Real Property Sales.zip + Lookup.zip (public, no login).
  2. Fabric pins: GET /api/admin/export-fabric/{zip}?table=parcels for
     every live WA_KING ZIP (from /api/coverage), or the ZIPS list.
     (The Account file's ZipCode is the tax-bill MAILING ZIP, not the
     situs ZIP, so it cannot select fabric pins.)
  3. Parse + filter EXTR_RPSale.csv (backend/harvesters/kc_sales_file.py):
     fabric pins only, sale_date >= SINCE, deduped per
     (pin, recording_number).
  4. POST batches to /api/harvest/ingest-sales-history (insert-only;
     dry_run unless WRITE=1). Never runs transfer-detect.

Env: SS_ADMIN_KEY (required), SS_BASE (default https://sellersignal.co),
WRITE ("1" to write; anything else = dry run), SINCE (YYYY-MM-DD,
default 2015-01-01), ZIPS (comma list; default all live WA_KING),
KC_DATA (dir holding the extracted CSVs; downloaded when missing),
BATCH (rows per call, default 1000).

Exit codes: 0 ok · 2 silent-zero guard (every call failed and nothing
was accepted) · 3 setup failure (no pins / no file).
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.harvesters.kc_sales_file import (  # noqa: E402
    dedupe_rows, iter_sales, load_lookups,
)

BASE = os.environ.get("SS_BASE", "https://sellersignal.co").rstrip("/")
KEY = os.environ.get("SS_ADMIN_KEY", "")
WRITE = os.environ.get("WRITE", "0").strip() == "1"
SINCE = date.fromisoformat(os.environ.get("SINCE") or "2015-01-01")
ZIPS = [z.strip() for z in (os.environ.get("ZIPS") or "").split(",") if z.strip()]
KC_DATA = Path(os.environ.get("KC_DATA", "/tmp/kc-data"))
BATCH = int(os.environ.get("BATCH", "1000"))
H = {"X-Admin-Key": KEY}
AQUA = "https://aqua.kingcounty.gov/extranet/assessor/"
FILES = {"EXTR_RPSale.csv": "Real%20Property%20Sales.zip",
         "EXTR_LookUp.csv": "Lookup.zip"}


def log(m):
    print(m, flush=True)


def _get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=180, **kw)
            if r.status_code in (502, 503, 504):
                raise requests.HTTPError(str(r.status_code))
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == 3:
                raise
            log(f"  retry {attempt + 1} {url[:90]}: {e}")
            time.sleep(5 * (attempt + 1))


def ensure_files():
    KC_DATA.mkdir(parents=True, exist_ok=True)
    for csv_name, zip_name in FILES.items():
        if (KC_DATA / csv_name).exists():
            continue
        log(f"download {zip_name}")
        r = _get(AQUA + zip_name, headers={"User-Agent": "Mozilla/5.0"})
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extract(csv_name, KC_DATA)


def fabric_pins() -> dict:
    zips = ZIPS
    if not zips:
        cov = _get(f"{BASE}/api/coverage").json().get("coverage") or []
        zips = sorted(c["zip_code"] for c in cov
                      if c.get("market_key") == "WA_KING")
    pin_zip = {}
    for z in zips:
        off = 0
        while True:
            body = _get(f"{BASE}/api/admin/export-fabric/{z}", headers=H,
                        params={"table": "parcels", "offset": off,
                                "limit": 5000}).json()
            rows = body.get("rows") or []
            for r in rows:
                pin_zip[r["pin"]] = z
            off += len(rows)
            if len(rows) < 1000:
                break
        log(f"  fabric {z}: {sum(1 for v in pin_zip.values() if v == z)} pins")
    return pin_zip


def main() -> int:
    if not KEY:
        log("SS_ADMIN_KEY not set")
        return 3
    log(f"[kc_sales_history] write={WRITE} since={SINCE} "
        f"zips={'all WA_KING' if not ZIPS else ZIPS}")
    ensure_files()
    lookups = load_lookups((KC_DATA / "EXTR_LookUp.csv")
                           .read_text(encoding="latin-1"))
    log(f"lookups: {len(lookups['instrument'])} instruments, "
        f"{len(lookups['reason'])} reasons")
    pin_zip = fabric_pins()
    if not pin_zip:
        log("no fabric pins — nothing to do")
        return 3
    unknown: dict = {}
    with open(KC_DATA / "EXTR_RPSale.csv", encoding="latin-1", newline="") as f:
        rows = list(iter_sales(f, lookups, pins=set(pin_zip), since=SINCE,
                               unknown=unknown))
    rows, dups = dedupe_rows(rows)
    by_zip_file = Counter(pin_zip[r["pin"]] for r in rows)
    log(f"file rows on fabric pins since {SINCE}: {len(rows)} "
        f"(dupes dropped {dups}; unknown codes {unknown})")

    tot = Counter()
    new_by_zip = Counter()
    calls = errs = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        calls += 1
        try:
            r = requests.post(f"{BASE}/api/harvest/ingest-sales-history",
                              headers=H, timeout=300,
                              json={"market_key": "WA_KING",
                                    "dry_run": not WRITE, "rows": batch})
            r.raise_for_status()
            b = r.json()
        except Exception as e:
            errs += 1
            log(f"  ERR batch {i}: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(10)
            continue
        for k in ("rows_in", "dup_in_batch", "not_in_fabric",
                  "already_present", "new_rows", "inserted"):
            tot[k] += b.get(k) or 0
        new_by_zip.update(b.get("new_by_zip") or {})
        if calls % 25 == 0:
            log(f"  {calls} calls: {dict(tot)}")
        time.sleep(0.5)

    log("per ZIP (file rows / new rows):")
    for z in sorted(by_zip_file):
        log(f"  {z}: {by_zip_file[z]} / {new_by_zip.get(z, 0)}")
    log(f"DONE write={WRITE} calls={calls} errors={errs} {json.dumps(dict(tot))}")
    if errs and errs == calls:
        log("silent-zero guard: every call failed")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
