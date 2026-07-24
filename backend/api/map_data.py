"""
Map data API — powers the territory map in the unified UI.

  GET /api/map/:zip                 — all parcels with lat/lng + pressure/category
  GET /api/map/:zip/bounds          — bounding box for initial map center
  GET /api/map/streetview/:pin      — Google Street View Static URL for a parcel

Heat map coloring on the frontend uses the 'category' field:
  category=call_now         → red
  category=build_now        → amber/gold
  category=strategic_hold   → muted gold
  category=hold             → soft blue/gray
  category=uninvestigated   → cool blue (lightest)
  category=avoid            → slate (blocker)
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from typing import Optional
from backend.api.db import get_supabase_client
from backend.api.zip_gate import require_live_zip
from backend.api.auth import user_from_authorization as _user_from_authorization
from backend.api.territory import require_zip_access as _require_zip_access
import os
import logging
import hmac
import hashlib
import base64
from urllib.parse import quote, urlencode

log = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Bbox outlier filter — drops contaminated parcels from map output
# ============================================================================

# Distance thresholds from the ZIP's median lat/lng. Parcels farther than
# these are dropped from map rendering. The KC ingest source (ZIP5 field)
# sometimes tags parcels with a ZIP whose geometry sits miles away —
# 98053 had 41.6% off-bbox parcels with coords reaching 25+ miles west
# into Seattle. We can't fix the source data, but we can refuse to
# render visibly wrong dots.
#
# Sizing: ~5 miles in each direction. 1 deg lat ≈ 69 mi; 1 deg lng at
# lat 47.6 ≈ 46.7 mi. So 0.075 lat / 0.105 lng ≈ 5 mi.
#
# Tightened from 10 mi after the initial deploy left too much nearby
# contamination (Bothell, Woodinville parcels 5-10 mi from 98053
# center). 5 mi keeps Sahalee / Cottage Lake / Union Hill (98053's
# real annexes) in-bounds while catching the cross-ZIP leakage that
# was making the map look wrong.
_BBOX_FILTER_MAX_LAT_DELTA = 0.075
_BBOX_FILTER_MAX_LNG_DELTA = 0.105
_BBOX_FILTER_MIN_SAMPLE    = 50  # don't filter on tiny samples — median unreliable


def _median(values: list[float]) -> float:
    """Sort + middle element. Not asyncio-safe but inputs are sync lists."""
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2


def _filter_bbox_outliers(coords: list[tuple[float, float]]) -> tuple[float, float, set[int]]:
    """
    Returns (median_lat, median_lng, indices_of_outliers).

    indices_of_outliers is a set of positions into the input `coords` list
    representing parcels that sit more than ~10 mi from the ZIP's median
    centroid. Caller filters its own parcel list using these indices.

    For samples below MIN_SAMPLE size the function returns an empty
    outlier set — median isn't reliable enough to filter against.
    """
    if len(coords) < _BBOX_FILTER_MIN_SAMPLE:
        if not coords:
            return 0.0, 0.0, set()
        return _median([c[0] for c in coords]), _median([c[1] for c in coords]), set()
    med_lat = _median([c[0] for c in coords])
    med_lng = _median([c[1] for c in coords])
    outliers = set()
    for i, (lat, lng) in enumerate(coords):
        if (abs(lat - med_lat) > _BBOX_FILTER_MAX_LAT_DELTA
                or abs(lng - med_lng) > _BBOX_FILTER_MAX_LNG_DELTA):
            outliers.add(i)
    return med_lat, med_lng, outliers


# ============================================================================
# Map data — heatmap + pin payload
# ============================================================================

def _gate(zip_code, authorization, x_admin_key):
    """Read-endpoint auth gate. Allows server-to-self admin-key loopback;
    otherwise requires an authenticated user with access to zip_code
    (operator = all ZIPs, agent = own assigned_zip). Mirrors briefings."""
    admin_env = (os.environ.get('ADMIN_KEY') or '').strip()
    if admin_env and x_admin_key and x_admin_key == admin_env:
        return
    _require_zip_access(_user_from_authorization(authorization), zip_code)


@router.get("/earth-config")
async def earth_config(authorization: str | None = Header(None),
                       x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    """
    Photorealistic 3D Tiles ("Earth mode") key handoff — MIGRATION_V4.md
    Phase 4, the "velvet rope": Earth mode is a territory-owner feature,
    never a public/marketing one, so the metered Google spend is scoped
    to paying agents.

    The key returned here is a BROWSER key by design (Google 3D tiles are
    fetched directly by the client; proxying the mesh through our single
    worker is a non-starter). Its real protections live in Cloud Console:
      - API restriction: Map Tiles API only
      - Referrer restriction: https://sellersignal.co/*
      - Quota caps
    This endpoint adds the product-level gate: only authenticated agents
    with a claimed territory (or operators / X-Admin-Key) receive it.

    Env: GOOGLE_MAPS_3D_TILES_KEY (separate from the server-side
    GOOGLE_MAPS_API_KEY used for Street View — never hand that one out).
    Returns 404 when unconfigured so the frontend can hide the EARTH
    control entirely.
    """
    key = os.environ.get('GOOGLE_MAPS_3D_TILES_KEY', '')
    if not key:
        raise HTTPException(404, 'Earth mode is not configured.')
    admin_expected = os.environ.get('ADMIN_KEY', '')
    if not (admin_expected and x_admin_key == admin_expected):
        user = _user_from_authorization(authorization)
        from backend.api.territory import _load_profile
        profile = _load_profile(user.id)
        if profile.get('role') != 'operator' and not profile.get('assigned_zip'):
            raise HTTPException(403, 'Earth mode is available once you hold a territory.')
    return {'key': key, 'attribution': 'Map data \u00a9 Google'}


# ── V4 parcel fabric: legal lot polygons (MIGRATION_V4.md Phase 4) ────────
# Proxies each market's parcel FeatureServer so county GIS uptime is not our
# uptime and callers never learn the upstream. In-process cache per ZIP (24h).
# Markets without a configured source return {} — the frontend falls back to
# centroid dots gracefully.
#
# Two fetch modes (all sources truth-tested with live pins, 2026-07-09):
#   zip  — layer has a situs-ZIP attribute; one paginated query per ZIP.
#   pins — no situs-ZIP attribute (Dallas TAXPAZIP is mailing-only; Travis
#          and CT have none). POST IN(...) batches of parcels_v3 pins.
#          Misses are overwhelmingly condos/units, which have no individual
#          lot polygon anyway (same gap geometry_backfill documented) —
#          the frontend's dot highlight covers those.
# Same layers geometry_backfill.MARKET_CONFIGS verified 2026-06-11, except
# WA_KING which uses the WA statewide layer (KC's AGOL ZIP5 covers only
# ~half its rows; statewide SITUS_ZIP_NR matched 7,887/8.3k on 98008).
_LOT_SOURCES = {
    'WA_KING': {
        'mode': 'zip',
        'url': 'https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0/query',
        'zip_where': "SITUS_ZIP_NR LIKE '{zip}%'",
        'out_fields': 'PARCEL_ID_NR,ORIG_PARCEL_ID',
    },
    'WA_SNOHOMISH': {
        'mode': 'zip',
        'url': 'https://services6.arcgis.com/z6WYi9VRHfgwgtyW/arcgis/rest/services/CADASTRAL__parcels_timezone/FeatureServer/0/query',
        'zip_where': "SITUSZIP LIKE '{zip}%'",
        'out_fields': 'PARCEL_ID',
    },
    'AZ_MARICOPA': {
        'mode': 'zip',
        'url': 'https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0/query',
        'zip_where': "PHYSICAL_ZIP LIKE '{zip}%'",
        'out_fields': 'APN',   # undashed on layer; digit-normalization matches dashed pins
    },
    'TX_COLLIN': {
        'mode': 'zip',
        'url': 'https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/rest/services/CCAD_Parcel_Feature_Set/FeatureServer/4/query',
        'zip_where': "situsZip LIKE '{zip}%'",
        'out_fields': 'propID',
    },
    'TX_DALLAS': {
        'mode': 'pins',
        'url': 'https://gis.dallascityhall.com/arcgis/rest/services/Basemap/DallasTaxParcels/FeatureServer/0/query',
        'pin_field': 'ACCT',
        'quoted': True,
    },
    'TX_TRAVIS': {
        'mode': 'pins',
        'url': 'https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/EXTERNAL_tcad_parcel/FeatureServer/0/query',
        'pin_field': 'PROP_ID',
        'quoted': False,       # esriFieldTypeInteger
    },
    'CT_FAIRFIELD': {
        'mode': 'pins',
        'url': 'https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/Connecticut_State_Parcel_Layer_2023/FeatureServer/0/query',
        'pin_field': 'Link',
        'quoted': True,
    },
}
_LOT_CACHE: dict = {}   # zip -> (ts, {pin: geometry})
_LOT_TTL = 86400
_LOT_PAGE = 1000        # KC-statewide/Maricopa clamp at 1000; uniform page size
_LOT_PIN_BATCH = 150    # pins per POST IN(...) — ~3KB where clause, in body



_LOT_TABLE = 'lot_polygons_v3'
_lot_table_missing = False      # set once if schema/032 isn't applied


def _load_stored_lots(supa, zip_code: str) -> dict:
    """Return {pin: geometry} from lot_polygons_v3, or {} if unavailable.

    Returns {} (not an error) when schema/032 hasn't been applied yet, so
    the caller transparently falls back to the live ArcGIS crawl.
    """
    global _lot_table_missing
    if _lot_table_missing:
        return {}
    out, off = {}, 0
    try:
        while True:
            page = (supa.table(_LOT_TABLE).select('pin, geom')
                    .eq('zip_code', zip_code)
                    .range(off, off + 999).execute()).data or []
            for r in page:
                if r.get('geom'):
                    out[str(r['pin'])] = r['geom']
            if len(page) < 1000 or off >= 60000:
                break
            off += 1000
    except Exception as e:
        msg = str(e)
        if 'does not exist' in msg or 'PGRST205' in msg or '42P01' in msg:
            _lot_table_missing = True
            log.warning('[lot-polygons] %s not present — apply schema/032 to '
                        'stop re-crawling county ArcGIS on every request',
                        _LOT_TABLE)
        else:
            log.warning('[lot-polygons] stored read failed for %s: %s',
                        zip_code, e)
        return {}
    return out


def _store_lots(supa, zip_code: str, market: str, polys: dict) -> int:
    """Upsert fetched geometry. Best-effort: never breaks the response."""
    global _lot_table_missing
    if _lot_table_missing or not polys:
        return 0
    rows = [{'zip_code': zip_code, 'pin': str(pin), 'geom': geom,
             'market_key': market or None}
            for pin, geom in polys.items() if geom]
    written = 0
    try:
        for i in range(0, len(rows), 500):
            (supa.table(_LOT_TABLE)
             .upsert(rows[i:i + 500], on_conflict='zip_code,pin')
             .execute())
            written += len(rows[i:i + 500])
    except Exception as e:
        msg = str(e)
        if 'does not exist' in msg or 'PGRST205' in msg or '42P01' in msg:
            _lot_table_missing = True
            log.warning('[lot-polygons] %s not present — apply schema/032',
                        _LOT_TABLE)
        else:
            log.warning('[lot-polygons] store failed for %s: %s', zip_code, e)
    return written


@router.get("/{zip_code}/lot-polygons")
async def lot_polygons(zip_code: str,
                       authorization: str | None = Header(None),
                       x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    _gate(zip_code, authorization, x_admin_key)
    import time as _time
    hit = _LOT_CACHE.get(zip_code)
    if hit and _time.time() - hit[0] < _LOT_TTL:
        return {'zip_code': zip_code, 'polygons': hit[1], 'cached': True}

    supa = get_supabase_client()
    empty = {'zip_code': zip_code, 'polygons': {}, 'cached': False}
    if not supa:
        return empty

    # Persisted geometry first (schema/032). The live county crawl below
    # takes 20-55s per ZIP and was previously repeated after every Railway
    # redeploy, which is the bulk of the Earth-view load time.
    #
    # Partial-store guard (2026-07-24): a crawl that gets throttled upstream
    # can return few features without erroring, storing a gross partial that
    # then serves forever (seen: 75219 stuck at 1,504 of ~8,589). If stored
    # coverage is under half the ZIP's parcels, fall through and top up the
    # missing pins instead of returning the partial. Threshold is 50% (not
    # higher) because condos legitimately have no lot polygon — Dallas ZIPs
    # sit at 59-86% by design and must NOT re-crawl on every cache miss.
    stored = _load_stored_lots(supa, zip_code)
    if stored:
        try:
            _cnt = (supa.table('parcels_v3').select('pin', count='exact')
                    .eq('zip_code', zip_code).limit(1).execute()).count or 0
        except Exception:
            _cnt = 0
        if _cnt == 0 or len(stored) >= 0.5 * _cnt:
            _LOT_CACHE[zip_code] = (_time.time(), stored)
            return {'zip_code': zip_code, 'polygons': stored,
                    'cached': True, 'source': 'db'}
        log.info('[lot-polygons] %s stored partial (%d of %d parcels) — '
                 'topping up missing pins', zip_code, len(stored), _cnt)
    try:
        cov = (supa.table('zip_coverage_v3').select('market_key')
               .eq('zip_code', zip_code).limit(1).execute()).data
        market = (cov[0].get('market_key') or '') if cov else ''
        cfg = _LOT_SOURCES.get(market)
        if not cfg:
            return empty
        # PostgREST caps responses at 1000 rows regardless of .limit() —
        # paginate with .range() (same pattern as get_map_data/briefings).
        raw_pins, _off = [], 0
        while True:
            page = (supa.table('parcels_v3').select('pin')
                    .eq('zip_code', zip_code)
                    .range(_off, _off + 999).execute()).data or []
            raw_pins.extend(str(r['pin']) for r in page)
            if len(page) < 1000 or _off >= 30000:
                break
            _off += 1000
        pins = {''.join(c for c in p if c.isdigit()) for p in raw_pins}
        if not raw_pins or not zip_code.isdigit():
            return empty

        # Upstream fetch runs in a thread — a multi-second sync urllib loop
        # on the event loop stalls the single uvicorn worker.
        import asyncio, urllib.request, urllib.parse, json as _json

        def _match_into(out, features, fields):
            for f in features:
                p = f.get('properties') or {}
                for fld in fields:
                    n = ''.join(c for c in str(p.get(fld) or '') if c.isdigit())
                    if n in pins and n not in out:
                        out[n] = f['geometry']
                        break

        def _fetch_lots():
            out = dict(stored)   # top-up mode: keep what's already persisted
            if cfg['mode'] == 'zip':
                fields = cfg['out_fields'].split(',')
                offset = 0
                while True:
                    q = urllib.parse.urlencode({
                        'where': cfg['zip_where'].format(zip=zip_code),
                        'outFields': cfg['out_fields'], 'outSR': '4326',
                        'f': 'geojson', 'geometryPrecision': '6',
                        'returnGeometry': 'true',
                        'resultOffset': str(offset),
                        'resultRecordCount': str(_LOT_PAGE)})
                    d = _json.loads(urllib.request.urlopen(
                        cfg['url'] + '?' + q, timeout=45).read())
                    fs = d.get('features', [])
                    _match_into(out, fs, fields)
                    if len(fs) < _LOT_PAGE or offset >= 40000:
                        break
                    offset += _LOT_PAGE
            else:  # pins mode
                fld = cfg['pin_field']
                # In top-up mode only fetch pins we don't already have —
                # keeps the upstream load minimal (Dallas throttles bursts).
                todo = [p for p in raw_pins
                        if ''.join(c for c in p if c.isdigit()) not in out]
                for i in range(0, len(todo), _LOT_PIN_BATCH):
                    batch = todo[i:i + _LOT_PIN_BATCH]
                    vals = ','.join(
                        ("'" + b.replace("'", "") + "'") if cfg['quoted']
                        else ''.join(c for c in b if c.isdigit())
                        for b in batch)
                    body = urllib.parse.urlencode({
                        'where': f"{fld} IN ({vals})",
                        'outFields': fld, 'outSR': '4326',
                        'f': 'geojson', 'geometryPrecision': '6',
                        'returnGeometry': 'true'}).encode()
                    d = _json.loads(urllib.request.urlopen(
                        urllib.request.Request(cfg['url'], data=body),
                        timeout=45).read())
                    _match_into(out, d.get('features', []), [fld])
            return out

        polys = await asyncio.to_thread(_fetch_lots)
        _LOT_CACHE[zip_code] = (_time.time(), polys)
        if polys:
            await asyncio.to_thread(_store_lots, supa, zip_code, market, polys)
        return {'zip_code': zip_code, 'polygons': polys, 'cached': False,
                'source': 'arcgis'}
    except Exception as e:
        log.warning("[lot-polygons] %s failed: %s", zip_code, e)
        if stored:   # a partial map beats an empty one
            return {'zip_code': zip_code, 'polygons': stored,
                    'cached': True, 'source': 'db-partial'}
        return empty


@router.get("/{zip_code}")
async def get_map_data(
    zip_code: str = Depends(require_live_zip),
    include_uninvestigated: bool = Query(True,
        description="Include parcels with no investigation data"),
    limit: Optional[int] = Query(None, ge=1, le=50000,
        description="Row cap. Defaults to 30000 when slim=1, else 5000."),
    slim: bool = Query(False,
        description="Omit address/owner_name/value (only needed on click — "
                    "the dossier endpoint supplies them). Cuts the payload "
                    "~64% gzipped so a whole ZIP fits in one response."),
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """
    All parcels in a ZIP formatted for map rendering.

    Each parcel includes:
      - pin, address, owner_name, value
      - lat, lng
      - band, signal_family
      - category: call_now | build_now | hold | avoid | uninvestigated
      - pressure: 0-3 if investigated, else null
      - has_street_view: True always (can generate on demand)
    """
    _gate(zip_code, authorization, x_admin_key)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # The old hard default of 5000 silently truncated 81 of 100 live
    # territories (85255 showed 21% of its parcels), which reads on the
    # map as a random smattering of dots — PostgREST returns rows
    # unordered, so the surviving 5000 are an arbitrary slice. Slim mode
    # drops the three heavy string/number fields the map never renders,
    # making a whole-ZIP response SMALLER than the old truncated one
    # (~0.26MB gz for 20k parcels vs ~0.72MB for 5k full rows).
    if limit is None:
        limit = 30000 if slim else 5000

    try:
        # Paginated fetch to beat Supabase PostgREST server cap (typically 1000)
        def _fetch_all(table, select_cols, page_size=1000):
            out = []
            offset = 0
            while True:
                if offset >= limit:
                    break
                this_page = min(page_size, limit - offset)
                res = (supa.table(table)
                       .select(select_cols)
                       .eq('zip_code', zip_code)
                       .range(offset, offset + this_page - 1)
                       .execute())
                batch = res.data or []
                out.extend(batch)
                if len(batch) < this_page:
                    break
                offset += this_page
                if offset > 100000:
                    break
            return out

        # Fetch all parcels in this ZIP
        parcels = _fetch_all('parcels_v3',
            'pin, address, owner_name, total_value, lat, lng, band, signal_family')

        if not parcels:
            return {
                'zip': zip_code,
                'parcels': [],
                'bounds': None,
                'stats': {
                    'total': 0, 'call_now': 0, 'build_now': 0,
                    'hold': 0, 'avoid': 0, 'uninvestigated': 0,
                },
            }

        # Fetch investigation records for this ZIP (also paginated)
        pins = [p['pin'] for p in parcels]
        inv_rows = _fetch_all('investigations_v3',
            'pin, mode, action_category, action_pressure')
        inv_by_pin = {}
        for row in inv_rows:
            pin = row['pin']
            # Prefer deep over screen
            if pin not in inv_by_pin or row['mode'] == 'deep':
                inv_by_pin[pin] = row

        # Annotate parcels with category + pressure
        stats = {'call_now': 0, 'build_now': 0, 'hold': 0,
                 'avoid': 0, 'uninvestigated': 0}
        out = []
        for p in parcels:
            inv = inv_by_pin.get(p['pin'])
            if inv and inv.get('action_category'):
                cat = inv['action_category']
                pressure = inv.get('action_pressure')
            else:
                cat = 'uninvestigated'
                pressure = None

            if not include_uninvestigated and cat == 'uninvestigated':
                continue

            stats[cat] = stats.get(cat, 0) + 1
            row = {
                'pin':           p['pin'],
                'lat':           float(p['lat']) if p.get('lat') else None,
                'lng':           float(p['lng']) if p.get('lng') else None,
                'band':          p.get('band'),
                'signal_family': p.get('signal_family'),
                'category':      cat,
                'pressure':      pressure,
            }
            if not slim:
                row['address'] = p.get('address')
                row['owner_name'] = p.get('owner_name')
                row['value'] = p.get('total_value')
            out.append(row)

        # Bbox outlier filter — drop parcels whose coords sit > ~10 mi
        # from the ZIP's median centroid. These are KC ingest
        # contamination (parcels tagged with ZIP5=X whose geometry sits
        # in ZIP Y). Source data we can't fix; we just refuse to render
        # the visibly-wrong dots on the map.
        coords_with_idx = [(i, p['lat'], p['lng']) for i, p in enumerate(out)
                           if p['lat'] is not None and p['lng'] is not None]
        filtered_count = 0
        if coords_with_idx:
            med_lat, med_lng, outlier_positions = _filter_bbox_outliers(
                [(c[1], c[2]) for c in coords_with_idx])
            # Map positions in coords_with_idx back to indices in `out`
            outlier_out_indices = {coords_with_idx[pos][0]
                                   for pos in outlier_positions}
            if outlier_out_indices:
                filtered_count = len(outlier_out_indices)
                # Decrement category stats for filtered parcels
                for idx in outlier_out_indices:
                    cat = out[idx]['category']
                    stats[cat] = max(0, stats.get(cat, 0) - 1)
                out = [p for i, p in enumerate(out)
                       if i not in outlier_out_indices]

        # Compute bounding box from filtered parcels with coords
        coords = [(p['lat'], p['lng']) for p in out if p['lat'] and p['lng']]
        bounds = None
        if coords:
            lats = [c[0] for c in coords]
            lngs = [c[1] for c in coords]
            bounds = {
                'min_lat': min(lats),
                'max_lat': max(lats),
                'min_lng': min(lngs),
                'max_lng': max(lngs),
                'center': {
                    'lat': (min(lats) + max(lats)) / 2,
                    'lng': (min(lngs) + max(lngs)) / 2,
                },
            }

        return {
            'zip':     zip_code,
            'parcels': out,
            'bounds':  bounds,
            'stats':   {'total': len(out), **stats,
                        'filtered_out_of_bbox': filtered_count},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching map data: {e}")


@router.get("/{zip_code}/bounds")
async def get_zip_bounds(
    zip_code: str = Depends(require_live_zip),
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """Bounding box for a ZIP — used to center map on load.

    Applies the same bbox-outlier filter as /map so the initial zoom
    isn't pulled wide by contaminated parcels (e.g., 98053 has parcels
    tagged with ZIP5=98053 whose geometry sits in Seattle — without
    filtering, the map would initially zoom to span Seattle→Snoqualmie).
    """
    _gate(zip_code, authorization, x_admin_key)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        result = (supa.table('parcels_v3')
                  .select('lat, lng')
                  .eq('zip_code', zip_code)
                  .not_.is_('lat', 'null')
                  .limit(10000)
                  .execute())
        rows = result.data or []
        coords = [(float(r['lat']), float(r['lng']))
                  for r in rows if r.get('lat') and r.get('lng')]

        if not coords:
            raise HTTPException(404, f"No geocoded parcels in {zip_code}")

        # Strip outliers before computing bounds
        _med_lat, _med_lng, outlier_positions = _filter_bbox_outliers(coords)
        filtered = [c for i, c in enumerate(coords)
                    if i not in outlier_positions]
        # Fallback: if filtering removed everything (shouldn't happen on
        # a ZIP with > 50 parcels — would mean median itself is junk),
        # fall back to the unfiltered set rather than 404.
        use = filtered if filtered else coords

        lats = [c[0] for c in use]
        lngs = [c[1] for c in use]

        return {
            'zip': zip_code,
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lng': min(lngs),
            'max_lng': max(lngs),
            'center':  {'lat': (min(lats) + max(lats)) / 2,
                        'lng': (min(lngs) + max(lngs)) / 2},
            'parcel_count': len(use),
            'filtered_out_of_bbox': len(coords) - len(use),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching bounds: {e}")


# ============================================================================
# Street View — signed static URLs for property photos
# ============================================================================

def _sign_url(url: str, secret: str) -> str:
    """
    Sign a Google Street View Static URL with the URL signing secret.
    Required for production use. See:
    https://developers.google.com/maps/documentation/streetview/digital-signature
    """
    # Split URL into base + query
    parsed = url.replace('https://', '').split('?', 1)
    path = '/' + parsed[0].split('/', 1)[1] if '/' in parsed[0] else '/'
    url_to_sign = path + '?' + parsed[1] if len(parsed) > 1 else path

    # Decode secret from URL-safe base64
    decoded_key = base64.urlsafe_b64decode(secret + '=' * (4 - len(secret) % 4))

    # Sign
    signature = hmac.new(decoded_key, url_to_sign.encode(), hashlib.sha1).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode()

    return url + '&signature=' + encoded_signature


@router.get("/streetview/{pin}")
async def get_streetview_url(
    pin: str,
    size: str = Query("640x400", pattern=r"^\d{2,4}x\d{2,4}$"),
    fov: int = Query(80, ge=20, le=120),
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """
    Returns a Google Street View Static URL for a parcel.
    Uses the parcel's lat/lng to center the camera.

    The URL is signed if GOOGLE_STREET_VIEW_SECRET is set (required for
    production volume). In development, unsigned URLs work up to a free tier.
    """
    api_key = os.environ.get('GOOGLE_STREET_VIEW_API_KEY') or os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        raise HTTPException(503, "Google Maps key not configured")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        result = (supa.table('parcels_v3')
                  .select('zip_code, lat, lng, address')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
        parcel = result.data if result else None

        if not parcel or not parcel.get('lat'):
            raise HTTPException(404, f"Parcel {pin} has no geocoded location")

        _gate(parcel.get('zip_code'), authorization, x_admin_key)

        params = {
            'size':     size,
            'location': f"{parcel['lat']},{parcel['lng']}",
            'fov':      fov,
            'source':   'outdoor',
            'key':      api_key,
        }
        base_url = 'https://maps.googleapis.com/maps/api/streetview'
        url = f"{base_url}?{urlencode(params)}"

        # Sign if secret is configured
        secret = os.environ.get('GOOGLE_STREET_VIEW_SECRET')
        if secret:
            url = _sign_url(url, secret)

        return {
            'pin':     pin,
            'address': parcel.get('address'),
            'url':     url,
            'signed':  bool(secret),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error generating Street View URL: {e}")
