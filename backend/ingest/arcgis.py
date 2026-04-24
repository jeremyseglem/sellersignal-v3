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
        # Parcel address + property info service.
        #
        # History: this config previously pointed at
        #   https://gismaps.kingcounty.gov/arcgis/rest/services/Property/
        #   KingCo_Parcels/MapServer/0
        # which is a geometry-only layer with 7 fields (PIN, MAJOR, MINOR,
        # Shape, ...). Every ingest query silently returned HTTP 200 with
        # a JSON 400-error body because we were asking for fields that do
        # not exist on that layer (ZIP5, OwnerName, AddressLine1, etc).
        #
        # The correct endpoint is property__parcel_address_area layer 1722
        # under the OpenDataPortal service. It has 66 fields including all
        # the property details we care about. Field names differ from the
        # previous config; see _parse_feature for the mapping.
        #
        # This endpoint does NOT expose owner name or owner mailing
        # street address (KC filters those out per RCW 42.56.070(8), the
        # commercial-use prohibition). It DOES expose taxpayer city +
        # state (KCTP_CITY, KCTP_STATE), which is sufficient to compute
        # is_out_of_state. Owner name and full taxpayer mailing street
        # come from the separate eReal Property harvester (see Fix 3 —
        # ereal_property.py).
        'url': (
            'https://gisdata.kingcounty.gov/arcgis/rest/services/'
            'OpenDataPortal/property__parcel_address_area/MapServer/1722/query'
        ),
        'zip_field': 'ZIP5',
        'out_fields': (
            'PIN,ADDR_FULL,ZIP5,KCTP_CITY,KCTP_STATE,'
            'APPRLNDVAL,APPR_IMPR,PROPTYPE,LOTSQFT,KCA_ACRES,'
            'LAT,LON,CTYNAME,POSTALCTYNAME'
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


def _parse_float(raw) -> Optional[float]:
    """Parse numeric value preserving decimals (for acres: NUMERIC(10,3))."""
    if raw is None or raw == '':
        return None
    try:
        cleaned = str(raw).replace(',', '').strip()
        return round(float(cleaned), 3)
    except (ValueError, TypeError):
        return None


def _derive_owner_type(owner_name: str) -> str:
    """
    Route owner_name to owner_type for structural classification.
    Identical to the classifier used by why_not_selling.

    Known previous bug: dotted entity abbreviations (L.L.C., L.P., L.L.P.)
    and bare LLP / LP were missed, causing LLP-named entities like
    "BELLEVUE I LLP WALLACE/SCOTT" to be classified as 'individual' and
    zeroing out the MATURE LLC parcel-state tag.

    Second pass (verified against 818 production 98004 mismatches):
      - TTEE / TTEES is a common assessor abbreviation for 'trustee';
        names ending "-TTEE" or "-TTEES" are trusts.
      - Entity abbreviations show up with internal spaces in assessor
        data: "L L C", "L L P", "L P" — normalize those by collapsing
        runs of single capital letters separated by whitespace into
        concatenated tokens.
      - Government entities (CITY OF / COUNTY OF / US OF AMERICA /
        SCHOOL DIST / WATER DIST / PUBLIC UTILITY) have their own
        classification — keep them separate from 'individual' so they
        don't end up on seller-intent briefings.
      - "LT+TTEE" and "-LT+TTEE" patterns (life-estate + trustee) also
        indicate a trust arrangement.

    Fix: strip periods, collapse "L L C" → "LLC" (and variants), add
    TTEE/TTEES/LT+TTEE trust patterns, recognize government entities,
    add LLP/LP and dotted variants.
    """
    if not owner_name:
        return 'unknown'
    on = owner_name.upper()

    # Normalize dotted forms: L.L.C. -> LLC, L.P. -> LP, etc.
    on_norm = on.replace('.', '')
    # Normalize space-separated single-letter abbreviations: "L L C" ->
    # "LLC", "L L P" -> "LLP", "L P" -> "LP". Run the regex twice since
    # a single pass can leave "A B C D E" partially collapsed.
    #   Matches two-or-more single letters separated by whitespace.
    on_norm = re.sub(r'\b([A-Z])\s+([A-Z])\s+([A-Z])\b', r'\1\2\3', on_norm)
    on_norm = re.sub(r'\b([A-Z])\s+([A-Z])\b', r'\1\2', on_norm)

    # Government entities first — before trust/llc so we don't mis-route
    # "CITY OF BELLEVUE" into individual or llc on later rules.
    if re.search(
        r'\b(?:CITY\s+OF|COUNTY\s+OF|STATE\s+OF|US\s+OF\s+AMERICA|'
        r'PORT\s+OF|UNITED\s+STATES|FEDERAL|MUNICIPAL|'
        r'SCHOOL\s+DIST(?:RICT)?|PUBLIC\s+UTIL|WATER\s+DIST|'
        r'PARK\s+DIST|FIRE\s+DIST|HOUSING\s+AUTH)\b',
        on_norm,
    ):
        return 'gov'

    # Trust BEFORE estate because many estate-like tokens ("SURVIVOR")
    # appear inside explicit trust names ("SURVIVORS TRUST"). If both
    # TRUST and SURVIVOR show up, the structure is a trust, not an
    # informal estate. Also covers -TTEE / LT+TTEE / REV LVG TR
    # abbreviations the assessor uses.
    if re.search(
        r'\bTRUST\b|\bTRSTEE\b|\bTRUSTEE\b|\bTTEE\b|\bTTEES\b|'
        r'\bLIVING\s*TR\b|\bFAMILY\s*TR\b|\bLT\s*\+\s*TTEE\b|'
        r'-TTEE\b|-TTEES\b|-LT\b',
        on_norm,
    ):
        return 'trust'

    if re.search(
        r'\bESTATE\b|\bHEIRS\b|\bDECEASED\b|\bSURVIVOR\b',
        on_norm,
    ):
        return 'estate'

    # Nonprofit — BEFORE llc so "FIRST BAPTIST CHURCH INC" correctly
    # routes to nonprofit rather than matching INC first.
    #
    # Unambiguous keywords (SYNAGOGUE, MOSQUE, YMCA, etc.) match
    # anywhere in the name. A few keywords (CHURCH, TEMPLE, PARISH,
    # CHAPEL) can also be surnames — in assessor format "LASTNAME
    # FIRST", surnames appear first. For those, we require either
    # a preceding word ("FIRST PRESBYTERIAN CHURCH") OR the keyword
    # followed by OF / IN ("CHURCH OF LATTER DAY SAINTS"). This
    # avoids mis-classifying "CHURCH JOHN" / "TEMPLE JOHN" as
    # organizations.
    if re.search(
        r'\bSYNAGOGUE\b|\bMOSQUE\b|'
        r'\bCATHEDRAL\b|'
        r'\bARCHDIOCESE\b|\bDIOCESE\b|'
        r'\bYMCA\b|\bYWCA\b|\bYMHA\b|'
        r'\bNONPROFIT\b|\bNON-PROFIT\b|\bNOT\s+FOR\s+PROFIT\b|'
        r'\bCHARITY\b|\bCHARITABLE\b|'
        r'\bMINISTRY\b|\bMINISTRIES\b|'
        r'\bCONGREGATION\b|\bFELLOWSHIP\b',
        on_norm,
    ):
        return 'nonprofit'
    # Position-sensitive: require a preceding word OR keyword+OF/IN.
    # KC assessor format is surname-first ("TEMPLE JOHN"), so
    # organizations never appear as "JOHN TEMPLE" in production.
    # Also match "TEMPLE + 2+ words" for Jewish congregation naming
    # ("TEMPLE BETH AM", "TEMPLE DE HIRSCH SINAI") where TEMPLE leads
    # the name.
    if re.search(
        r'\S+\s+(?:CHURCH|TEMPLE|PARISH|CHAPEL)\b|'
        r'\b(?:CHURCH|TEMPLE|PARISH|CHAPEL)\s+(?:OF|IN)\b|'
        r'\bTEMPLE\s+\S+\s+\S+',
        on_norm,
    ):
        return 'nonprofit'

    if re.search(
        r'\b(?:LLC|LLP|LP|INC|CORP|LTD|'
        r'PARTNERSHIP|PARTNERS|'
        r'HOLDINGS|GROUP|ENTERPRISES?|'
        r'LIMITED\s+LIABILITY\s+COMPANY)\b',
        on_norm,
    ):
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
    """
    Convert a raw ArcGIS feature into a parcels_v3 row dict.

    Field mapping from OpenDataPortal/property__parcel_address_area/1722:
      PIN              -> pin (primary key)
      ADDR_FULL        -> address (site)
      CTYNAME          -> city (site city)
      ZIP5             -> (already known from query)
      KCTP_CITY        -> owner_city (taxpayer mailing city)
      KCTP_STATE       -> owner_state (taxpayer mailing state)
      APPRLNDVAL       -> land_value
      APPR_IMPR        -> building_value (appraised improvements)
      PROPTYPE         -> prop_type
      LOTSQFT          -> lot_sqft (not building sqft — that's eReal
                          Property only)
      KCA_ACRES        -> acres
      LAT, LON         -> lat, lng

    Fields INTENTIONALLY NOT on this layer:
      - owner_name, owner_name_raw: KC doesn't expose on public ArcGIS.
        Pulled separately by backend/harvesters/ereal_property.py
        (Fix 3). During re-ingest we do NOT overwrite owner_name on
        existing rows — the upsert only sets it if we have a value.
      - owner_address (street): not available in the ArcGIS layer, see
        the eReal Property harvester.
      - year_built, sqft, bedrooms, baths: detail-page-only fields.

    The previous version of this function computed is_absentee by
    comparing situs street address to owner street. Since we don't have
    owner street here, is_absentee drops back to the taxpayer-city
    heuristic: absentee IF the taxpayer city is different from the
    site city. Coarser but meaningful — if taxpayer mailing goes to a
    different city, they don't live in the property.
    """
    attrs = feature.get('attributes', {}) or {}
    geom = feature.get('geometry', {}) or {}

    pin = str(attrs.get('PIN', '')).strip()
    address        = (attrs.get('ADDR_FULL') or '').strip()
    site_city      = (attrs.get('CTYNAME') or
                      attrs.get('POSTALCTYNAME') or '').strip()

    owner_city  = (attrs.get('KCTP_CITY') or '').strip()
    owner_state = (attrs.get('KCTP_STATE') or '').strip()

    # Lat/lng: this layer exposes LAT/LON attributes directly; fall
    # back to geometry centroid if missing.
    lat = attrs.get('LAT')
    lng = attrs.get('LON')
    if lat is None or lng is None:
        lat, lng = _extract_lat_lng(geom)

    default_state = config['default_state']
    state = site_state_from_city(site_city) or default_state

    # Absentee heuristic: taxpayer city differs from site city (case-
    # insensitive). Conservative — missing taxpayer city means we can't
    # tell, so False.
    #
    # CAVEAT: this will fire on adjacent-city crossovers (Ballmer's
    # Hunts Point home with a Bellevue taxpayer mailing, for example).
    # Those aren't "absentee" in the usual sense — they're just someone
    # getting mail at a nearby city. For a harder check, look at
    # is_out_of_state, which only fires when the taxpayer STATE differs
    # from the site state (i.e. genuine OOS ownership, which is the
    # seller signal we actually care about for absentee_oos_disposition).
    is_absentee = bool(owner_city and site_city
                       and owner_city.strip().upper()
                           != site_city.strip().upper())
    is_out_of_state = bool(owner_state) and owner_state.upper() != state.upper()

    return {
        'pin':              pin,
        'zip_code':         zip_code,
        'market_key':       market_key,
        'address':          address,
        'city':             site_city or None,
        'state':            state,
        # Owner name & raw are NOT touched during ArcGIS re-ingest. Upsert
        # merges on 'pin' conflict but only overwrites columns we include
        # in the payload. By omitting owner_name / owner_name_raw /
        # owner_type, we preserve any existing value (loaded via eReal
        # Property harvester or older ingest).
        'owner_city':       owner_city or None,
        'owner_state':      owner_state or None,
        'lat':              lat,
        'lng':              lng,
        'total_value':      (
            (_parse_value(attrs.get('APPRLNDVAL')) or 0)
            + (_parse_value(attrs.get('APPR_IMPR')) or 0)
        ) or None,
        'land_value':       _parse_value(attrs.get('APPRLNDVAL')),
        'building_value':   _parse_value(attrs.get('APPR_IMPR')),
        'acres':            _parse_float(attrs.get('KCA_ACRES')),
        'prop_type':        (attrs.get('PROPTYPE') or '').strip() or None,
        'is_absentee':      is_absentee,
        'is_out_of_state':  is_out_of_state,
        # is_vacant_land: building value 0 means no improvements ≈ vacant
        'is_vacant_land':   not bool(_parse_value(attrs.get('APPR_IMPR'))),
    }


def site_state_from_city(city: str) -> Optional[str]:
    """
    Derive state from site city for King County. All King County cities
    are in WA, but we expose this helper so ingest for other counties
    can override. Returns None if the city is unknown; caller falls
    back to config['default_state'].
    """
    if not city:
        return None
    # All KC cities are WA. Keep the function so future markets can
    # override per-county rules.
    return 'WA'


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
