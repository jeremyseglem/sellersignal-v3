"""
Geometry backfill — fix parcels_v3 rows with null lat/lng.

Problem: a prior ingest path produced 6,658 parcels in 98004 with no
coordinates, making the map unusable. Re-running full ingest risks
overwriting owner_name, value, and other columns that have since been
augmented (canonicalization, classification, banding, investigation).

This module is surgical: it only queries KC ArcGIS for geometry, only
updates lat/lng, leaves everything else alone.

Batch strategy:
  1. Pull all PINs in ZIP where lat IS NULL or lng IS NULL
  2. Batch-query ArcGIS in chunks of ~200 PINs per `where` clause
  3. Extract lat/lng from returned geometry (point OR polygon centroid)
  4. Bulk-update parcels_v3 with the coordinates

ArcGIS query uses outSR=4326 (WGS84) so Leaflet can consume directly.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlencode

try:
    import httpx
except ImportError:
    httpx = None

from backend.api.db import get_supabase_client


# ──────────────────────────────────────────────────────────────────────
# Config — reuses the market config from arcgis.py but locked to
# geometry-only queries
# ──────────────────────────────────────────────────────────────────────
MARKET_CONFIGS = {
    'WA_KING': {
        'url':       'https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0/query',
        'pin_field': 'PARCELID',
    },
}

BATCH_SIZE = 200       # PINs per ArcGIS where-clause
PAGE_SIZE = 2000       # features per response (ArcGIS max)
REQUEST_TIMEOUT_SECONDS = 60


# ──────────────────────────────────────────────────────────────────────
# Geometry extraction — same logic as arcgis._extract_lat_lng
# ──────────────────────────────────────────────────────────────────────
def _extract_lat_lng(geom: dict) -> tuple[Optional[float], Optional[float]]:
    """Compute (lat, lng) from ArcGIS geometry (point or polygon centroid)."""
    if not geom:
        return None, None

    # Point geometry
    if 'x' in geom and 'y' in geom:
        return float(geom['y']), float(geom['x'])

    # Polygon: first ring centroid
    rings = geom.get('rings') or []
    if rings and rings[0]:
        ring = rings[0]
        xs = [p[0] for p in ring if len(p) >= 2]
        ys = [p[1] for p in ring if len(p) >= 2]
        if xs and ys:
            return sum(ys) / len(ys), sum(xs) / len(xs)

    return None, None


# ──────────────────────────────────────────────────────────────────────
# ArcGIS batch fetcher
# ──────────────────────────────────────────────────────────────────────
async def _fetch_geometry_for_pins(pins: list[str],
                                    market_key: str = 'WA_KING') -> dict[str, tuple[float, float]]:
    """
    Batch-query ArcGIS for geometry by PIN. Returns {pin: (lat, lng)} for
    every pin where we got usable geometry. Missing pins simply don't
    appear in the dict.
    """
    if httpx is None:
        raise ImportError("httpx is required. pip install httpx")
    config = MARKET_CONFIGS.get(market_key)
    if not config:
        raise ValueError(f"Market {market_key} not configured for geometry backfill")

    out: dict[str, tuple[float, float]] = {}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for i in range(0, len(pins), BATCH_SIZE):
            batch = pins[i:i + BATCH_SIZE]
            # Build WHERE clause like: PARCELID IN ('1234','5678',...)
            quoted = ",".join(f"'{p}'" for p in batch)
            where_clause = f"{config['pin_field']} IN ({quoted})"

            params = {
                'where':        where_clause,
                'outFields':    config['pin_field'],
                'returnGeometry': 'true',
                'outSR':        '4326',
                'f':            'json',
                'resultRecordCount': str(PAGE_SIZE),
            }
            url = f"{config['url']}?{urlencode(params)}"

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                print(f"[geometry_backfill] batch {i//BATCH_SIZE} error: {e}")
                continue

            for feat in data.get('features', []):
                attrs = feat.get('attributes', {}) or {}
                pin = str(attrs.get(config['pin_field'], '')).strip()
                if not pin:
                    continue
                lat, lng = _extract_lat_lng(feat.get('geometry', {}) or {})
                if lat is not None and lng is not None:
                    out[pin] = (lat, lng)

            # Be polite to the free endpoint
            await asyncio.sleep(0.2)

    return out


# ──────────────────────────────────────────────────────────────────────
# Supabase query + update
# ──────────────────────────────────────────────────────────────────────
def _fetch_pins_missing_geometry(supa, zip_code: str) -> list[str]:
    """PINs in this ZIP where lat or lng is NULL."""
    out: list[str] = []
    offset = 0
    PAGE = 1000
    while True:
        res = (supa.table('parcels_v3')
               .select('pin')
               .eq('zip_code', zip_code)
               .or_('lat.is.null,lng.is.null')
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        out.extend(r['pin'] for r in batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 200000:
            break
    return out


def _bulk_update_coords(supa, coords: dict[str, tuple[float, float]]) -> int:
    """Update lat/lng for each pin. Returns count of rows updated."""
    updated = 0
    # Supabase client doesn't have true bulk-update-by-list, so we update
    # per-pin. For 6,658 rows this is ~10-20 min. Acceptable.
    for pin, (lat, lng) in coords.items():
        try:
            supa.table('parcels_v3').update({
                'lat': lat, 'lng': lng
            }).eq('pin', pin).execute()
            updated += 1
        except Exception as e:
            print(f"[geometry_backfill] update failed for {pin}: {e}")
    return updated


# ──────────────────────────────────────────────────────────────────────
# Public API — async-native (preferred; safe inside FastAPI handlers)
# ──────────────────────────────────────────────────────────────────────
async def backfill_geometry_zip_async(
    zip_code: str, market_key: str = 'WA_KING',
    dry_run: bool = False, limit: Optional[int] = None,
    verbose: bool = True,
) -> dict:
    """
    Async implementation. Safe to call from a FastAPI async endpoint
    where an event loop is already running.
    """
    def log(msg: str):
        if verbose:
            print(msg, flush=True)

    stats: dict = {
        'zip_code': zip_code, 'market_key': market_key,
        'dry_run': dry_run,
        'missing_geom': 0, 'fetched': 0, 'updated': 0,
        'not_found': 0, 'errors': [],
    }

    supa = get_supabase_client()
    if not supa:
        stats['errors'].append('Supabase not configured')
        return stats

    pins = _fetch_pins_missing_geometry(supa, zip_code)
    stats['missing_geom'] = len(pins)
    log(f"[geometry_backfill] ZIP {zip_code}: {len(pins)} parcels missing geometry")

    if not pins:
        log("[geometry_backfill] nothing to do")
        return stats

    if limit:
        pins = pins[:limit]
        log(f"[geometry_backfill] --limit {limit} applied, processing: {len(pins)}")

    if dry_run:
        log(f"[geometry_backfill] DRY RUN — would query {len(pins)} PINs from ArcGIS")
        log(f"[geometry_backfill] sample PINs: {pins[:5]}")
        return stats

    log(f"[geometry_backfill] querying ArcGIS in batches of {BATCH_SIZE}...")
    try:
        coords = await _fetch_geometry_for_pins(pins, market_key)
    except Exception as e:
        stats['errors'].append(f"ArcGIS fetch failed: {e}")
        log(f"[geometry_backfill] ArcGIS fetch failed: {e}")
        return stats

    stats['fetched'] = len(coords)
    stats['not_found'] = len(pins) - len(coords)
    log(f"[geometry_backfill] fetched coords for {len(coords)} of {len(pins)} PINs")
    if stats['not_found']:
        log(f"[geometry_backfill] {stats['not_found']} PINs had no ArcGIS geometry (may be retired parcels)")

    if coords:
        log(f"[geometry_backfill] updating Supabase...")
        stats['updated'] = _bulk_update_coords(supa, coords)
        log(f"[geometry_backfill] updated {stats['updated']} rows")

    return stats


# ──────────────────────────────────────────────────────────────────────
# Sync wrapper for CLI use — NOT safe inside a running event loop
# ──────────────────────────────────────────────────────────────────────
def backfill_geometry_zip(zip_code: str, market_key: str = 'WA_KING',
                          dry_run: bool = False, limit: Optional[int] = None,
                          verbose: bool = True) -> dict:
    """
    Synchronous wrapper around backfill_geometry_zip_async.
    Creates its own event loop — do NOT call from inside async code;
    use backfill_geometry_zip_async() there instead.
    """
    return asyncio.run(backfill_geometry_zip_async(
        zip_code=zip_code, market_key=market_key,
        dry_run=dry_run, limit=limit, verbose=verbose,
    ))
