"""
ArcGIS structure enrichment — beds/baths/sqft/year-built/stories from
each market's parcel feature service, for markets whose EXISTING source
layer already exposes structure attributes (verified 2026-07-30 by
probing every layer's field list):

  CT_FAIRFIELD  Number_of_Bedroom / Number_of_Baths+Half / Living_Area /
                AYB (actual year built)                     [pin = Link]
  CO_PITKIN     bedrooms / baths / stories / live_area /
                actual_yr_built / last_remodel              [pin = pin]
  CO_DENVER     RES_ORIG_YEAR_BUILT / RES_ABOVE_GRADE_AREA  [pin = SCHEDNUM]
  AZ_MARICOPA   CONST_YEAR / LIVING_SPACE                   [pin = APN_DASH]
  MA_MIDDLESEX / MA_NORFOLK / MA_ESSEX / MA_PLYMOUTH
                YEAR_BUILT / RES_AREA|BLD_AREA / STORIES
                [pin = f"{TOWN_ID}-{PROP_ID}" — composite, rebuilt from
                 the layer's TOWN_ID + PROP_ID fields]

Markets NOT here (need secondary sources; wave 2): WA_SNOHOMISH,
TX_DALLAS / TX_COLLIN / TX_TRAVIS (CAD improvement exports),
FL_PALM_BEACH (PAPA details layer), MT_* (cadastral dwelling tables),
TN_DAVIDSON (assessor characteristics dataset). WA_KING has its own
bulk-extract module (kc_structure_enrich.py).

Query strategy: the source is queried by PIN chunks (POST, `IN (...)`
where clauses) rather than by ZIP — pin fields are universal and stable
while zip fields vary per layer (and CT has no zip field at all).

Write path mirrors kc_structure_enrich: batch upsert on_conflict='pin',
grouped by key-signature (PostgREST uniform-key rule), carrying the
NOT-NULL columns (zip_code, market_key) because Postgres validates the
candidate insert tuple before conflict resolution. NULL = unknown; the
marketplace engine rank-doesn't-reject on NULL.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (SellerSignal structure enrichment)"}
_CHUNK = 400          # pins per source query (POST — no URL-length limit)
_SLEEP = 0.2          # politeness between source queries


def _num(v, cast=int) -> Optional[float]:
    try:
        n = cast(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _map_ct(a: dict) -> dict:
    baths = (_num(a.get("Number_of_Baths"), float) or 0) \
        + 0.5 * (_num(a.get("Number_of_Half_Baths"), float) or 0)
    return {
        "bedrooms": _num(a.get("Number_of_Bedroom")),
        "bathrooms": round(baths, 2) if baths > 0 else None,
        "sqft": _num(a.get("Living_Area")),
        "year_built": _num(a.get("AYB")),
    }


def _map_pitkin(a: dict) -> dict:
    sqft = _num(a.get("live_area")) or _num(a.get("heated_area")) \
        or _num(a.get("area_sqft"))
    return {
        "bedrooms": _num(a.get("bedrooms")),
        "bathrooms": _num(a.get("baths"), float),
        "stories": _num(a.get("stories"), float),
        "sqft": sqft,
        "year_built": _num(a.get("actual_yr_built")),
        "year_renovated": _num(a.get("last_remodel")),
    }


def _map_denver(a: dict) -> dict:
    return {
        "sqft": _num(a.get("RES_ABOVE_GRADE_AREA")),
        "year_built": _num(a.get("RES_ORIG_YEAR_BUILT")),
    }


def _map_maricopa(a: dict) -> dict:
    return {
        "sqft": _num(a.get("LIVING_SPACE")),
        "year_built": _num(a.get("CONST_YEAR")),
    }


def _map_boulder(a: dict) -> dict:
    style = str(a.get("DesignDscr") or "").strip().lower()
    extra = {"features": {"style": style}} if style else {}
    baths = (_num(a.get("FullBaths"), float) or 0) \
        + 0.75 * (_num(a.get("ThreeQtrBaths"), float) or 0) \
        + 0.5 * (_num(a.get("HalfBaths"), float) or 0)
    return {
        "bedrooms": _num(a.get("Bedrooms")),
        "bathrooms": round(baths, 2) if baths > 0 else None,
        "sqft": _num(a.get("FinishedSqft")),
        "year_built": _num(a.get("YearBuilt")),
        **extra,
    }


def _map_tn(a: dict) -> dict:
    return {
        "sqft": _num(a.get("FinishedArea")),
        "year_built": _num(a.get("YearBuilt")),
    }


def _map_collin(a: dict) -> dict:
    out = {
        "sqft": _num(a.get("imprvMainArea")),
        "year_built": _num(a.get("imprvYearBuilt")),
        "acres": _num(a.get("landSizeAcres"), float),
    }
    if str(a.get("imprvPoolFlag") or "").strip().upper() in ("Y", "T", "1", "TRUE"):
        out["features"] = {"pool": True}
    return out


def _map_ma(a: dict) -> dict:
    out = {
        "sqft": _num(a.get("RES_AREA")) or _num(a.get("BLD_AREA")),
        "year_built": _num(a.get("YEAR_BUILT")),
        "stories": _num(a.get("STORIES"), float),
    }
    style = str(a.get("STYLE") or "").strip().lower()
    if style:
        out["features"] = {"style": style}
    return out


_MA_CONFIG = {
    "url": ("https://arcgisserver.digital.mass.gov/arcgisserver/rest/"
            "services/AGOL/L3_Parcels_FeatureService_4326/FeatureServer/1"),
    "pin_field": "PROP_ID",
    "out_fields": "PROP_ID,TOWN_ID,YEAR_BUILT,BLD_AREA,RES_AREA,STORIES,STYLE",
    "map": _map_ma,
    # parcels_v3 pin = f"{TOWN_ID}-{PROP_ID}"; query on the PROP_ID part
    # and rebuild the composite from the response to map back exactly.
    "pin_split": "-",
    "compose": lambda a: (f"{str(a.get('TOWN_ID') or '').strip()}-"
                          f"{str(a.get('PROP_ID') or '').strip()}"),
}

STRUCT_CONFIGS: dict[str, dict] = {
    "CT_FAIRFIELD": {
        "url": ("https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/"
                "rest/services/Connecticut_State_Parcel_Layer_2023/"
                "FeatureServer/0"),
        "pin_field": "Link",
        "out_fields": ("Link,Number_of_Bedroom,Number_of_Baths,"
                       "Number_of_Half_Baths,Living_Area,AYB"),
        "map": _map_ct,
    },
    "CO_PITKIN": {
        "url": ("https://maps.pitkincounty.com/arcgis/rest/services/"
                "Hosted/Parcels/FeatureServer/0"),
        "pin_field": "pin",
        "numeric_pin": True,   # layer field is numeric — unquoted IN list
        "out_fields": ("pin,bedrooms,baths,stories,live_area,heated_area,"
                       "area_sqft,actual_yr_built,last_remodel"),
        "map": _map_pitkin,
    },
    "CO_DENVER": {
        "url": ("https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/"
                "rest/services/ODC_PROP_PARCELS_A/FeatureServer/245"),
        "pin_field": "SCHEDNUM",
        "out_fields": "SCHEDNUM,RES_ORIG_YEAR_BUILT,RES_ABOVE_GRADE_AREA",
        "map": _map_denver,
    },
    "AZ_MARICOPA": {
        "url": ("https://gis.mcassessor.maricopa.gov/arcgis/rest/"
                "services/Parcels/MapServer/0"),
        "pin_field": "APN_DASH",
        "out_fields": "APN_DASH,CONST_YEAR,LIVING_SPACE",
        "map": _map_maricopa,
    },
    "TX_COLLIN": {
        # CCAD parcels layer carries improvement attrs directly.
        # acres only written where currently null (engine-side no-op is
        # handled by the write path sending values as-is — Collin acres
        # coverage in parcels_v3 is 0%, so overwrite risk is nil).
        "url": ("https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/"
                "rest/services/CCAD_Parcel_Feature_Set/FeatureServer/4"),
        "pin_field": "propID",
        "numeric_pin": True,
        "out_fields": "propID,imprvYearBuilt,imprvMainArea,landSizeAcres,imprvPoolFlag",
        "map": _map_collin,
        "prefer_max": "sqft",
    },
    "CO_BOULDER": {
        # CAMA building-attributes TABLE (MapServer layer 1); one row per
        # building — the enricher keeps the largest FinishedSqft per pin.
        # parcels_v3 pin = strap/AccountNo (e.g. 'R0008431').
        "url": ("https://maps.bouldercounty.org/arcgis/rest/services/"
                "CamaView/PropSearch_BLDG_ATTRIBUTES/MapServer/1"),
        "pin_field": "AccountNo",
        "out_fields": ("AccountNo,Bedrooms,FullBaths,HalfBaths,"
                       "ThreeQtrBaths,YearBuilt,FinishedSqft,DesignDscr"),
        "map": _map_boulder,
        "prefer_max": "sqft",
    },
    "TN_DAVIDSON": {
        "url": ("https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/"
                "rest/services/Parcels_with_Building_Characteristics_view/"
                "FeatureServer/0"),
        "pin_field": "ParcelID",   # numeric; equals our ParID-derived pin
        "numeric_pin": True,
        "out_fields": "ParcelID,FinishedArea,YearBuilt",
        "map": _map_tn,
        "prefer_max": "sqft",
    },
    "MA_MIDDLESEX": _MA_CONFIG,
    "MA_DUKES": _MA_CONFIG,
    "MA_NANTUCKET": _MA_CONFIG,   # Martha's Vineyard — same MassGIS statewide layer
    "MA_NORFOLK": _MA_CONFIG,
    "MA_ESSEX": _MA_CONFIG,
    "MA_PLYMOUTH": _MA_CONFIG,
}


_CLAMPS = {  # implausible-for-a-residence values -> None (whole-building
             # records, data glitches); also protects NUMERIC(4,2)/(4,1)
    "bedrooms": 50, "bathrooms": 99, "stories": 99,
    "year_built": 2100, "year_renovated": 2100, "sqft": 2_000_000,
}


def _clamp(mapped: dict) -> dict:
    out = {}
    for k, v in mapped.items():
        cap = _CLAMPS.get(k)
        if cap is not None and not isinstance(v, dict) and v is not None \
                and v > cap:
            continue
        out[k] = v
    return out


def _query_chunk(client: httpx.Client, cfg: dict, values: list[str]) -> list[dict]:
    if cfg.get("numeric_pin"):
        vals = [v for v in values if v.replace(".", "", 1).isdigit()]
        if not vals:
            return []
        quoted = ",".join(vals)
    else:
        quoted = ",".join("'" + v.replace("'", "''") + "'" for v in values)
    data = {
        "where": f"{cfg['pin_field']} IN ({quoted})",
        "outFields": cfg["out_fields"],
        "returnGeometry": "false",
        "f": "json",
    }
    r = client.post(cfg["url"] + "/query", data=data)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"ArcGIS error: {body['error']}")
    return [f.get("attributes", {}) for f in body.get("features", [])]


def enrich_zip_arcgis(supa, zip_code: str, market_key: str) -> dict:
    cfg = STRUCT_CONFIGS.get(market_key)
    if cfg is None:
        raise ValueError(f"no ArcGIS structure adapter for {market_key}")

    # 1. Target pins.
    pins: list[str] = []
    offset = 0
    while True:
        page = (supa.table("parcels_v3").select("pin")
                .eq("zip_code", zip_code)
                .range(offset, offset + 999).execute()).data or []
        pins.extend(str(r["pin"]) for r in page)
        if len(page) < 1000:
            break
        offset += 1000
    if not pins:
        return {"zip_code": zip_code, "pins": 0, "rows_written": 0}
    pin_set = set(pins)

    # For composite pins (MA), the source is queried on the suffix part.
    def query_value(pin: str) -> str:
        sep = cfg.get("pin_split")
        return pin.split(sep, 1)[1] if sep and sep in pin else pin

    def response_pin(attrs: dict) -> str:
        compose: Optional[Callable] = cfg.get("compose")
        if compose:
            return compose(attrs)
        raw = attrs.get(cfg["pin_field"])
        if isinstance(raw, float) and raw.is_integer():
            raw = int(raw)   # numeric layer fields come back as floats
        return str(raw or "").strip()

    # 2. Query the source in chunks, map fields per pin.
    updates: dict[str, dict] = {}
    source_hits = 0
    with httpx.Client(timeout=90, headers=_UA) as client:
        for i in range(0, len(pins), _CHUNK):
            chunk = pins[i:i + _CHUNK]
            values = list({query_value(p) for p in chunk})
            attrs_list = _query_chunk(client, cfg, values)
            for a in attrs_list:
                pin = response_pin(a)
                if pin not in pin_set:
                    continue
                mapped = _clamp({k: v for k, v in cfg["map"](a).items()
                                 if v is not None})
                if not mapped:
                    continue
                source_hits += 1
                mapped["pin"] = pin
                pref = cfg.get("prefer_max")
                prev = updates.get(pin)
                if prev is not None and pref:
                    # multiple buildings per parcel — keep the largest
                    if (prev.get(pref) or 0) >= (mapped.get(pref) or 0):
                        continue
                updates[pin] = mapped
            if i + _CHUNK < len(pins):
                time.sleep(_SLEEP)

    # 3. Write — key-signature batching, NOT NULL columns carried.
    payload = []
    for u in updates.values():
        u["zip_code"] = zip_code
        u["market_key"] = market_key
        payload.append(u)

    by_sig: dict[tuple, list[dict]] = {}
    for u in payload:
        by_sig.setdefault(tuple(sorted(u.keys())), []).append(u)

    written = 0
    field_counts: dict[str, int] = {}
    for _sig, rows_ in by_sig.items():
        for i in range(0, len(rows_), 500):
            batch = rows_[i:i + 500]
            supa.table("parcels_v3").upsert(batch, on_conflict="pin").execute()
            written += len(batch)
    for u in payload:
        for k in u:
            if k in ("pin", "zip_code", "market_key"):
                continue
            field_counts[k] = field_counts.get(k, 0) + 1

    return {
        "zip_code": zip_code,
        "market_key": market_key,
        "pins": len(pins),
        "source_rows_matched": source_hits,
        "rows_written": written,
        "field_counts": field_counts,
    }
