"""
Raw signal matcher.

Reads unmatched rows from raw_signals_v3, resolves party_names against
owner_canonical_v3, writes matches to raw_signal_matches_v3, and
promotes high-confidence matches into the existing investigations_v3
flow so the scoring engine processes them naturally.

This is the FINAL stage of the harvester pipeline:
    harvester -> raw_signals_v3 -> [matcher] -> investigations_v3 -> scoring

Design:
- Loops raw_signals with matched_at IS NULL
- For each signal, dispatches to a type-specific matcher based on signal_type
- Reuses the existing ingest/legal_filings.py matchers where possible
  so the scoring logic doesn't diverge between SerpAPI-era code and
  harvester-era code
- Writes raw_signal_matches_v3 rows for each match
- Updates raw_signals_v3 matched_at + match_count
- Inserts into investigations_v3 for matched parcels so the scoring
  engine picks them up
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from backend.ingest.legal_filings import (
    DivorceFiling,
    RecorderDocument,
    match_divorce_to_parcels,
    match_recorder_to_parcels,
)

log = logging.getLogger(__name__)


# ─── Top-level entry point ─────────────────────────────────────────────

def process_unmatched(
    supa,
    zip_filter: Optional[str] = None,
    batch_size: int = 100,
    max_batches: int = 50,
) -> dict:
    """
    Process up to (batch_size * max_batches) unmatched raw_signals.

    zip_filter: if set (e.g. '98004'), only write matches for parcels in
                that ZIP. Harvester runs KC-wide but the pilot scopes
                to 98004.

    Returns summary stats.
    """
    stats = {
        "processed":    0,
        "matched":      0,
        "signals_none": 0,
        "by_type":      {},
        "errors":       [],
    }

    # Pre-load owners_db for the zip filter (or the whole KC coverage)
    owners_db, use_codes = _load_owners_db(supa, zip_filter)
    if not owners_db:
        log.warning("No owners loaded — check canonicalization status")
        stats["errors"].append("No owners in owners_db")
        return stats

    log.info(f"Loaded {len(owners_db)} canonicalized owners for matching")

    batch_n = 0
    while batch_n < max_batches:
        rows = _fetch_unmatched_batch(supa, batch_size)
        if not rows:
            log.info("No more unmatched raw_signals")
            break

        for row in rows:
            try:
                n_matched = _process_one(
                    supa, row, owners_db, use_codes, zip_filter
                )
                stats["processed"] += 1
                if n_matched > 0:
                    stats["matched"] += 1
                    stats["by_type"][row["signal_type"]] = (
                        stats["by_type"].get(row["signal_type"], 0) + 1
                    )
                else:
                    stats["signals_none"] += 1
            except Exception as e:
                log.exception(f"Match failed for raw_signal {row['id']}")
                stats["errors"].append({
                    "raw_signal_id": row["id"],
                    "error":         str(e),
                })

        batch_n += 1

    return stats


# ─── Internals ─────────────────────────────────────────────────────────

def _load_owners_db(supa, zip_filter: Optional[str]) -> tuple[dict, dict]:
    """
    Load canonicalized owners into the shape the legacy matchers expect.

    Returns (owners_db, use_codes) where:
      owners_db[pin] = {owner_name, co_owner_name, canonicalized, ...}
      use_codes[pin] = {prop_type: 'R'|'C'|..., ...}

    For the pilot we scope to a single ZIP. Full matcher runs would load
    all covered ZIPs, or process per-ZIP in a loop.
    """
    # Parcels (filtered to ZIP if provided) — we need prop_type/use_code
    # for the divorce matcher's residential filter
    PAGE = 1000
    offset = 0
    parcels: list[dict] = []
    while True:
        q = supa.table('parcels_v3').select(
            'pin, owner_name, prop_type, zip_code'
        )
        if zip_filter:
            q = q.eq('zip_code', zip_filter)
        batch = q.range(offset, offset + PAGE - 1).execute().data or []
        parcels.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 200000:
            break

    # owner_canonical (for each pin, the parsed owner entities)
    pins = [p['pin'] for p in parcels]
    canonical_by_pin = _load_canonical_for_pins(supa, pins)

    owners_db: dict = {}
    use_codes: dict = {}
    for p in parcels:
        pin = p['pin']
        owners_db[pin] = {
            'owner_name':     (p.get('owner_name') or '').upper(),
            'co_owner_name':  '',  # parcels_v3 doesn't split co-owner separately
            'canonicalized':  canonical_by_pin.get(pin),
        }
        use_codes[pin] = {
            'prop_type': p.get('prop_type') or 'R',  # default to residential
        }

    return owners_db, use_codes


def _load_canonical_for_pins(supa, pins: list[str]) -> dict:
    """
    Batch-fetch owner_canonical_v3 rows for a set of pins.
    Returns {pin: canonical_row}.
    """
    out: dict = {}
    CHUNK = 500
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i : i + CHUNK]
        rows = (supa.table('owner_canonical_v3')
                .select('*')
                .in_('pin', chunk)
                .execute().data) or []
        for r in rows:
            out[r['pin']] = r
    return out


def _fetch_unmatched_batch(supa, batch_size: int) -> list[dict]:
    """Pull next batch of raw_signals with matched_at IS NULL."""
    rows = (supa.table('raw_signals_v3')
            .select('*')
            .is_('matched_at', 'null')
            .order('harvested_at', desc=False)
            .limit(batch_size)
            .execute()).data or []
    return rows


def _process_one(
    supa,
    row: dict,
    owners_db: dict,
    use_codes: dict,
    zip_filter: Optional[str],
) -> int:
    """
    Match a single raw_signal to parcels. Write match rows.
    Returns number of parcels matched.
    """
    signal_type = row["signal_type"]
    dispatcher = _DISPATCH.get(signal_type)
    if not dispatcher:
        # Unknown signal type — mark processed, no match
        _mark_matched(supa, row["id"], match_count=0)
        return 0

    candidates = dispatcher(row, owners_db, use_codes)
    # Filter to zip if provided (paranoia — owners_db was already zip-filtered)
    if zip_filter:
        candidates = [c for c in candidates if c.get("parcel_id") in owners_db]

    if not candidates:
        _mark_matched(supa, row["id"], match_count=0)
        return 0

    # Write raw_signal_matches_v3 rows
    match_rows = [
        {
            "raw_signal_id":  row["id"],
            "pin":            c["parcel_id"],
            "match_strength": c.get("trigger_hint", {}).get("match_strength", "strict"),
            "match_method":   f"legacy::{signal_type}",
        }
        for c in candidates
    ]
    (supa.table('raw_signal_matches_v3')
     .upsert(match_rows, on_conflict='raw_signal_id,pin')
     .execute())

    # Mark raw_signal processed
    _mark_matched(supa, row["id"], match_count=len(match_rows))

    # Promote to investigations_v3 — one row per matched parcel
    _promote_to_investigations(supa, row, candidates)

    return len(match_rows)


def _mark_matched(supa, raw_signal_id: int, match_count: int):
    (supa.table('raw_signals_v3')
     .update({
         'matched_at':  datetime.utcnow().isoformat(),
         'match_count': match_count,
     })
     .eq('id', raw_signal_id)
     .execute())


def _promote_to_investigations(supa, row: dict, candidates: list[dict]):
    """
    Insert one investigations_v3 row per matched parcel so the scoring
    engine picks it up.

    Important: we're writing minimal rows that the existing scoring code
    already understands (signal_family, trigger_hint_json, etc.). The
    scoring rescore will fill in everything else.
    """
    for c in candidates:
        pin = c["parcel_id"]
        signal_family = c.get("signal_family") or _infer_signal_family(row["signal_type"])
        trigger_hint = c.get("trigger_hint") or {}

        # Build a minimal signal row matching investigations_v3 shape.
        # The scoring engine keys on signals[].type and signal_family.
        signal_obj = {
            "type":         row["signal_type"],
            "category":     _category_for(row["signal_type"]),
            "trust":        row["trust_level"],
            "source_type":  row["source_type"],        # NEW: lets scoring distinguish
                                                       # court_record from web_match
            "detail":       trigger_hint,
            "event_date":   row.get("event_date"),
            "document_ref": row.get("document_ref"),
        }

        # Upsert into investigations_v3 (mode='harvester' is a new mode alongside
        # screen/deep — signals from harvesters bypass SerpAPI entirely)
        (supa.table('investigations_v3')
         .upsert({
             "pin":              pin,
             "mode":             "harvester",
             "zip_code":         _get_zip_for_pin(supa, pin),
             "signals":          [signal_obj],
             "signal_family":    signal_family,
             "harvested_ref":    row["document_ref"],
         }, on_conflict='pin,mode')
         .execute())


def _infer_signal_family(signal_type: str) -> str:
    """Map harvester signal_type -> scoring's signal_family taxonomy."""
    return {
        "probate":      "probate_pending",
        "divorce":      "divorce_unwinding",
        "nod":          "foreclosure_pressure",
        "trustee_sale": "foreclosure_pressure",
        "lis_pendens":  "foreclosure_pressure",
        "obituary":     "life_event_recent",
    }.get(signal_type, "other")


def _category_for(signal_type: str) -> str:
    return {
        "probate":      "life_event",
        "divorce":      "life_event",
        "nod":          "financial_pressure",
        "trustee_sale": "financial_pressure",
        "lis_pendens":  "financial_pressure",
        "obituary":     "life_event",
    }.get(signal_type, "other")


_zip_cache: dict = {}

def _get_zip_for_pin(supa, pin: str) -> Optional[str]:
    if pin in _zip_cache:
        return _zip_cache[pin]
    r = (supa.table('parcels_v3')
         .select('zip_code')
         .eq('pin', pin)
         .limit(1)
         .execute()).data
    z = r[0]['zip_code'] if r else None
    _zip_cache[pin] = z
    return z


# ─── Dispatch table ────────────────────────────────────────────────────

def _dispatch_divorce(row, owners_db, use_codes):
    """Adapt a divorce RawSignal to DivorceFiling for the legacy matcher."""
    parties = row.get('party_names') or []
    if len(parties) < 2:
        return []

    # Build DivorceFiling expected by legacy matcher
    event_date = row.get('event_date')
    if isinstance(event_date, str):
        event_date = datetime.fromisoformat(event_date).date()
    filing = DivorceFiling(
        case_number=row.get('document_ref') or "",
        filing_date=datetime.combine(event_date, datetime.min.time())
                    if event_date else datetime.utcnow(),
        case_type="Dissolution",   # we assume dissolution; harvester pre-filtered
        petitioner_name=parties[0].get('raw', ''),
        respondent_name=parties[1].get('raw', ''),
    )
    return match_divorce_to_parcels([filing], owners_db, use_codes)


def _dispatch_probate(row, owners_db, use_codes):
    """
    Probate matching: single-party (decedent) vs all parcel owners.
    Reuses name_match from legacy code.
    """
    from backend.ingest.legal_filings import name_match

    parties = row.get('party_names') or []
    if not parties:
        return []

    decedent_raw = parties[0].get('raw', '')
    if not decedent_raw:
        return []

    candidates = []
    for pin, info in owners_db.items():
        if use_codes.get(pin, {}).get('prop_type', '') != 'R':
            continue
        owner_name = info.get('owner_name', '')
        if not owner_name:
            continue

        if name_match(decedent_raw, owner_name):
            candidates.append({
                "parcel_id":     pin,
                "signal_family": "probate_pending",
                "trigger_hint": {
                    "case_number":    row.get('document_ref'),
                    "filing_date":    (row.get('event_date') or ''),
                    "decedent":       decedent_raw,
                    "match_strength": "strict",
                },
            })

    return candidates


_DISPATCH = {
    "divorce":      _dispatch_divorce,
    "probate":      _dispatch_probate,
    # Future: nod, lis_pendens, trustee_sale (via match_recorder_to_parcels),
    # obituary (direct name match with stricter threshold), llc_officer_change
}
