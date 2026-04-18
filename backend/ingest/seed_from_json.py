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
    """Compute is_absentee, is_out_of_state from parcel data where possible."""
    # We don't have mailing address in this JSON shape, so these default False.
    # True ingest from ArcGIS sets them correctly; this is a bootstrap path.
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


def load_parcels_from_json(
    json_path: str,
    zip_code: str,
    market_key: str = 'WA_KING',
    default_state: str = 'WA',
    default_city: str = 'Bellevue',
) -> list[dict]:
    """
    Read the JSON and transform into parcels_v3 row dicts.
    Returns a list ready for supabase.table('parcels_v3').upsert(...)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"{json_path} not found")

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
        row.update(_derive_flags(row))
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
