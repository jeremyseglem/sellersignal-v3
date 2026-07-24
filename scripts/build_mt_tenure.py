#!/usr/bin/env python3
"""
Montana tenure backfill — ORION per-county SQL Server extract -> parcels_v3.tenure_years

WHY THIS EXISTS
  MT tenure (deed/transfer dates) lives ONLY in the Montana DOR ORION per-county
  databases, shipped as detached SQL Server .mdf files at
  ftpgeoinfo.msl.mt.gov/.../ORION_SQLDatabases/COUNTY{n}.ZIP. The statewide
  Cadastral FeatureServer and the StatewideCama.gdb extract carry current owner
  + value but NO transfer date (verified 2026-07-23). The per-parcel Property
  Card page (svc.mt.gov) is a JS SPA with no JSON API. So the ONLY machine route
  to MT tenure is: restore the county .mdf, read dbo.Deed joined to dbo.Property.

  Without tenure, the aging-trust (>=10yr) and llc-long-hold (>=7yr) selectors
  return empty — which is why the six MT ZIPs launched 2026-07-23 with absentee
  buckets full but trust/llc at zero. This module fills that gap.

DATA MODEL (confirmed against Gallatin COUNTY6.ZIP, 2026-07-24)
  dbo.Property : PropertyID (PK), GeoCode (17-digit dashed, e.g.
                 '06-0602-29-4-01-03-0000'), TaxYear, Addr_*, PropType
  dbo.Deed     : DeedID, PropertyID (FK), DeedDate, RecordedDate, DocType,
                 DocType_Desc, Book, Page, DocNumber   (216k rows in Gallatin)
  Join Deed.PropertyID -> Property.PropertyID -> Property.GeoCode.
  parcels_v3.pin is the UNDASHED geocode ('060602294010300000'), so we strip
  dashes to match.

  tenure = years between MAX(DeedDate) per geocode and today. We take the most
  recent deed as the current owner's acquisition (most recent transfer). Future-
  dated and pre-1900 rows are DOR data-entry junk and are dropped.

COUNTY CODES: Gallatin=6, Madison=25, Flathead=7.

EXECUTION ENVIRONMENT
  Requires a reachable SQL Server able to ATTACH the .mdf, plus the ODBC 18
  driver. This does NOT run on Railway (Python/Postgres shop). It runs wherever
  SQL Server can be stood up — a local/container host or an ephemeral build box.
  It talks to production Supabase over the same REST client the app uses, so the
  OUTPUT (tenure_years in parcels_v3) lands in prod; the SQL Server is a
  transient extraction tool, never a production dependency.

  Setup that this module assumes is already done (see SESSION log / MANIFESTO):
    - SQL Server 2022 running, ODBC Driver 18 installed
    - env MSSQL_HOST (default 127.0.0.1,1433), MSSQL_SA_PASSWORD
    - env SUPABASE_URL, SUPABASE_SERVICE_KEY  (writes parcels_v3)

USAGE
  # one county at a time; downloads mdf if not already local
  MSSQL_SA_PASSWORD=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
    python3 scripts/build_mt_tenure.py --county 6
  # dry run (extract + report, no DB writes)
  ... python3 scripts/build_mt_tenure.py --county 6 --dry-run
  # limit to specific ZIPs (parcels_v3 filter) — default: all MT parcels in county
  ... python3 scripts/build_mt_tenure.py --county 6 --zips 59715,59718
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
import zipfile

FTP = ("https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Cadastral/"
       "ORION_SQLDatabases/COUNTY{n}.ZIP")
COUNTY_NAME = {6: "Gallatin", 25: "Madison", 7: "Flathead"}
WORK = os.environ.get("MT_TENURE_WORK", "/tmp/mt_orion")
MSSQL_HOST = os.environ.get("MSSQL_HOST", "127.0.0.1,1433")
MSSQL_PWD = os.environ.get("MSSQL_SA_PASSWORD", "")

MIN_YEAR = 1900          # drop pre-1900 deed junk
MAX_DATE = datetime.date.today()   # drop future-dated deed junk


def _download_mdf(county: int) -> str:
    os.makedirs(WORK, exist_ok=True)
    mdf = os.path.join(WORK, f"county{county}.mdf")
    if os.path.exists(mdf) and os.path.getsize(mdf) > 1_000_000:
        print(f"[tenure] county{county}.mdf already local ({os.path.getsize(mdf):,} B)")
        return mdf
    zp = os.path.join(WORK, f"county{county}.zip")
    if not os.path.exists(zp):
        url = FTP.format(n=county)
        print(f"[tenure] downloading {url}")
        subprocess.run(["curl", "-sSL", "-o", zp, url], check=True)
    print(f"[tenure] extracting {zp}")
    with zipfile.ZipFile(zp) as z:
        inner = [n for n in z.namelist() if n.lower().endswith(".mdf")][0]
        z.extract(inner, WORK)
        os.replace(os.path.join(WORK, inner), mdf)
    return mdf


def _attach_and_extract(county: int, mdf: str) -> dict[str, datetime.date]:
    """Return {undashed_geocode: most_recent_deed_date} for the county."""
    import pyodbc
    # SQL Server must own the file; copy into its userdata dir
    srv_dir = "/var/opt/mssql/userdata"
    os.makedirs(srv_dir, exist_ok=True)
    srv_mdf = os.path.join(srv_dir, f"county{county}.mdf")
    if not os.path.exists(srv_mdf):
        subprocess.run(["cp", mdf, srv_mdf], check=True)
        subprocess.run(["chown", "mssql:mssql", srv_mdf], check=False)
    db = f"c{county}"
    cs = (f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={MSSQL_HOST};"
          f"UID=sa;PWD={MSSQL_PWD};Encrypt=no;TrustServerCertificate=yes;"
          f"Connection Timeout=60")
    c = pyodbc.connect(cs, autocommit=True)
    cur = c.cursor()
    cur.execute(
        f"IF DB_ID('{db}') IS NULL CREATE DATABASE {db} "
        f"ON (FILENAME='{srv_mdf}') FOR ATTACH_REBUILD_LOG;")
    cur.execute(f"""
        SELECT p.GeoCode, MAX(d.DeedDate) AS last_deed
        FROM {db}.dbo.Property p
        JOIN {db}.dbo.Deed d ON d.PropertyID = p.PropertyID
        WHERE d.DeedDate IS NOT NULL
        GROUP BY p.GeoCode
    """)
    out: dict[str, datetime.date] = {}
    dropped = 0
    for geo, dt in cur.fetchall():
        if not geo or not dt:
            continue
        d = dt.date() if hasattr(dt, "date") else dt
        if d.year < MIN_YEAR or d > MAX_DATE:
            dropped += 1
            continue
        pin = geo.replace("-", "").strip()
        out[pin] = d
    c.close()
    print(f"[tenure] {COUNTY_NAME[county]}: {len(out):,} parcels with valid deed "
          f"date ({dropped:,} junk dropped)")
    return out


def _supabase():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def _apply(county: int, tenure: dict[str, datetime.date],
           zips: list[str] | None, dry_run: bool):
    supa = _supabase()
    # Pull MT parcels for this county's ZIPs from parcels_v3, page through, match by pin.
    market_zips = {
        6:  ["59715", "59718", "59714", "59730", "59716"],
        25: ["59716"],
        7:  ["59937"],
    }[county]
    if zips:
        market_zips = [z for z in market_zips if z in zips]

    today = datetime.date.today()
    updated = matched = missing = 0
    for z in market_zips:
        rows, start = [], 0
        while True:
            resp = (supa.table("parcels_v3")
                    .select("pin,tenure_years")
                    .eq("zip_code", z).range(start, start + 999).execute())
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            start += 1000
        updates = []
        for r in rows:
            pin = str(r["pin"])
            d = tenure.get(pin)
            if not d:
                missing += 1
                continue
            matched += 1
            yrs = round((today - d).days / 365.25, 1)
            if r.get("tenure_years") != yrs:
                updates.append({
                    "pin": pin,
                    "tenure_years": yrs,
                    "last_transfer_date": d.isoformat(),
                })
        if dry_run:
            print(f"[tenure] {z}: {len(rows)} parcels, {matched} matched so far, "
                  f"{len(updates)} would update (DRY RUN)")
            continue
        for i in range(0, len(updates), 500):
            supa.table("parcels_v3").upsert(
                updates[i:i + 500], on_conflict="pin").execute()
        updated += len(updates)
        print(f"[tenure] {z}: {len(rows)} parcels, {len(updates)} tenure updates written")
    print(f"[tenure] county {county} done: matched={matched} "
          f"missing={missing} written={updated}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", type=int, required=True, choices=[6, 25, 7])
    ap.add_argument("--zips", default=None,
                    help="comma-separated ZIP filter (default: all in county)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not MSSQL_PWD:
        sys.exit("MSSQL_SA_PASSWORD required")
    mdf = _download_mdf(a.county)
    tenure = _attach_and_extract(a.county, mdf)
    zips = [z.strip() for z in a.zips.split(",")] if a.zips else None
    _apply(a.county, tenure, zips, a.dry_run)


if __name__ == "__main__":
    main()
