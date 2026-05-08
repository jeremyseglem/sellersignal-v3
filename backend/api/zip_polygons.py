"""
ZIP polygons API — serves Census ZCTA polygons for our active coverage.

  GET /api/zip-polygons             — FeatureCollection for all live ZIPs
  GET /api/zip-polygons?include_development=true  — also include in-dev ZIPs

This powers the territories map view. The frontend hits this once on map
load and gets back a FeatureCollection with the polygons it needs.

Why this endpoint exists (vs. a static asset):
  - Coverage list changes as we add ZIPs (KC + Snohomish + future markets).
    A static frontend asset would need a redeploy on every ZIP add.
  - The full WA polygon bundle (~1.2MB) is much larger than what any single
    user needs. Filtering to live coverage trims responses to ~50-80KB
    typical, which loads instantly and caches well.
  - When we expand to other states, we add more bundles per state and
    this endpoint dispatches by market_key.

Data source:
  data/zip_polygons/wa.json — Census ZCTA 2010 boundaries for Washington
  state, filtered to {zip, lat, lng} properties only, with Douglas-Peucker
  simplification at tolerance 0.001 degrees (~111m). 598 ZCTAs total.

Caching strategy:
  - Bundle is loaded once at module import (cold start cost only).
  - Per-request response is computed by filtering the in-memory bundle
    against the current zip_coverage_v3 list. Database call is ~10ms.
  - HTTP response includes Cache-Control: max-age=3600 (1 hr) — polygons
    don't change between deploys; the per-zip list might change when a
    new market is added but tolerating an hour of staleness is fine for
    a territory selector.
"""
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response

from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

router = APIRouter()


# ── Bundle loader ─────────────────────────────────────────────────────────
# Bundles are keyed by market_key prefix. WA covers WA_KING and
# WA_SNOHOMISH; future markets get their own bundles.
_BUNDLES: dict[str, dict] = {}


def _load_bundle(state_code: str) -> dict:
    """
    Lazily load and cache a state's polygon bundle. Returns a dict like
    {"<zip>": <feature>, ...} keyed by ZIP for fast lookup.
    """
    if state_code in _BUNDLES:
        return _BUNDLES[state_code]

    repo_root = Path(__file__).resolve().parent.parent.parent
    path = repo_root / "data" / "zip_polygons" / f"{state_code.lower()}.json"
    if not path.exists():
        log.warning("[zip-polygons] no bundle for state=%s at %s", state_code, path)
        _BUNDLES[state_code] = {}
        return {}

    try:
        with open(path) as f:
            geo = json.load(f)
        by_zip = {}
        for feat in geo.get("features", []):
            z = feat.get("properties", {}).get("zip")
            if z:
                by_zip[z] = feat
        _BUNDLES[state_code] = by_zip
        log.info("[zip-polygons] loaded %d features for state=%s", len(by_zip), state_code)
        return by_zip
    except Exception as e:
        log.exception("[zip-polygons] failed to load bundle for %s: %s", state_code, e)
        _BUNDLES[state_code] = {}
        return {}


# ── Endpoint ──────────────────────────────────────────────────────────────
@router.get("")
async def list_zip_polygons(
    response: Response,
    include_development: bool = Query(False),
):
    """
    Return a FeatureCollection of polygons for our currently-covered ZIPs.

    Each feature is a Census ZCTA boundary, GeoJSON Polygon/MultiPolygon
    geometry in WGS84, with properties:
      - zip:    5-digit ZIP code
      - lat:    centroid latitude
      - lng:    centroid longitude
      - state:  state abbreviation (e.g. 'WA')
      - status: 'live' | 'in_development'
      - city:   city name from coverage table
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Pull the live coverage list
    try:
        q = supa.table("zip_coverage_v3").select("zip_code, market_key, city, state, status")
        if not include_development:
            q = q.eq("status", "live")
        rows = (q.execute().data or [])
    except Exception as e:
        log.exception("[zip-polygons] coverage query failed: %s", e)
        raise HTTPException(503, "Coverage lookup failed")

    # Group by state so we load each bundle once
    by_state: dict[str, list[dict]] = {}
    for r in rows:
        st = (r.get("state") or "WA").upper()
        by_state.setdefault(st, []).append(r)

    features: list[dict] = []
    missing: list[str] = []
    for state_code, state_rows in by_state.items():
        bundle = _load_bundle(state_code)
        if not bundle:
            for r in state_rows:
                missing.append(r["zip_code"])
            continue
        for r in state_rows:
            zip_code = r["zip_code"]
            feat = bundle.get(zip_code)
            if not feat:
                missing.append(zip_code)
                continue
            # Shallow-copy + extend properties with coverage metadata.
            # Don't mutate the cached feature.
            enriched = {
                "type":       "Feature",
                "geometry":   feat["geometry"],
                "properties": {
                    **feat.get("properties", {}),
                    "state":  state_code,
                    "city":   r.get("city"),
                    "status": r.get("status"),
                },
            }
            features.append(enriched)

    # Cache for an hour. Polygons don't change between deploys; a new
    # ZIP added during the hour is fine to surface a few minutes late.
    response.headers["Cache-Control"] = "public, max-age=3600"

    return {
        "type":     "FeatureCollection",
        "features": features,
        "stats": {
            "returned":        len(features),
            "covered_total":   len(rows),
            "missing":         missing,  # ZIPs we cover but have no polygon for
        },
    }
