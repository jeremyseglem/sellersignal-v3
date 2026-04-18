"""
King County ArcGIS parcel ingest.

Pulls parcels for a given ZIP from King County's Property Parcels feature
service, parses the fields, and upserts into parcels_v3. This replaces
the sandbox's CSV-based ingest path — direct HTTP fetch suitable for
Railway and for re-running on any ZIP in the WA_KING market.

Data source:
  https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0

Pagination is handled via ArcGIS's resultOffset. Each page caps at 2000
features. We loop until `exceededTransferLimit=false` or we hit a safety
cap of 20000 features per ZIP (no ZIP in King County has more than ~12K
residential parcels).

Fields pulled and their parcels_v3 mapping:
  PARCELID           -> pin (primary key)
  OwnerName          -> owner_name_raw
  AddressLine1       -> address
  CityStateZip       -> city (parsed), state (parsed)
  TotalValue         -> total_value
  TotalBuildingValue -> building_value
  TotalLandValue     -> land_value
  PropType           -> prop_type
  GISAcres           -> acres
  OwnerAddress1      -> owner_address
  OwnerCity          -> owner_city
  OwnerState         -> owner_state
  OwnerZipCode       -> owner_zip
  (geometry)         -> lat, lng
"""
from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

try:
    import httpx
except ImportError:
    httpx = None  # will raise at runtime if ingest is called without httpx


# ============================================================================
# Configuration per market
# ============================================================================

MARKET_CONFIGS = {
    'WA_KING': {
        'url': 'https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0/query',
        'zip_field': 'ZIP5',
        'out_fields': (
            'PARCELID,OwnerName,AddressLine1,CityStateZip,TotalValue,'
            'TotalBuildingValue,TotalLandValue,PropType,GISAcres,'
            'OwnerAddress1,OwnerCity,OwnerState,OwnerZipCode,Subdivision'
        ),
        'default_state': 'WA',
    },
}

PAGE_SIZE = 2000
SAFETY_CAP = 20000
REQUEST_TIMEOUT_SECONDS = 90


# ============================================================================
# Helpers
# ============================================================================

def _parse_city_state(city_state_zip: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse 'BELLEVUE WA 98004' or 'Bellevue, WA 98004' format.
    Returns (city, state) — both may be None if parse fails.
    """
    if not city_state_zip:
        return None, None
    s = city_state_zip.strip().replace(',', '')
    # Match: CITY (words) STATE (2 letters) ZIP (digits)
    m = re.match(r'^([A-Za-z\s]+?)\s+([A-Z]{2})\s+\d{5}', s)
    if m:
        return m.group(1).strip().title(), m.group(2)
    # Fallback: just extract 2-letter state if present
    m = re.search(r'\b([A-Z]{2})\b', s)
    return None, m.group(1) if m else None


def _parse_value(raw) -> Optional[int]:
    """Parse numeric value from ArcGIS. Handles None, empty, commas, floats."""
    if raw is None or raw == '':
        return None
    try:
        # Strip commas, handle floats
        cleaned = str(raw).replace(',', '').strip()
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _derive_owner_type(owner_name: str) -> str:
    """
    Route owner_name to owner_type for structural classification.
    Identical to the classifier used by why_not_selling.
    """
    if not owner_name:
        return 'unknown'
    on = owner_name.upper()
    if re.search(r'\bESTATE\b|\bHEIRS\b|\bDECEASED\b|\bSURVIVOR\b', on):
        return 'estate'
    if re.search(r'\bTRUST\b|\bTRSTEE\b|\bTRUSTEE\b|\bLIVING\s*TR\b|\bFAMILY\s*TR\b', on):
        return 'trust'
    if re.search(r'\bLLC\b|\bINC\b|\bCORP\b|\bLTD\b|\bPARTNERSHIP\b|'
                 r'\bHOLDINGS\b|\bGROUP\b|\bENTERPRISES?\b|\bPARTNERS\b', on):
        return 'llc'
    return 'individual'


def _normalize_owner_display_name(raw: str) -> str:
    """
    Convert assessor format ('HENDERSON MARGARET') to display format
    ('Margaret Henderson'). For entities, preserve raw with Title Case.
    """
    if not raw:
        return ''
    raw = raw.strip()
    owner_type = _derive_owner_type(raw)
    if owner_type in ('trust', 'llc', 'estate'):
        # Entities: preserve structure, Title Case everything except common
        # abbreviations (LLC, INC, etc.)
        parts = raw.split()
        normalized = []
        for p in parts:
            if p.upper() in ('LLC', 'INC', 'CORP', 'LTD', 'LP', 'LLP'):
                normalized.append(p.upper())
            else:
                normalized.append(p.capitalize())
        return ' '.join(normalized)
    # Individual: assessor stores as 'LAST FIRST' or 'LAST FIRST MIDDLE'
    # Also handles '&' as in 'SMITH JOHN & MARY'
    primary = raw.split('&')[0].strip()
    parts = primary.split()
    if len(parts) >= 2:
        last = parts[0].capitalize()
        first_middle = ' '.join(p.capitalize() for p in parts[1:])
        return f"{first_middle} {last}"
    return primary.capitalize()


def _is_absentee(situs_address: str, owner_address: str) -> bool:
    """True if owner's mailing address differs from the property situs."""
    if not situs_address or not owner_address:
        return False
    a = re.sub(r'\s+', '', situs_address.upper())
    b = re.sub(r'\s+', '', owner_address.upper())
    # Check prefix match on first 10 characters (accounts for unit suffixes)
    if len(a) >= 5 and len(b) >= 5:
        return not (a.startswith(b[:min(10, len(b))]) or b.startswith(a[:min(10, len(a))]))
    return False


# ============================================================================
# Main ingest function
# ============================================================================

async def fetch_parcels_for_zip(
    zip_code: str,
    market_key: str = 'WA_KING',
) -> list[dict]:
    """
    Fetch all parcels for a ZIP from the market's ArcGIS endpoint.
    Returns a list of dicts in parcels_v3 schema.

    Paginates automatically. Handles 2000-feature page cap.
    Returns empty list if market isn't configured or no parcels found.
    """
    if httpx is None:
        raise ImportError("httpx is required for ingest. pip install httpx")

    config = MARKET_CONFIGS.get(market_key)
    if not config:
        raise ValueError(f"Market {market_key} not configured for ingest")

    all_features = []
    offset = 0

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        while len(all_features) < SAFETY_CAP:
            params = {
                'where': f"{config['zip_field']}='{zip_code}'",
                'outFields': config['out_fields'],
                'returnGeometry': 'true',
                'outSR': '4326',  # WGS84 for Leaflet
                'f': 'json',
                'resultRecordCount': str(PAGE_SIZE),
                'resultOffset': str(offset),
            }
            url = f"{config['url']}?{urlencode(params)}"

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                print(f"[arcgis] error fetching page at offset {offset}: {e}")
                break

            features = data.get('features', [])
            all_features.extend(features)

            capped = data.get('exceededTransferLimit') is True
            if not features or (not capped and len(features) < PAGE_SIZE):
                break

            offset += len(features)
            # Small pause between pages (be polite to the free endpoint)
            await asyncio.sleep(0.3)

    return [_parse_feature(f, zip_code, market_key, config) for f in all_features]


def _parse_feature(feature: dict, zip_code: str, market_key: str, config: dict) -> dict:
    """Convert a raw ArcGIS feature into a parcels_v3 row dict."""
    attrs = feature.get('attributes', {}) or {}
    geom = feature.get('geometry', {}) or {}

    pin = str(attrs.get('PARCELID', '')).strip()
    owner_name_raw = (attrs.get('OwnerName') or '').strip()
    address = (attrs.get('AddressLine1') or '').strip()
    city_state_zip = attrs.get('CityStateZip') or ''
    city, state = _parse_city_state(city_state_zip)
    state = state or config['default_state']

    owner_address = (attrs.get('OwnerAddress1') or '').strip()
    owner_city = (attrs.get('OwnerCity') or '').strip()
    owner_state = (attrs.get('OwnerState') or '').strip()
    owner_zip = (attrs.get('OwnerZipCode') or '').strip()

    # Lat/lng from geometry (ArcGIS polygon -> use centroid, but for simple
    # point parcels or ring geometries we need to compute)
    lat, lng = _extract_lat_lng(geom)

    owner_type = _derive_owner_type(owner_name_raw)
    owner_name = _normalize_owner_display_name(owner_name_raw)
    is_absentee = _is_absentee(address, owner_address)
    is_out_of_state = bool(owner_state) and owner_state.upper() != state.upper()

    return {
        'pin':              pin,
        'zip_code':         zip_code,
        'market_key':       market_key,
        'address':          address,
        'city':             city,
        'state':            state,
        'owner_name_raw':   owner_name_raw,
        'owner_name':       owner_name,
        'owner_type':       owner_type,
        'owner_address':    owner_address,
        'owner_city':       owner_city,
        'owner_state':      owner_state,
        'owner_zip':        owner_zip,
        'lat':              lat,
        'lng':              lng,
        'total_value':      _parse_value(attrs.get('TotalValue')),
        'land_value':       _parse_value(attrs.get('TotalLandValue')),
        'building_value':   _parse_value(attrs.get('TotalBuildingValue')),
        'acres':            _parse_value(attrs.get('GISAcres')),  # handles as int, ok for ~2 decimal precision rough
        'prop_type':        (attrs.get('PropType') or '').strip(),
        'is_absentee':      is_absentee,
        'is_out_of_state':  is_out_of_state,
        'is_vacant_land':   bool(attrs.get('TotalBuildingValue')) is False,
    }


def _extract_lat_lng(geom: dict) -> tuple[Optional[float], Optional[float]]:
    """
    Compute a point from ArcGIS geometry.
      - Point geometry: use directly
      - Polygon geometry: compute centroid from first ring
    Returns (lat, lng) or (None, None) if geometry missing/malformed.
    """
    if not geom:
        return None, None

    # Point geometry
    if 'x' in geom and 'y' in geom:
        return float(geom['y']), float(geom['x'])

    # Polygon: first ring centroid
    rings = geom.get('rings') or []
    if rings and rings[0]:
        ring = rings[0]
        if not ring:
            return None, None
        xs = [p[0] for p in ring if len(p) >= 2]
        ys = [p[1] for p in ring if len(p) >= 2]
        if xs and ys:
            return sum(ys) / len(ys), sum(xs) / len(xs)

    return None, None


# ============================================================================
# Upsert into Supabase
# ============================================================================

def upsert_parcels(parcels: list[dict]) -> dict:
    """
    Upsert a batch of parcels into parcels_v3.
    Batches to 1000 rows per request to avoid payload limits.

    Returns stats: { inserted_or_updated, failed }.
    """
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured")

    stats = {'inserted_or_updated': 0, 'failed': 0, 'batches': 0}
    if not parcels:
        return stats

    for i in range(0, len(parcels), 1000):
        batch = parcels[i:i + 1000]
        try:
            supa.table('parcels_v3').upsert(batch, on_conflict='pin').execute()
            stats['inserted_or_updated'] += len(batch)
            stats['batches'] += 1
        except Exception as e:
            print(f"[arcgis.upsert] batch {stats['batches']} failed: {e}")
            stats['failed'] += len(batch)

    return stats


def stamp_ingest_complete(zip_code: str, parcel_count: int) -> None:
    """Mark ingest stage complete in zip_coverage_v3."""
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        return
    supa.table('zip_coverage_v3').update({
        'parcels_ingested_at': datetime.now(timezone.utc).isoformat(),
        'parcel_count':        parcel_count,
        'updated_at':          datetime.now(timezone.utc).isoformat(),
    }).eq('zip_code', zip_code).execute()
