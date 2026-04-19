"""
Legal Filings Ingest — v3

Takes a CSV export from KC Superior Court Family Law (dissolutions) or
KC Recorder LandmarkWeb (NOD/Trustee Sale/Lis Pendens), parses it with
the existing legal_filings.py loader + matcher functions, and writes:

  1. Filing records to legal_filings_v3 (dedup'd on case/recording number)
  2. Filing-to-parcel matches to legal_filing_matches_v3
  3. Optionally updates parcels_v3.signal_family for matched parcels
     ('financial_stress' for NOD/trustee sale/lis pendens,
      'divorce_unwinding' for dissolution filings)

Usage from CLI:
    python -m backend.ingest.legal_filings_ingest \\
        --csv /path/to/recorder.csv \\
        --kind recorder \\
        --zip 98004

    python -m backend.ingest.legal_filings_ingest \\
        --csv /path/to/divorce.csv \\
        --kind divorce \\
        --zip 98004

Legal:
  - Only consumes human-exported CSVs. Does not scrape KC LandmarkWeb.
  - ToS of LandmarkWeb permits targeted manual search; prohibits
    automated mass-download. This module respects that boundary.

Match strength semantics:
  - 'direct_pin'  (recorder docs with explicit parcel number) -> STRONG
  - 'name_both'   (divorce with both petitioner+respondent on title) -> STRONG
  - 'name_one'    (divorce with one party on title) -> WEAK — needs corroboration

Only STRONG matches result in signal_family promotion. WEAK matches are
recorded for review but don't auto-promote a parcel to pressure-3.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Reuse the sandbox-proven loader/matcher functions
from backend.pipeline.legal_filings import (
    load_divorce_filings_csv,
    load_recorder_documents_csv,
    match_divorce_to_parcels,
    match_recorder_to_parcels,
    DivorceFiling,
    RecorderDocument,
)
from backend.api.db import get_supabase_client


# ─── Helpers ─────────────────────────────────────────────────────────────

def _fetch_parcels_for_zip(supa, zip_code: str) -> list[dict]:
    """Pull all parcels in a ZIP, paginated past Supabase's 1000-row default."""
    out = []
    offset = 0
    page = 1000
    while True:
        res = (supa.table('parcels_v3')
               .select('pin, owner_name, prop_type')
               .eq('zip_code', zip_code)
               .range(offset, offset + page - 1)
               .execute())
        batch = res.data or []
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if offset > 200000:
            break
    return out


def _build_owners_db(parcels: list[dict]) -> tuple[dict, dict]:
    """
    Reshape parcels list into the format match_* expects:
      owners_db[pin] = {"owner_name": ...}
      use_codes[pin] = {"prop_type": ...}
    """
    owners_db = {p['pin']: {'owner_name': p.get('owner_name') or ''}
                 for p in parcels}
    use_codes = {p['pin']: {'prop_type': (p.get('prop_type') or 'R').upper()[:1] or 'R'}
                 for p in parcels}
    return owners_db, use_codes


def _derive_subtype(filing_kind: str, case_type_or_doc_type: str) -> str:
    """Canonical subtype label."""
    s = (case_type_or_doc_type or '').upper()
    if filing_kind == 'divorce':
        if 'DISSOLUTION WITH CHILDREN' in s or 'CHILDREN' in s:
            return 'dissolution_with_children'
        if 'DISSOL' in s:
            return 'dissolution_no_children'
        return 'family_law_other'
    # recorder
    if 'TRUSTEE SALE' in s:
        return 'trustee_sale'
    if 'DEFAULT' in s or 'NOD' in s:
        return 'notice_of_default'
    if 'LIS PENDENS' in s:
        return 'lis_pendens'
    return 'recorder_other'


# ─── Writers ─────────────────────────────────────────────────────────────

def _upsert_divorce_filing(supa, f: DivorceFiling, source_csv: str,
                           uploaded_by: str) -> Optional[str]:
    """Insert (or skip-if-exists) a divorce filing. Returns the row id."""
    subtype = _derive_subtype('divorce', f.case_type)
    row = {
        'filing_kind':        'divorce',
        'filing_subtype':     subtype,
        'filing_date':        f.filing_date.date().isoformat(),
        'case_or_rec_number': f.case_number,
        'petitioner_name':    f.petitioner_name,
        'respondent_name':    f.respondent_name,
        'source_csv_name':    source_csv,
        'uploaded_by':        uploaded_by,
        'raw_row': {
            'case_type':       f.case_type,
            'petitioner':      f.petitioner_name,
            'respondent':      f.respondent_name,
            'filing_date':     f.filing_date.isoformat(),
        },
    }
    return _upsert_filing_row(supa, row)


def _upsert_recorder_filing(supa, d: RecorderDocument, source_csv: str,
                            uploaded_by: str) -> Optional[str]:
    subtype = _derive_subtype('recorder', d.document_type)
    row = {
        'filing_kind':        'recorder',
        'filing_subtype':     subtype,
        'filing_date':        d.recording_date.date().isoformat(),
        'case_or_rec_number': d.recording_number,
        'grantor_names':      d.grantor_names,
        'grantee_names':      d.grantee_names,
        'parcel_id_on_filing': d.parcel_id,
        'source_csv_name':    source_csv,
        'uploaded_by':        uploaded_by,
        'raw_row': {
            'document_type':  d.document_type,
            'grantor':        d.grantor_names,
            'grantee':        d.grantee_names,
            'recording_date': d.recording_date.isoformat(),
            'parcel_id':      d.parcel_id,
        },
    }
    return _upsert_filing_row(supa, row)


def _upsert_filing_row(supa, row: dict) -> Optional[str]:
    """
    Insert a filing row. The unique index on (filing_kind, case_or_rec_number)
    means re-uploads don't duplicate. On conflict, we fetch the existing id.
    """
    try:
        res = (supa.table('legal_filings_v3')
               .upsert(row, on_conflict='filing_kind,case_or_rec_number',
                       returning='representation')
               .execute())
        if res.data:
            return res.data[0].get('id')
    except Exception as e:
        print(f"  [upsert-filing] error: {e}")
        # Fall through to fetch path
    # Fetch the existing row's id
    try:
        res = (supa.table('legal_filings_v3')
               .select('id')
               .eq('filing_kind', row['filing_kind'])
               .eq('case_or_rec_number', row['case_or_rec_number'])
               .maybe_single()
               .execute())
        return (res.data or {}).get('id') if res else None
    except Exception:
        return None


def _write_matches(supa, filing_id: str, zip_code: str, candidates: list[dict]):
    """
    candidates: list of dicts from match_*_to_parcels, shape:
      {'parcel_id': pin, 'signal_family': 'financial_stress'|'divorce_unwinding',
       'trigger_hint': {...}}
    """
    # Idempotent: drop prior matches for this filing, re-insert
    (supa.table('legal_filing_matches_v3')
         .delete()
         .eq('filing_id', filing_id)
         .execute())

    rows = []
    for c in candidates:
        hint = c.get('trigger_hint', {})
        match_strength = hint.get('match_strength', 'strong')  # recorder default strong
        # Derive match_path
        if 'parcel_id' in c and c.get('parcel_id'):
            # Direct-pin for recorder, otherwise name-match for divorce
            if c['signal_family'] == 'financial_stress':
                match_path = 'direct_pin' if match_strength == 'strong' else 'name_one'
            else:
                match_path = 'name_both' if match_strength == 'strong' else 'name_one'
        else:
            match_path = 'name_one'

        rows.append({
            'filing_id':            filing_id,
            'pin':                  c['parcel_id'],
            'zip_code':             zip_code,
            'match_path':           match_path,
            'match_strength':       match_strength,
            'derived_signal_family': c['signal_family'],
            'urgency_tier':         hint.get('urgency_tier'),
            'applied_to_parcel':    False,
        })
    if rows:
        supa.table('legal_filing_matches_v3').insert(rows).execute()
    return len(rows)


def _apply_signals_to_parcels(supa, zip_code: str) -> dict:
    """
    For every STRONG unapplied match in this ZIP, update parcels_v3.signal_family.
    Marks matches as applied_to_parcel=TRUE.

    Only STRONG matches promote. WEAK matches are left in the matches table
    for review.
    """
    # Fetch unapplied strong matches in this ZIP
    res = (supa.table('legal_filing_matches_v3')
           .select('id, pin, derived_signal_family')
           .eq('zip_code', zip_code)
           .eq('match_strength', 'strong')
           .eq('applied_to_parcel', False)
           .execute())
    matches = res.data or []
    if not matches:
        return {'promoted': 0, 'affected_pins': []}

    # Dedup: if the same pin is hit by multiple filings, one update is enough
    by_pin = {}
    for m in matches:
        by_pin[m['pin']] = m['derived_signal_family']

    promoted = 0
    for pin, family in by_pin.items():
        try:
            (supa.table('parcels_v3')
             .update({'signal_family': family})
             .eq('pin', pin)
             .execute())
            promoted += 1
        except Exception as e:
            print(f"  [apply] failed to update {pin}: {e}")

    # Mark matches as applied
    match_ids = [m['id'] for m in matches]
    if match_ids:
        (supa.table('legal_filing_matches_v3')
         .update({'applied_to_parcel': True})
         .in_('id', match_ids)
         .execute())

    return {'promoted': promoted, 'affected_pins': list(by_pin.keys())}


# ─── Main ingest flows ───────────────────────────────────────────────────

def ingest_csv(csv_path: str, filing_kind: str, zip_code: str,
               uploaded_by: str = 'cli', apply_signals: bool = True) -> dict:
    """
    Top-level ingest.

    Returns:
      {
        'filings_parsed':     int,
        'filings_stored':     int,
        'matches_written':    int,
        'signals_promoted':   int,        (when apply_signals=True)
        'affected_pins':      [pin,...],
      }
    """
    if filing_kind not in ('divorce', 'recorder'):
        raise ValueError(f"filing_kind must be 'divorce' or 'recorder', got {filing_kind}")

    csv_path = str(Path(csv_path).expanduser().resolve())
    if not Path(csv_path).exists():
        raise FileNotFoundError(csv_path)

    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured (SUPABASE_URL + SUPABASE_SERVICE_KEY)")

    # 1. Load parcels for the ZIP
    parcels = _fetch_parcels_for_zip(supa, zip_code)
    print(f"[ingest] {len(parcels)} parcels in ZIP {zip_code}")
    if not parcels:
        return {'filings_parsed': 0, 'filings_stored': 0, 'matches_written': 0,
                'signals_promoted': 0, 'affected_pins': [],
                'error': f'No parcels in Supabase for ZIP {zip_code}'}

    owners_db, use_codes = _build_owners_db(parcels)

    # 2. Parse CSV
    source_name = Path(csv_path).name
    filings_parsed = 0
    filings_stored = 0
    matches_written = 0

    if filing_kind == 'divorce':
        divorces = load_divorce_filings_csv(csv_path)
        filings_parsed = len(divorces)
        print(f"[ingest] parsed {filings_parsed} divorce filings from CSV")

        # Filter to dissolutions only
        divorces = [f for f in divorces if f.is_dissolution]
        print(f"[ingest]   {len(divorces)} are dissolutions")

        for f in divorces:
            filing_id = _upsert_divorce_filing(supa, f, source_name, uploaded_by)
            if not filing_id:
                continue
            filings_stored += 1
            candidates = match_divorce_to_parcels([f], owners_db, use_codes,
                                                   zip_filter=zip_code)
            matches_written += _write_matches(supa, filing_id, zip_code, candidates)

    else:  # recorder
        docs = load_recorder_documents_csv(csv_path)
        filings_parsed = len(docs)
        print(f"[ingest] parsed {filings_parsed} recorder docs from CSV")

        for d in docs:
            filing_id = _upsert_recorder_filing(supa, d, source_name, uploaded_by)
            if not filing_id:
                continue
            filings_stored += 1
            candidates = match_recorder_to_parcels([d], owners_db, use_codes)
            matches_written += _write_matches(supa, filing_id, zip_code, candidates)

    print(f"[ingest] stored {filings_stored} filings, wrote {matches_written} matches")

    result = {
        'filings_parsed':   filings_parsed,
        'filings_stored':   filings_stored,
        'matches_written':  matches_written,
        'signals_promoted': 0,
        'affected_pins':    [],
    }

    # 3. Apply signal_family updates to matched parcels
    if apply_signals:
        apply_result = _apply_signals_to_parcels(supa, zip_code)
        result['signals_promoted'] = apply_result['promoted']
        result['affected_pins']    = apply_result['affected_pins']
        print(f"[ingest] promoted signal_family on {apply_result['promoted']} parcels")
        if apply_result['affected_pins']:
            print(f"[ingest]   affected pins: {apply_result['affected_pins'][:10]}"
                  f"{'...' if len(apply_result['affected_pins']) > 10 else ''}")

    return result


# ─── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest a legal-filings CSV into v3 Supabase."
    )
    parser.add_argument('--csv', required=True, help="path to CSV export")
    parser.add_argument('--kind', required=True, choices=['divorce', 'recorder'])
    parser.add_argument('--zip', required=True, help="ZIP code to match against")
    parser.add_argument('--uploaded-by', default='cli',
                        help="identifier for provenance (default: 'cli')")
    parser.add_argument('--no-apply', action='store_true',
                        help="parse and match only; don't update parcels_v3.signal_family")
    args = parser.parse_args()

    try:
        result = ingest_csv(
            csv_path=args.csv,
            filing_kind=args.kind,
            zip_code=args.zip,
            uploaded_by=args.uploaded_by,
            apply_signals=not args.no_apply,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n═══ Ingest Summary ═══")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
