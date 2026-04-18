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
from fastapi import APIRouter, HTTPException, Query
from backend.api.db import get_supabase_client
import os
import hmac
import hashlib
import base64
from urllib.parse import quote, urlencode

router = APIRouter()


# ============================================================================
# Map data — heatmap + pin payload
# ============================================================================

@router.get("/{zip_code}")
async def get_map_data(
    zip_code: str,
    include_uninvestigated: bool = Query(True,
        description="Include parcels with no investigation data"),
    limit: int = Query(5000, ge=1, le=20000),
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
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        # Fetch all parcels in this ZIP
        parcels_res = (supa.table('parcels_v3')
                       .select('pin, address, owner_name, total_value, lat, lng, band, signal_family')
                       .eq('zip_code', zip_code)
                       .limit(limit)
                       .execute())
        parcels = parcels_res.data or []

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

        # Fetch investigation records for this ZIP in one query
        pins = [p['pin'] for p in parcels]
        inv_res = (supa.table('investigations_v3')
                   .select('pin, mode, action_category, action_pressure')
                   .eq('zip_code', zip_code)
                   .execute())
        inv_by_pin = {}
        for row in (inv_res.data or []):
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
            out.append({
                'pin':           p['pin'],
                'address':       p.get('address'),
                'owner_name':    p.get('owner_name'),
                'value':         p.get('total_value'),
                'lat':           float(p['lat']) if p.get('lat') else None,
                'lng':           float(p['lng']) if p.get('lng') else None,
                'band':          p.get('band'),
                'signal_family': p.get('signal_family'),
                'category':      cat,
                'pressure':      pressure,
            })

        # Compute bounding box from parcels with coords
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
            'stats':   {'total': len(out), **stats},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching map data: {e}")


@router.get("/{zip_code}/bounds")
async def get_zip_bounds(zip_code: str):
    """Bounding box for a ZIP — used to center map on load."""
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
        coords = [(r['lat'], r['lng']) for r in rows if r.get('lat') and r.get('lng')]

        if not coords:
            raise HTTPException(404, f"No geocoded parcels in {zip_code}")

        lats = [float(c[0]) for c in coords]
        lngs = [float(c[1]) for c in coords]

        return {
            'zip': zip_code,
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lng': min(lngs),
            'max_lng': max(lngs),
            'center':  {'lat': (min(lats) + max(lats)) / 2,
                        'lng': (min(lngs) + max(lngs)) / 2},
            'parcel_count': len(coords),
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
    size: str = Query("640x400", regex=r"^\d{2,4}x\d{2,4}$"),
    fov: int = Query(80, ge=20, le=120),
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
                  .select('lat, lng, address')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
        parcel = result.data if result else None

        if not parcel or not parcel.get('lat'):
            raise HTTPException(404, f"Parcel {pin} has no geocoded location")

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
