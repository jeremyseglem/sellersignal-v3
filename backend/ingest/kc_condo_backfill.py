"""
KC condo-unit backfill — pins, prop_type, and complex linkage from the
bulk assessor condo extract.

Why this exists (2026-07-26): KC's ArcGIS parcel layer carries ONE record
per condo complex (PIN = Major + '0000', the common-area parcel with the
building footprint). The individual unit PINs (Major + unit Minor) exist
only in the bulk extract 'Condo Complex and Units.zip'
(EXTR_CondoUnit2.csv, ~115k units). Result before this module: unit
parcels in parcels_v3 had no lat/lng (geometry backfill marked them
geocode_skipped — "not in source"), no prop_type, no lot polygon, and
were invisible/unclickable on the map while still being bucket-eligible.

What this module does, per WA_KING ZIP:
  1. Ensure the condo extract is downloaded + parsed (cached in-process;
     ~6.8 MB zip from aqua.kingcounty.gov, same host family as the seed
     builder's RPSale/RPAcct downloads).
  2. Find parcels_v3 rows whose PIN's Major appears in the extract's
     unit index (these are condo units by county truth data).
  3. Batch-query KC ArcGIS for each affected Major's complex parcel
     (PIN = Major + '0000') with returnCentroid — one centroid per
     building.
  4. Update the unit rows: prop_type='K', lat/lng = complex centroid
     (only where currently NULL — never clobber real geometry),
     parent_pin = complex PIN (defensive: skipped with a warning if
     migration 033 hasn't been applied).

Non-goals here: lot-polygon serving for units (map layer resolves the
parent's polygon at read time — separate change in map_data.py), and
non-KC condos (Dallas/Austin need their own source or a geocode
fallback).
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from typing import Optional

import httpx

CONDO_ZIP_URL = (
    "https://aqua.kingcounty.gov/extranet/assessor/"
    "Condo%20Complex%20and%20Units.zip"
)
KC_ARCGIS_URL = (
    "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/"
    "services/PARCEL_ADDRESS_PUB_AREA_3069/FeatureServer/0/query"
)
_UA = {"User-Agent": "Mozilla/5.0 (SellerSignal condo backfill)"}

# In-process caches — the extract is ~115k rows and changes weekly at
# most; one download per Railway process lifetime is plenty.
_UNIT_MAJORS: Optional[set[str]] = None          # majors that are condos
_UNIT_INDEX: Optional[dict[str, str]] = None     # unit PIN -> major
_CENTROID_CACHE: dict[str, tuple[float, float]] = {}   # major -> (lat,lng)
_NO_COMPLEX: set[str] = set()                    # majors with no ArcGIS rec


def _ensure_extract_loaded() -> tuple[set[str], dict[str, str]]:
    """Download + parse EXTR_CondoUnit2.csv once per process."""
    global _UNIT_MAJORS, _UNIT_INDEX
    if _UNIT_MAJORS is not None:
        return _UNIT_MAJORS, _UNIT_INDEX

    with httpx.Client(timeout=180, headers=_UA, follow_redirects=True) as c:
        r = c.get(CONDO_ZIP_URL)
        r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in zf.namelist() if n.startswith("EXTR_CondoUnit2")
                and n.endswith(".csv"))
    majors: set[str] = set()
    index: dict[str, str] = {}
    with zf.open(name) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8",
                                                 errors="replace"))
        for row in reader:
            major = (row.get("Major") or "").strip()
            minor = (row.get("Minor") or "").strip()
            if len(major) == 6 and len(minor) == 4:
                majors.add(major)
                index[major + minor] = major
    _UNIT_MAJORS, _UNIT_INDEX = majors, index
    return majors, index


def _fetch_complex_centroids(majors: list[str]) -> dict[str, tuple[float, float]]:
    """Batch-query ArcGIS for Major+'0000' complex parcels' centroids."""
    want = [m for m in majors
            if m not in _CENTROID_CACHE and m not in _NO_COMPLEX]
    CHUNK = 80
    with httpx.Client(timeout=60, headers=_UA) as c:
        for i in range(0, len(want), CHUNK):
            chunk = want[i:i + CHUNK]
            pins = ",".join(f"'{m}0000'" for m in chunk)
            params = {
                "where": f"PIN IN ({pins})",
                "outFields": "PIN",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "f": "json",
            }
            try:
                r = c.get(KC_ARCGIS_URL, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception:
                # Transient ArcGIS failure — leave these majors uncached so
                # a re-run retries them. Do NOT mark _NO_COMPLEX.
                time.sleep(1.0)
                continue
            found: set[str] = set()
            for f in data.get("features", []):
                pin = (f.get("attributes") or {}).get("PIN") or ""
                cen = f.get("centroid") or {}
                if len(pin) == 10 and "x" in cen and "y" in cen:
                    major = pin[:6]
                    _CENTROID_CACHE[major] = (cen["y"], cen["x"])
                    found.add(major)
            for m in chunk:
                if m not in found:
                    _NO_COMPLEX.add(m)
            time.sleep(0.3)
    return {m: _CENTROID_CACHE[m] for m in majors if m in _CENTROID_CACHE}


def backfill_condos_for_zip(supa, zip_code: str,
                            dry_run: bool = False) -> dict:
    """
    Identify condo-unit parcels in one ZIP via the extract, set
    prop_type='K', backfill lat/lng from the complex centroid where NULL,
    and write parent_pin (defensively).
    """
    majors, unit_index = _ensure_extract_loaded()

    rows: list = []
    PAGE = 1000
    off = 0
    while True:
        page = (supa.table("parcels_v3")
                    .select("pin,lat,lng,prop_type")
                    .eq("zip_code", zip_code)
                    .eq("market_key", "WA_KING")
                    .range(off, off + PAGE - 1)
                    .execute().data) or []
        rows.extend(page)
        if len(page) < PAGE:
            break
        off += PAGE

    units = [r for r in rows if unit_index.get(str(r["pin"]))]
    if not units:
        return {"zip_code": zip_code, "parcels": len(rows),
                "condo_units": 0, "updated": 0, "pinned": 0,
                "no_complex_geom": 0, "dry_run": dry_run}

    needed_majors = sorted({unit_index[str(r["pin"])] for r in units})
    centroids = _fetch_complex_centroids(needed_majors)

    updated = pinned = no_geom = parent_pin_ok = 0
    parent_pin_supported = True
    for r in units:
        pin = str(r["pin"])
        major = unit_index[pin]
        payload: dict = {}
        if (r.get("prop_type") or "").strip().upper() != "K":
            payload["prop_type"] = "K"
        cen = centroids.get(major)
        if cen and (r.get("lat") is None or r.get("lng") is None):
            payload["lat"], payload["lng"] = cen
            pinned += 1
        elif not cen:
            no_geom += 1
        if parent_pin_supported:
            payload["parent_pin"] = major + "0000"
        if not payload:
            continue
        if dry_run:
            updated += 1
            continue
        try:
            supa.table("parcels_v3").update(payload).eq("pin", pin).execute()
            updated += 1
            if "parent_pin" in payload:
                parent_pin_ok += 1
        except Exception as e:
            if "parent_pin" in payload and "parent_pin" in str(e):
                # Migration 033 not applied — retry without it, once, and
                # stop attempting parent_pin for the rest of the run.
                parent_pin_supported = False
                payload.pop("parent_pin")
                if payload:
                    supa.table("parcels_v3").update(payload) \
                        .eq("pin", pin).execute()
                    updated += 1
            else:
                raise

    return {
        "zip_code": zip_code,
        "parcels": len(rows),
        "condo_units": len(units),
        "updated": updated,
        "pinned": pinned,
        "no_complex_geom": no_geom,
        "parent_pin_written": parent_pin_ok,
        "parent_pin_supported": parent_pin_supported,
        "dry_run": dry_run,
    }
