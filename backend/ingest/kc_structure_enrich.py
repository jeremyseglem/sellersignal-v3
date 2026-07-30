"""
KC structure enrichment — beds/baths/sqft/year-built/stories/renovation/
waterfront/views from the bulk assessor extracts, per WA_KING ZIP.

Feeds the marketplace demand engine's Tier-2 criteria (schema/035).

Sources (aqua.kingcounty.gov, same host family as the seed builder):
  Residential Building.zip / EXTR_ResBldg.csv   (~90 MB CSV)
      -> houses: Bedrooms, Bath{Full,3qtr,Half}Count, SqFtTotLiving,
         YrBuilt, YrRenovated, Stories
  Condo Complex and Units.zip / EXTR_CondoUnit2.csv (~115k units)
      -> condo units: NbrBedrooms, bath counts, Footage, YrBuilt,
         unit View* ratings
  Parcel.zip / EXTR_Parcel.csv                  (~200 MB CSV)
      -> all parcels: 9 view ratings (0-4) -> view_rating = max,
         WfntLocation/WfntFootage -> waterfront flags,
         SqFtLot -> acres fill (ONLY where acres is currently null)

Memory discipline (Railway OOM history): zips are cached on DISK in
/tmp/kc_extracts once per process lifetime; CSVs are streamed row-by-row
from the zip and filtered against the target ZIP's PIN set — nothing
county-wide is held in memory.

Write path: batch upsert on_conflict='pin' sending only the enrichment
columns. Every payload pin comes from parcels_v3 for the target ZIP, so
the conflict/update path is always taken and no insert can fire.

Conventions: 0 means "not recorded" in the extracts -> stored as NULL.
Bathrooms use the listing convention: full + 0.75*three-quarter +
0.5*half.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import zipfile
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_CACHE_DIR = "/tmp/kc_extracts"
_UA = {"User-Agent": "Mozilla/5.0 (SellerSignal structure enrichment)"}

_SOURCES = {
    "resbldg": ("https://aqua.kingcounty.gov/extranet/assessor/"
                "Residential%20Building.zip", "EXTR_ResBldg.csv"),
    "condo":   ("https://aqua.kingcounty.gov/extranet/assessor/"
                "Condo%20Complex%20and%20Units.zip", "EXTR_CondoUnit2.csv"),
    "parcel":  ("https://aqua.kingcounty.gov/extranet/assessor/"
                "Parcel.zip", "EXTR_Parcel.csv"),
}

_VIEW_COLS_PARCEL = (
    "MtRainier", "Olympics", "Cascades", "Territorial", "SeattleSkyline",
    "PugetSound", "LakeWashington", "LakeSammamish", "SmallLakeRiverCreek",
    "OtherView",
)
_VIEW_COLS_CONDO = (
    "ViewMountain", "ViewLakeRiver", "ViewCityTerritorial",
    "ViewPugetSound", "ViewLakeWaSamm",
)


def _ensure_zip_cached(key: str) -> str:
    """Download the extract zip to disk once per process; return path."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    url, _ = _SOURCES[key]
    path = os.path.join(_CACHE_DIR, key + ".zip")
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    log.info("kc_structure_enrich: downloading %s", url)
    tmp = path + ".part"
    with httpx.Client(timeout=300, headers=_UA, follow_redirects=True) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
    os.replace(tmp, path)
    return path


def _rows(key: str):
    """Stream DictReader rows from the cached zip's CSV."""
    path = _ensure_zip_cached(key)
    _, csv_name = _SOURCES[key]
    zf = zipfile.ZipFile(path)
    name = next(n for n in zf.namelist() if n == csv_name)
    with zf.open(name) as fh:
        reader = csv.DictReader(
            io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
        for row in reader:
            yield row


def _num(v, cast=int) -> Optional[float]:
    """Parse an extract number; 0/blank/garbage -> None."""
    try:
        n = cast(float(str(v).strip()))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _baths(row: dict, full: str, three: str, half: str) -> Optional[float]:
    f = _num(row.get(full)) or 0
    t = _num(row.get(three)) or 0
    h = _num(row.get(half)) or 0
    total = f + 0.75 * t + 0.5 * h
    return round(total, 2) if total > 0 else None


def enrich_zip(supa, zip_code: str) -> dict:
    """Enrich parcels_v3 structure columns for one WA_KING ZIP."""
    # 1. Target pins + current acres (acres is only filled where null).
    pins: dict[str, Optional[float]] = {}
    offset = 0
    while True:
        page = (supa.table("parcels_v3").select("pin, acres")
                .eq("zip_code", zip_code)
                .range(offset, offset + 999).execute()).data or []
        for r in page:
            pins[str(r["pin"])] = r.get("acres")
        if len(page) < 1000:
            break
        offset += 1000
    if not pins:
        return {"zip_code": zip_code, "pins": 0, "updated": 0}

    updates: dict[str, dict] = {}

    def upd(pin: str) -> dict:
        return updates.setdefault(pin, {"pin": pin})

    # 2. Houses — EXTR_ResBldg. Multiple buildings per pin: keep the
    #    largest living area as the primary residence.
    best_sqft: dict[str, int] = {}
    res_hits = 0
    for row in _rows("resbldg"):
        pin = (row.get("Major") or "").strip() + (row.get("Minor") or "").strip()
        if pin not in pins:
            continue
        sqft = _num(row.get("SqFtTotLiving")) or 0
        if pin in best_sqft and sqft <= best_sqft[pin]:
            continue
        best_sqft[pin] = sqft
        res_hits += 1
        u = upd(pin)
        u["bedrooms"] = _num(row.get("Bedrooms"))
        u["bathrooms"] = _baths(row, "BathFullCount", "Bath3qtrCount",
                                "BathHalfCount")
        u["sqft"] = sqft or None
        u["year_built"] = _num(row.get("YrBuilt"))
        u["year_renovated"] = _num(row.get("YrRenovated"))
        u["stories"] = _num(row.get("Stories"), cast=float)

    # 3. Condo units — EXTR_CondoUnit2 (unit-level truth; wins over any
    #    ResBldg collision, which shouldn't occur for K pins anyway).
    condo_hits = 0
    for row in _rows("condo"):
        pin = (row.get("Major") or "").strip() + (row.get("Minor") or "").strip()
        if pin not in pins:
            continue
        condo_hits += 1
        u = upd(pin)
        u["bedrooms"] = _num(row.get("NbrBedrooms"))
        u["bathrooms"] = _baths(row, "BathFullCount", "Bath3qtrCount",
                                "BathHalfCount")
        u["sqft"] = _num(row.get("Footage"))
        u["year_built"] = _num(row.get("YrBuilt"))
        views = [(_num(row.get(c)) or 0) for c in _VIEW_COLS_CONDO]
        if max(views) > 0:
            u["view_rating"] = int(max(views))

    # 4. Parcel amenities — views, waterfront, lot-size fill.
    parcel_hits = 0
    for row in _rows("parcel"):
        pin = (row.get("Major") or "").strip() + (row.get("Minor") or "").strip()
        if pin not in pins:
            continue
        parcel_hits += 1
        u = upd(pin)
        views = [(_num(row.get(c)) or 0) for c in _VIEW_COLS_PARCEL]
        if max(views) > 0:
            u["view_rating"] = max(int(max(views)),
                                   u.get("view_rating") or 0)
        wfnt_loc = _num(row.get("WfntLocation"))
        if wfnt_loc:
            u["waterfront"] = True
            u["waterfront_footage"] = _num(row.get("WfntFootage"))
        if pins[pin] in (None, 0):
            sqft_lot = _num(row.get("SqFtLot"))
            if sqft_lot:
                u["acres"] = round(sqft_lot / 43560.0, 3)

    # 5. Write — only rows that gained at least one real value. PostgREST
    #    requires uniform keys within one request, and padding with nulls
    #    would overwrite existing values (acres!) — so drop the None
    #    entries per row and batch by identical key-signature.
    payload = []
    for u in updates.values():
        clean = {k: v for k, v in u.items() if v is not None}
        if len(clean) > 1:  # more than just the pin
            clean["zip_code"] = zip_code  # belt-and-suspenders scope
            payload.append(clean)

    by_sig: dict[tuple, list[dict]] = {}
    for u in payload:
        by_sig.setdefault(tuple(sorted(u.keys())), []).append(u)

    written = 0
    field_counts: dict[str, int] = {}
    for sig, rows_ in by_sig.items():
        for i in range(0, len(rows_), 500):
            batch = rows_[i:i + 500]
            supa.table("parcels_v3").upsert(batch, on_conflict="pin").execute()
            written += len(batch)
    for u in payload:
        for k, v in u.items():
            if k in ("pin", "zip_code"):
                continue
            field_counts[k] = field_counts.get(k, 0) + 1

    return {
        "zip_code": zip_code,
        "pins": len(pins),
        "resbldg_rows_matched": res_hits,
        "condo_units_matched": condo_hits,
        "parcel_rows_matched": parcel_hits,
        "rows_written": written,
        "field_counts": field_counts,
    }
