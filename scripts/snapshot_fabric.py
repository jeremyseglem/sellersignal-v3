"""
Monthly frozen snapshot of the parcel fabric and the match table.

Why: the platform keeps only the CURRENT owner / tenure / band for each
parcel, and King County overwrites the owner with the buyer within weeks
of a sale. A model that predicts sales must be trained on what was known
BEFORE each sale (point-in-time features); without frozen history every
training row leaks the outcome (the 2026-10-22 hindcast's reverse-causation
trap). Each month this writes an immutable copy that nobody can rebuild
later. Founder go: Jeremy 2026-10-29 ("yes lets do it").

What it writes (Supabase Storage, PRIVATE bucket `fabric-snapshots`):
    <label>/parcels/<zip>.jsonl.gz   one per live ZIP (point-in-time row)
    <label>/matches.jsonl.gz         raw_signal_matches_v3, all rows
    <label>/manifest.json            row counts + sha256 per file; written
                                     LAST, so its presence = complete
<label> defaults to the UTC date (YYYY-MM-DD).

Rules:
  - Read-only on the database. The only write is to Storage.
  - Immutable: refuses to write a label whose manifest already exists
    (set FORCE=1 to override — founder call only).
  - Columns: the intended list below, intersected with what the live table
    actually returns, so an unapplied migration never breaks the run and no
    field is ever invented. Geometry/polygon columns are not included.
  - Pagination: parcels per ZIP by pin, matches by id keyset (no deep
    offsets — the 57014 statement-timeout lesson). 1,000 rows per page.
  - DRY_RUN=1: counts only, nothing uploaded.

Env: SUPABASE_URL, SUPABASE_SERVICE_KEY (repo secrets already used by the
harvest workflows), DRY_RUN (default 1), SNAPSHOT_LABEL, ZIPS (comma list,
default all live), FORCE.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import os
import sys
import time

import requests

BUCKET = "fabric-snapshots"
PAGE = 1000

PARCEL_COLUMNS = [
    "pin", "zip_code", "market_key",
    "owner_name_raw", "owner_name", "owner_type",
    "owner_address", "owner_city", "owner_state", "owner_zip",
    "total_value", "land_value", "building_value",
    "sqft", "year_built", "acres", "prop_type",
    "last_transfer_date", "last_transfer_price", "tenure_years",
    "is_absentee", "is_out_of_state", "is_vacant_land",
    "band", "signal_family", "parent_pin",
    "bedrooms", "bathrooms", "stories", "year_renovated",
    "waterfront", "view_rating",
    "data_freshness_at", "updated_at",
]
MATCH_COLUMNS = [
    "id", "raw_signal_id", "pin", "match_strength", "match_method",
    "match_review_status", "matched_at",
]


class Client:
    def __init__(self, url: str, key: str, session=None):
        self.url = url.rstrip("/")
        self.key = key
        self.s = session or requests.Session()
        self.h = {"apikey": key, "Authorization": f"Bearer {key}"}

    def _get(self, path, params=None, headers=None, retries=4):
        last = None
        for a in range(retries):
            try:
                r = self.s.get(f"{self.url}{path}", params=params,
                               headers={**self.h, **(headers or {})},
                               timeout=120)
                if r.status_code < 500:
                    return r
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.RequestException as e:
                last = str(e)
            time.sleep(3 * (a + 1))
        raise RuntimeError(f"GET {path} failed: {last}")

    def rows(self, table, params):
        r = self._get(f"/rest/v1/{table}", params=params)
        if r.status_code != 200:
            raise RuntimeError(f"{table}: HTTP {r.status_code} {r.text[:300]}")
        return r.json()

    def live_columns(self, table, wanted):
        """Intersect the intended list with the columns the table returns."""
        sample = self.rows(table, {"select": "*", "limit": "1"})
        if not sample:
            return list(wanted)
        have = set(sample[0].keys())
        cols = [c for c in wanted if c in have]
        missing = [c for c in wanted if c not in have]
        if missing:
            print(f"[snapshot] {table}: not in live table, skipped: {missing}")
        return cols

    def live_zips(self):
        out = self.rows("zip_coverage_v3", {
            "select": "zip_code,market_key", "status": "eq.live",
            "order": "zip_code"})
        return [(r["zip_code"], r["market_key"]) for r in out]

    def parcels(self, zip_code, cols):
        last = ""
        while True:
            p = {"select": ",".join(cols), "zip_code": f"eq.{zip_code}",
                 "order": "pin", "limit": str(PAGE)}
            if last:
                p["pin"] = f"gt.{last}"
            batch = self.rows("parcels_v3", p)
            yield from batch
            if len(batch) < PAGE:
                return
            last = batch[-1]["pin"]

    def matches(self, cols):
        last = 0
        while True:
            batch = self.rows("raw_signal_matches_v3", {
                "select": ",".join(cols), "id": f"gt.{last}",
                "order": "id", "limit": str(PAGE)})
            yield from batch
            if len(batch) < PAGE:
                return
            last = batch[-1]["id"]

    # ---- storage ----
    def object_exists(self, path):
        r = self._get(f"/storage/v1/object/{BUCKET}/{path}")
        return r.status_code == 200

    def ensure_bucket(self):
        r = self._get(f"/storage/v1/bucket/{BUCKET}")
        if r.status_code == 200:
            if r.json().get("public"):
                raise RuntimeError(f"bucket {BUCKET} is PUBLIC — refusing")
            return
        r = self.s.post(f"{self.url}/storage/v1/bucket", headers=self.h,
                        json={"id": BUCKET, "name": BUCKET, "public": False},
                        timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create bucket: HTTP {r.status_code} {r.text[:300]}")

    def upload(self, path, data: bytes, ctype):
        for a in range(4):
            r = self.s.post(f"{self.url}/storage/v1/object/{BUCKET}/{path}",
                            headers={**self.h, "Content-Type": ctype,
                                     "x-upsert": "true"},
                            data=data, timeout=300)
            if r.status_code in (200, 201):
                return
            time.sleep(3 * (a + 1))
        raise RuntimeError(f"upload {path}: HTTP {r.status_code} {r.text[:300]}")


def to_jsonl_gz(rows) -> tuple[bytes, int]:
    buf = io.BytesIO()
    n = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for row in rows:
            gz.write((json.dumps(row, sort_keys=True, default=str) + "\n").encode())
            n += 1
    return buf.getvalue(), n


def run(client: Client, label: str, dry_run: bool, zips_filter=None,
        force=False) -> dict:
    if not dry_run:
        client.ensure_bucket()
        if client.object_exists(f"{label}/manifest.json") and not force:
            raise RuntimeError(f"snapshot {label} already exists (immutable); "
                               "set FORCE=1 only on a founder's go")

    pcols = client.live_columns("parcels_v3", PARCEL_COLUMNS)
    mcols = client.live_columns("raw_signal_matches_v3", MATCH_COLUMNS)
    zips = client.live_zips()
    if zips_filter:
        zips = [z for z in zips if z[0] in zips_filter]

    files = {}
    by_market = {}
    for zip_code, market in zips:
        data, n = to_jsonl_gz(client.parcels(zip_code, pcols))
        path = f"{label}/parcels/{zip_code}.jsonl.gz"
        files[path] = {"rows": n, "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest(),
                       "zip_code": zip_code, "market_key": market}
        by_market[market] = by_market.get(market, 0) + n
        if not dry_run:
            client.upload(path, data, "application/gzip")
        print(f"[snapshot] {zip_code} {market}: {n} parcels"
              f"{'' if dry_run else ' uploaded'}", flush=True)

    data, n = to_jsonl_gz(client.matches(mcols))
    path = f"{label}/matches.jsonl.gz"
    files[path] = {"rows": n, "bytes": len(data),
                   "sha256": hashlib.sha256(data).hexdigest()}
    if not dry_run:
        client.upload(path, data, "application/gzip")
    print(f"[snapshot] matches: {n}{'' if dry_run else ' uploaded'}", flush=True)

    manifest = {
        "label": label,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA"),
        "dry_run": dry_run,
        "parcel_columns": pcols,
        "match_columns": mcols,
        "zips": len(zips),
        "parcels_total": sum(v["rows"] for k, v in files.items() if "/parcels/" in k),
        "parcels_by_market": by_market,
        "matches_total": n,
        "files": files,
    }
    if not dry_run:
        client.upload(f"{label}/manifest.json",
                      json.dumps(manifest, indent=1).encode(), "application/json")
    return manifest


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing"); sys.exit(1)
    dry = os.environ.get("DRY_RUN", "1") != "0"
    label = (os.environ.get("SNAPSHOT_LABEL")
             or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
    zf = {z.strip() for z in os.environ.get("ZIPS", "").split(",") if z.strip()}
    m = run(Client(url, key), label, dry, zf or None,
            os.environ.get("FORCE") == "1")
    print(json.dumps({k: m[k] for k in ("label", "dry_run", "zips",
                                        "parcels_total", "matches_total",
                                        "parcels_by_market")}, indent=1))


if __name__ == "__main__":
    main()
