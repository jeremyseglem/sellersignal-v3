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
        # Geometry-only layer from KC GIS. Note: this is a DIFFERENT endpoint
        # than the owner/value ingest source — this service exposes only
        # OBJECTID, MAJOR, MINOR, PIN, and Shape. The PIN field here is a
        # 10-char string that matches parcels_v3.pin.
        'url':       'https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0/query',
        'pin_field': 'PIN',
    },
    'WA_SNOHOMISH': {
        # Snohomish County public Parcels FeatureServer — same layer used
        # by backend/ingest/arcgis.py for the full Snohomish ingest. Returns
        # geometry by default (returnGeometry=true is still set explicitly
        # for clarity). PARCEL_ID is a 14-char string with leading zeros
        # (e.g., '00371900100300'), matching how parcels_v3.pin stores
        # Snohomish PINs.
        'url': (
            'https://services6.arcgis.com/z6WYi9VRHfgwgtyW/'
            'arcgis/rest/services/Parcels/FeatureServer/0/query'
        ),
        'pin_field': 'PARCEL_ID',
    },
    'AZ_MARICOPA': {
        # Maricopa County Assessor parcels layer. Geometry is Web Mercator
        # POLYGONS, but the layer also exposes per-parcel WGS84 LATITUDE /
        # LONGITUDE *attributes* — exact parcel points — so we read those
        # directly instead of reprojecting polygon centroids.
        # NOTE: the layer's APN is UNDASHED ('16703002') while parcels_v3.pin
        # is dashed ('167-03-002'), so the AZ branch in _fetch_geometry_for_pins
        # undashes pins for the WHERE clause and maps the result back.
        'url': 'https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0/query',
        'pin_field': 'APN',
        'coords_from_attributes': True,
    },
    'TX_DALLAS': {
        # City of Dallas GIS "DallasTaxParcels" layer (sourced from DCAD +
        # neighboring CADs; covers all of Dallas County + 1-mi buffer). The
        # ACCT field is the 17-char DCAD account number and matches
        # parcels_v3.pin exactly (verified 2026-06-11 — ACCT '60221500020010000'
        # → 3445 Haynie Ave, Highland Park). Native SR is TX State Plane
        # (102738, feet); we request outSR=4326 so the query returns WGS84
        # polygon rings, and _extract_lat_lng takes the ring centroid (the
        # layer does NOT expose per-parcel lat/lng attributes, so polygon
        # centroid — not coords_from_attributes — is correct here).
        'url': (
            'https://gis.dallascityhall.com/arcgis/rest/services/'
            'Basemap/DallasTaxParcels/FeatureServer/0/query'
        ),
        'pin_field': 'ACCT',
    },
}

BATCH_SIZE = 50        # PINs per ArcGIS IN clause. 200 was too large —
                       # URL-encoded IN(...) of 200 quoted 10-char PINs
                       # exceeded ~4KB and was silently truncated somewhere
                       # in the chain (only first ~100 matched). 50 gives
                       # ~600-char IN list, well under any URL length limit.
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
    attr_mode = bool(config.get('coords_from_attributes'))

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for i in range(0, len(pins), BATCH_SIZE):
            batch = pins[i:i + BATCH_SIZE]

            if attr_mode:
                # Layer APN is undashed; parcels_v3.pin is dashed. Query by
                # undashed APN, map results back to the original dashed pin.
                apn_map = {p.replace('-', ''): p for p in batch}  # undashed -> pin
                quoted = ",".join(f"'{a}'" for a in apn_map)
                where_clause = f"{config['pin_field']} IN ({quoted})"
                params = {
                    'where':        where_clause,
                    'outFields':    f"{config['pin_field']},LATITUDE,LONGITUDE",
                    'returnGeometry': 'false',
                    'f':            'json',
                    'resultRecordCount': str(PAGE_SIZE),
                }
            else:
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
                raw_pin = str(attrs.get(config['pin_field'], '')).strip()
                if not raw_pin:
                    continue
                if attr_mode:
                    pin = apn_map.get(raw_pin, raw_pin)
                    lat, lng = attrs.get('LATITUDE'), attrs.get('LONGITUDE')
                    try:
                        lat, lng = float(lat), float(lng)
                    except (TypeError, ValueError):
                        continue
                else:
                    pin = raw_pin
                    lat, lng = _extract_lat_lng(feat.get('geometry', {}) or {})
                if lat is not None and lng is not None:
                    out[pin] = (lat, lng)

            # Be polite to the free endpoint
            await asyncio.sleep(0.2)

    return out


# ──────────────────────────────────────────────────────────────────────
# Supabase query + update
# ──────────────────────────────────────────────────────────────────────

# Module-level flag — set to False after the first time we detect that
# the geocode_skipped column doesn't exist on parcels_v3 (i.e., the
# 024 migration hasn't been applied yet). Avoids hitting the same
# fallback path repeatedly. Resets on process restart.
_geocode_skipped_column_available: Optional[bool] = None


def _fetch_pins_missing_geometry(supa, zip_code: str) -> list[str]:
    """PINs in this ZIP where lat or lng is NULL.

    Excludes PINs marked geocode_skipped=TRUE (the 024 migration's
    "we tried and the source has no record" flag) so they don't sit
    at the top of the queue and block progress on findable PINs.

    Defensive: if the column doesn't exist (migration not applied
    yet), falls back to the legacy query and logs a one-time warning.
    """
    global _geocode_skipped_column_available
    out: list[str] = []
    offset = 0
    PAGE = 1000

    def _query(use_skipped_filter: bool):
        q = (supa.table('parcels_v3')
             .select('pin')
             .eq('zip_code', zip_code)
             .or_('lat.is.null,lng.is.null')
             .range(offset, offset + PAGE - 1))
        if use_skipped_filter:
            q = q.eq('geocode_skipped', False)
        return q.execute()

    while True:
        try:
            if _geocode_skipped_column_available is not False:
                res = _query(use_skipped_filter=True)
                _geocode_skipped_column_available = True
            else:
                res = _query(use_skipped_filter=False)
        except Exception as e:
            err = str(e)
            if 'geocode_skipped' in err and _geocode_skipped_column_available is None:
                print("[geometry_backfill] WARN: geocode_skipped column not present "
                      "(schema/024_geocode_skipped.sql not applied). Falling back to "
                      "unfiltered query — stuck PINs will continue to block the queue.")
                _geocode_skipped_column_available = False
                res = _query(use_skipped_filter=False)
            else:
                raise

        batch = res.data or []
        out.extend(r['pin'] for r in batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 200000:
            break
    return out


def _mark_pins_geocode_skipped(supa, pins: list[str]) -> int:
    """Mark PINs as geocode_skipped=TRUE so future backfills skip them.

    These are PINs the source ArcGIS had no record for — retired,
    subdivided, or condo-unit parcels the county doesn't expose
    geometry for. Per-pin update (slow but the slow path here is
    the ArcGIS fetch, not the Supabase update).

    Returns count of PINs successfully marked. Returns 0 if the
    column doesn't exist (migration not applied), without raising.
    """
    global _geocode_skipped_column_available
    if _geocode_skipped_column_available is False:
        return 0
    marked = 0
    for pin in pins:
        try:
            supa.table('parcels_v3').update({
                'geocode_skipped': True
            }).eq('pin', pin).execute()
            marked += 1
        except Exception as e:
            err = str(e)
            if 'geocode_skipped' in err:
                _geocode_skipped_column_available = False
                print("[geometry_backfill] WARN: cannot mark geocode_skipped, "
                      "column missing. Apply schema/024_geocode_skipped.sql.")
                return marked
            print(f"[geometry_backfill] mark skipped failed for {pin}: {e}")
    return marked


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
        # Mark the not-found PINs as geocode_skipped so the next backfill
        # call doesn't re-fetch the same set and stall progress. This is
        # the fix for the poisoned-queue pattern that capped 98053 at
        # ~8 new geocodes per call after the first few batches.
        not_found_pins = [pin for pin in pins if pin not in coords]
        skipped_count = _mark_pins_geocode_skipped(supa, not_found_pins)
        stats['marked_skipped'] = skipped_count
        if skipped_count:
            log(f"[geometry_backfill] marked {skipped_count} PINs geocode_skipped=TRUE")

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
