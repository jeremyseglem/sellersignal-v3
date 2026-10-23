"""
Buildable-ZIP scorer — the ZIP builder's proactive intake valve.

Ranks every UNCOVERED ZIP in counties where we already operate by
  score = source_grade × (ZHVI × for-sale inventory)   [$ volume on market]

Data (all free, no key, no login — bootstrap rule):
  - Our coverage:  GET https://sellersignal.co/api/coverage  (public)
  - Median value:  Zillow ZHVI by ZIP (monthly CSV, carries State+CountyName)
  - Inventory:     Zillow for-sale inventory by ZIP (monthly CSV)
  - Demand:        GET /api/notifications/admin/waitlist-summary
                   (expansion_request rows; needs ADMIN_KEY env)

Design decisions (recorded so reruns stay honest):
  - County sets per market are derived EMPIRICALLY: look up our own
    covered ZIPs in the ZHVI file and collect their CountyName values.
    No hand-typed county names (the WI_MILWAUKEE lesson: the market is
    actually Door/Dane/North Shore, not Milwaukee city).
  - Source grades come from the 2026-10-23 transfer-feed audit
    (claude/TRANSFER_FEED_MATRIX.md). A = transfer detector SHIPPED;
    B = feed verified, build pending; C = workable/high-per-unit-cost;
    D = weak/unverified. Multipliers 1.0/0.8/0.6/0.4.
  - Luxury-fit floor: 25th percentile of OUR covered ZIPs' ZHVI —
    empirical, not invented. ZIPs under it are listed but flagged.
  - Any ZIP with expansion_request demand gets surfaced regardless of
    score, with its waiting-email count.

Output: scored CSV + a markdown candidate block for ZIP_BUILD_QUEUE.md.
Founders still approve; the deputy wires max 2/Saturday; Warden verifies.

Usage:
  python3 scripts/score_buildable_zips.py [--out DIR]
  env: ADMIN_KEY (optional — demand check skipped without it)
"""
import argparse
import csv
import io
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import date

ENGINE = "https://sellersignal.co"
ZHVI_URL = ("https://files.zillowstatic.com/research/public_csvs/zhvi/"
            "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")
INVT_URL = ("https://files.zillowstatic.com/research/public_csvs/invt_fs/"
            "Zip_invt_fs_uc_sfrcondo_sm_month.csv")

# Transfer-feed audit grades (claude/TRANSFER_FEED_MATRIX.md, 2026-10-23).
# Grades reflect expansion READINESS: how cheap is a new ZIP in this
# market given the feeds we have verified or shipped.
GRADES = {
    "WA_KING": "A", "CO_DENVER": "A",                     # detector shipped
    "WI_MILWAUKEE": "B",                                   # WI RETR statewide (probe out)
    "MN_HENNEPIN": "B", "CO_BOULDER": "B",
    "FL_COLLIER": "B", "FL_PALM_BEACH": "B", "FL_INDIAN_RIVER": "B",
    "NC_WAKE": "B", "WA_SNOHOMISH": "B", "AZ_MARICOPA": "B",
    "MA_NANTUCKET": "C", "MA_DUKES": "C", "MA_MIDDLESEX": "C",
    "MA_ESSEX": "C", "MA_NORFOLK": "C", "MA_PLYMOUTH": "C",
    "TX_TRAVIS": "C", "TX_DALLAS": "C", "TX_COLLIN": "C",
    "CT_FAIRFIELD": "C", "CT_LITCHFIELD": "C",
    "NC_BUNCOMBE": "D", "CO_ARAPAHOE": "D", "CO_PITKIN": "D",
    "TN_DAVIDSON": "D", "CA_SANTACLARA": "D",
    "MT_GALLATIN": "D", "MT_FLATHEAD": "D", "MT_MISSOULA": "D",
    "MT_PARK": "D", "MT_CARBON": "D", "MT_LAKE": "D", "MT_RAVALLI": "D",
}
GRADE_MULT = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4}


def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "overture-zip-scorer"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_num(row, month_cols, window=3):
    """Mean of the last `window` non-empty monthly values."""
    vals = []
    for c in reversed(month_cols):
        v = row.get(c)
        if v not in (None, ""):
            try:
                vals.append(float(v))
            except ValueError:
                continue
        if len(vals) >= window:
            break
    return statistics.mean(vals) if vals else None


def load_zillow(buf):
    rdr = csv.DictReader(io.StringIO(buf.decode("utf-8-sig")))
    month_cols = [c for c in rdr.fieldnames if c[:2] == "20" and "-" in c]
    rows = {}
    for r in rdr:
        if r.get("RegionType") != "zip":
            continue
        z = r["RegionName"].zfill(5)
        rows[z] = {
            "state": r.get("State") or "",
            "county": r.get("CountyName") or "",
            "city": r.get("City") or "",
            "metro": r.get("Metro") or "",
            "val": latest_num(r, month_cols),
        }
    return rows, month_cols[-1] if month_cols else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratch/zip_scorer")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    print("1/5 coverage …", flush=True)
    coverage = json.loads(fetch(f"{ENGINE}/api/coverage", 60))
    if isinstance(coverage, dict):   # endpoint wraps the list
        coverage = (coverage.get("zips") or coverage.get("coverage")
                    or coverage.get("data") or [])
    covered = {c["zip_code"]: c for c in coverage}
    print(f"    {len(covered)} covered ZIPs, "
          f"{len({c['market_key'] for c in coverage})} markets")

    print("2/5 Zillow ZHVI …", flush=True)
    zhvi, zhvi_month = load_zillow(fetch(ZHVI_URL))
    print(f"    {len(zhvi)} ZIPs, latest month {zhvi_month}")

    print("3/5 Zillow inventory …", flush=True)
    invt_rdr = csv.DictReader(io.StringIO(fetch(INVT_URL).decode("utf-8-sig")))
    inv_months = [c for c in invt_rdr.fieldnames if c[:2] == "20" and "-" in c]
    invt = {}
    for r in invt_rdr:
        if r.get("RegionType") != "zip":
            continue
        invt[r["RegionName"].zfill(5)] = latest_num(r, inv_months)

    # Empirical county map: market_key -> {(state, county), ...} from OUR zips
    mk_counties = defaultdict(set)
    missing_in_zhvi = []
    for z, c in covered.items():
        zr = zhvi.get(z)
        if zr and zr["county"]:
            mk_counties[c["market_key"]].add((zr["state"], zr["county"]))
        else:
            missing_in_zhvi.append(z)
    county_to_mk = {}
    for mk, pairs in mk_counties.items():
        for p in pairs:
            county_to_mk.setdefault(p, set()).add(mk)

    # Luxury floor: 25th pct of covered ZIPs' ZHVI
    cov_vals = sorted(v["val"] for z, v in ((z, zhvi.get(z)) for z in covered)
                      if v and v["val"])
    floor = cov_vals[len(cov_vals) // 4] if cov_vals else 0

    print("4/5 demand …", flush=True)
    demand = {}
    admin_key = os.environ.get("ADMIN_KEY")
    if admin_key:
        req = urllib.request.Request(
            f"{ENGINE}/api/notifications/admin/waitlist-summary",
            headers={"X-Admin-Key": admin_key})
        try:
            wl = json.loads(urllib.request.urlopen(req, timeout=60).read())
            for e in wl.get("zips", []):
                n = e["by_source"].get("expansion_request", 0)
                if n:
                    demand[e["zip_code"]] = n
        except Exception as ex:
            print(f"    demand check failed ({ex}) — continuing without")
    else:
        print("    ADMIN_KEY not set — demand check skipped")
    print(f"    {len(demand)} ZIPs with expansion requests")

    print("5/5 scoring …", flush=True)
    out_rows = []
    for z, zr in zhvi.items():
        if z in covered:
            continue
        key = (zr["state"], zr["county"])
        mks = county_to_mk.get(key)
        if not mks:
            continue
        mk = sorted(mks)[0]
        grade = GRADES.get(mk, "D")
        val, inv = zr["val"], invt.get(z)
        if not val or not inv:
            continue
        volume = val * inv
        score = volume * GRADE_MULT[grade]
        out_rows.append({
            "zip": z, "market_key": mk, "grade": grade,
            "city": zr["city"], "state": zr["state"], "county": zr["county"],
            "zhvi": round(val), "for_sale_inventory": round(inv, 1),
            "dollar_volume_on_market": round(volume),
            "score": round(score),
            "above_luxury_floor": val >= floor,
            "expansion_requests": demand.get(z, 0),
        })
    out_rows.sort(key=lambda r: (-r["expansion_requests"], -r["score"]))

    csv_path = os.path.join(args.out, f"buildable_zips_{date.today()}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # Markdown candidate block for ZIP_BUILD_QUEUE.md
    md = [f"## Candidates — scored {date.today()} "
          f"(ZHVI {zhvi_month}; luxury floor ${floor:,.0f} = 25th pct of our fabric)",
          "", "| rank | zip | market | grade | city | ZHVI | inventory "
          "| $ on market | floor | requests |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    shown = [r for r in out_rows if r["above_luxury_floor"] or r["expansion_requests"]][:25]
    for i, r in enumerate(shown, 1):
        md.append(f"| {i} | {r['zip']} | {r['market_key']} | {r['grade']} "
                  f"| {r['city']}, {r['state']} | ${r['zhvi']:,} "
                  f"| {r['for_sale_inventory']} "
                  f"| ${r['dollar_volume_on_market']/1e6:,.1f}M "
                  f"| {'✓' if r['above_luxury_floor'] else '✗'} "
                  f"| {r['expansion_requests'] or ''} |")
    md_path = os.path.join(args.out, f"queue_block_{date.today()}.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"\nDONE {len(out_rows)} candidates scored "
          f"({sum(1 for r in out_rows if r['above_luxury_floor'])} above floor)")
    print(f"  csv: {csv_path}\n  md:  {md_path}")
    if missing_in_zhvi:
        print(f"  note: {len(missing_in_zhvi)} covered ZIPs absent from ZHVI "
              f"(county map built from the rest): {missing_in_zhvi[:10]}")
    for r in shown[:10]:
        print(f"  {r['zip']} {r['market_key']:<14} {r['grade']} "
              f"${r['zhvi']:>9,} × {r['for_sale_inventory']:>6} "
              f"= ${r['dollar_volume_on_market']/1e6:,.1f}M "
              f"{'REQ:' + str(r['expansion_requests']) if r['expansion_requests'] else ''}")


if __name__ == "__main__":
    sys.exit(main())
