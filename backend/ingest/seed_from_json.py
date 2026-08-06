"""
seed_from_json.py — Load parcels from a pre-built JSON file into parcels_v3.

This is an alternative to the live ArcGIS fetch, used when:
  - The live ArcGIS endpoint is unreachable or misconfigured
  - We have a known-good data snapshot we want to import
  - We're bootstrapping a new ZIP with sandbox data

The JSON file shape is a dict keyed by PIN, with each value a dict containing:
    {
      "owner_name": "LI ZHI",
      "last_transfer_date": "2016-10-27",
      "tenure_years": 9.5,
      "sale_price": "1560000",
      "address": "10215 SE 16TH ST",
      "value": 2409000,
      "owner_type": "individual"
    }

This command reads such a file, normalizes to parcels_v3 schema, and upserts.
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _derive_flags(parcel: dict) -> dict:
    """Compute is_absentee, is_out_of_state from parcel data where possible.

    2026-06-12: when the SEED itself carries explicit is_absentee /
    is_out_of_state (Dallas + Travis builders compute them against the real
    situs state), trust the seed — deriving here against row['state'] burned
    us when a missing ?state= param defaulted the row to WA and flagged
    7,573 of 8,536 Travis parcels (every TX-resident owner) absentee.

    When the seed carries owner_state (mailing state — AZ seeds do as of
    2026-06-10), is_out_of_state is computed against the parcel's own
    situs state. Seeds without owner_state (legacy KC/SNO shape) keep the
    bootstrap False defaults; reingest-property-details sets them later.
    """
    if parcel.get('_seed_is_absentee') is not None:
        return {
            'is_absentee':     bool(parcel.get('_seed_is_absentee')),
            'is_out_of_state': bool(parcel.get('_seed_is_out_of_state')),
            'is_vacant_land':  False,
        }
    owner_state = (parcel.get('owner_state') or '').strip().upper()
    home_state = (parcel.get('state') or '').strip().upper()
    if owner_state and home_state:
        oos = (len(owner_state) == 2 and owner_state.isalpha()
               and owner_state != home_state)
        return {
            'is_absentee':     oos,
            'is_out_of_state': oos,
            'is_vacant_land':  False,
        }
    return {
        'is_absentee':     False,
        'is_out_of_state': False,
        'is_vacant_land':  False,
    }


def _normalize_display_name(raw: str) -> str:
    """Convert assessor format 'SMITH JOHN' to display 'John Smith'."""
    if not raw:
        return ''
    raw = raw.strip()
    upper = raw.upper()
    # Entities: Title Case but preserve LLC/INC/CORP
    if any(k in upper for k in ('LLC', 'INC', 'CORP', 'LTD', 'TRUST', 'ESTATE', 'HOLDINGS')):
        parts = raw.split()
        return ' '.join(
            p.upper() if p.upper() in ('LLC', 'INC', 'CORP', 'LTD', 'LP', 'LLP') else p.capitalize()
            for p in parts
        )
    # Individual: assessor stores as LAST FIRST [MIDDLE]; handle '&' and '+'
    primary = re.split(r'[&+]', raw)[0].strip()
    parts = primary.split()
    if len(parts) >= 2:
        last = parts[0].capitalize()
        rest = ' '.join(p.capitalize() for p in parts[1:])
        return f"{rest} {last}"
    return primary.capitalize()


def _to_int(v) -> int | None:
    """Parse an int from str/float/int, returning None on failure."""
    if v is None or v == '': return None
    try:
        return int(float(str(v).replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


_MARKET_STATE = {
    "CT_FAIRFIELD": "CT",
    "TX_COLLIN": "TX",
    'WA_KING':      'WA',
    'WA_SNOHOMISH': 'WA',
    'AZ_MARICOPA':  'AZ',
    'TX_DALLAS':    'TX',
    'TX_TRAVIS':    'TX',   # was missing — same 'Phoenix, WA' bug class
    'MT_GALLATIN':  'MT',
    'MT_PARK':     'MT',
    'MT_FLATHEAD':  'MT',
    'FL_COLLIER':    'FL',
    'FL_PALM_BEACH': 'FL',
    'MA_MIDDLESEX': 'MA',
    'MA_NORFOLK':   'MA',
    'MA_ESSEX':     'MA',
    'MA_PLYMOUTH':  'MA',
    'MA_DUKES':     'MA',
    'TN_DAVIDSON':  'TN',
    'CO_PITKIN':    'CO',
    'CO_DENVER':    'CO',
    'CO_BOULDER':   'CO',
    'CO_ARAPAHOE':  'CO',
    'NC_BUNCOMBE': 'NC',
    'WI_MILWAUKEE': 'WI',
    'NC_WAKE':      'NC',
}


def load_parcels_from_json(
    json_path: str,
    zip_code: str,
    market_key: str = 'WA_KING',
    default_state: str | None = None,
    default_city: str = 'Bellevue',
) -> list[dict]:
    """
    Read the JSON and transform into parcels_v3 row dicts.
    Returns a list ready for supabase.table('parcels_v3').upsert(...)

    default_state: if None, resolved from market_key via _MARKET_STATE
    (falls back to 'WA'). Prevents the cmd_seed-default-Bellevue bug
    shape recurring on the state column (85254 was seeded state='WA').
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"{json_path} not found")

    if not default_state:
        default_state = _MARKET_STATE.get((market_key or '').upper(), 'WA')

    with open(path) as f:
        data = json.load(f)

    rows = []
    for pin, p in data.items():
        owner_raw = (p.get('owner_name') or '').strip()
        addr = (p.get('address') or '').strip()

        row = {
            'pin':               str(pin),
            'zip_code':          zip_code,
            'market_key':        market_key,
            'address':           addr,
            'city':              default_city,
            'state':             default_state,

            'owner_name_raw':    owner_raw,
            'owner_name':        _normalize_display_name(owner_raw),
            'owner_type':        p.get('owner_type') or 'unknown',

            'total_value':       _to_int(p.get('value')),
            'last_transfer_date': p.get('last_transfer_date'),
            'last_transfer_price': _to_int(p.get('sale_price')),
            'tenure_years':      p.get('tenure_years'),
        }
        # Optional enrichment fields — present in AZ seeds (2026-06-10+),
        # absent in legacy KC/SNO seeds. Only set when present so older
        # seed files re-run cleanly without nulling reingested values.
        owner_state = (p.get('owner_state') or '').strip().upper()
        if owner_state:
            row['owner_state'] = owner_state
        owner_city = (p.get('owner_city') or '').strip()
        if owner_city:
            row['owner_city'] = owner_city
        if p.get('is_absentee') is not None:
            row['_seed_is_absentee'] = p.get('is_absentee')
            row['_seed_is_out_of_state'] = p.get('is_out_of_state')
        if p.get('lat') is not None and p.get('lng') is not None:
            try:
                row['lat'] = float(p['lat'])
                row['lng'] = float(p['lng'])
            except (TypeError, ValueError):
                pass
        row.update(_derive_flags(row))
        row.pop('_seed_is_absentee', None)
        row.pop('_seed_is_out_of_state', None)
        rows.append(row)

    return rows


def upsert_parcels(rows: list[dict]) -> dict:
    """Upsert into parcels_v3 in batches of 1000."""
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured")

    stats = {'inserted_or_updated': 0, 'failed': 0, 'batches': 0}
    for i in range(0, len(rows), 1000):
        batch = rows[i:i + 1000]
        try:
            supa.table('parcels_v3').upsert(batch, on_conflict='pin').execute()
            stats['inserted_or_updated'] += len(batch)
            stats['batches'] += 1
        except Exception as e:
            print(f"  [seed] batch {stats['batches']} failed: {e}")
            stats['failed'] += len(batch)
    return stats


def stamp_ingest_complete(zip_code: str, parcel_count: int) -> None:
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        return
    supa.table('zip_coverage_v3').update({
        'parcels_ingested_at': datetime.now(timezone.utc).isoformat(),
        'parcel_count':        parcel_count,
        'updated_at':          datetime.now(timezone.utc).isoformat(),
    }).eq('zip_code', zip_code).execute()
