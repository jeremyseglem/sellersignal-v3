#!/usr/bin/env python3
"""
Greenwich CT town-wide owner roll — emits the Maricopa CSV schema so
CountyOwnerIndex.from_maricopa_roll loads it (apn,owner_name,address,zip,
city,puc). acct = Link (== parcels_v3.pin for CT_FAIRFIELD). puc='01' for
State_Use 1xx residential so the loader's RES-first ordering works.

USAGE: OUT=/tmp/ct-roll.csv.gz python3 scripts/build_ct_roll.py
"""
import csv, gzip, json, os, time, urllib.parse, urllib.request

BASE = os.environ.get("CT_PARCELS_URL",
    "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/"
    "Connecticut_State_Parcel_Layer_2023/FeatureServer/0")
OUT = os.environ.get("OUT", "/tmp/ct-roll.csv.gz")
TOWN = os.environ.get("TOWN", "Greenwich")
UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Roll/1.0"}

def gj(params):
    url = f"{BASE}/query?{urllib.parse.urlencode(params)}"
    for a in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))
        except Exception:
            if a == 3: raise
            time.sleep(3 * (a + 1))

n, offset = 0, 0
with gzip.open(OUT, "wt", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["apn", "owner_name", "address", "zip", "city", "puc"])
    while True:
        d = gj({"where": f"Town_Name='{TOWN}'",
                "outFields": "Link,Owner,Co_Owner,Location,State_Use",
                "returnGeometry": "false", "orderByFields": "OBJECTID",
                "resultOffset": str(offset), "resultRecordCount": "2000", "f": "json"})
        feats = d.get("features", [])
        if not feats: break
        for f in feats:
            a = f.get("attributes") or {}
            apn = str(a.get("Link") or "").strip()
            owner = (a.get("Owner") or "").strip()
            co = (a.get("Co_Owner") or "").strip()
            if co and co.upper() not in owner.upper():
                owner = f"{owner} & {co}"
            if not apn or not owner: continue
            use = (a.get("State_Use") or "").strip()
            w.writerow([apn, owner, (a.get("Location") or "").strip(), "", TOWN,
                        "01" if use.startswith("1") else (use or "OTH")])
            n += 1
        offset += len(feats)
        if len(feats) < 2000: break
print(f"[roll] wrote {n:,} rows -> {OUT}")
