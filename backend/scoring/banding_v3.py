"""
Banding — assigns every parcel to a Band 0-4 based on structural features.

Band scale:
  0 — excluded from consideration entirely (commercial, government,
      REO, tax agent, recent buyer, institutional)
  1 — weak structural signal (likely not a current prospect, no
      specific concerning pattern)
  2 — monitoring pool (trust_aging, silent_transition baseline,
      individual_long_tenure — patterns that merit watching)
  2.5 — elevated monitoring (family clusters, dormant_absentee —
        patterns where transition likelihood is above baseline)
  3 — active prospect (financial_stress from court records,
      failed_sale_attempt with rationality filter, investor_disposition
      at exit window, death_inheritance from probate/obit)
  4 — post-transaction (sold in last 2 years — excluded from fresh runs,
      kept for historical lookback)

This is structural only — it looks at the parcel's static attributes
(owner_type, tenure, value) and its assigned archetype (from classify
stage). Investigation signals (NOD, probate, etc.) can promote a parcel
from Band 2 to Band 3 at runtime via the selection layer, but banding
itself does NOT read investigation data. That separation is intentional:
bands are stable structural labels; pressure-driven promotion is a
selection-time decision.

Archetypes map to bands per the matrix below. See why_not_selling.py
for archetype definitions.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional


# ============================================================================
# Archetype -> base band map
# ============================================================================

ARCHETYPE_TO_BAND = {
    'trust_young':              1,     # young trusts = low structural signal
    'trust_mature':             2,     # mid-cycle trusts merit watching
    'trust_aging':              2,     # aging trusts in monitoring pool
    'llc_investor_early':       1,     # early-cycle investors unlikely to move
    'llc_investor_mature':      2.5,   # exit-window LLCs = elevated monitoring
    'llc_long_hold':            1,     # past typical exit, now stable
    'individual_settled':       1,     # settled primary residence
    'individual_long_tenure':   2,     # 20+ year individual = life-event likely
    'individual_recent':        0,     # recent buyer hard exclusion
    'absentee_active':          1,     # second-home pattern, long horizon
    'absentee_dormant':         2.5,   # disengagement = elevated monitoring
    'estate_heirs':             3,     # estate markers = active prospect
    'unknown':                  1,
}


# ============================================================================
# Hard disqualifier regex banks
# ============================================================================

# Institutional / government / church / school
INSTITUTIONAL_RX = re.compile(
    r'\bUSA\b|\bCITY OF\b|\bTOWN OF\b|\bVILLAGE OF\b|\bBOROUGH OF\b|'
    r'\bCOUNTY OF\b|\bSTATE OF\b|\bUNITED STATES\b|\bFEDERAL\b|'
    r'\bMUNICIPAL\b|\bSCHOOL DIST|\bSCHOOL\b|\bACADEMY\b|\bSEMINARY\b|'
    r'\bFIRE DIST|\bWATER DIST|\bSEWER\b|\bHOUSING AUTH|\bCHURCH\b|'
    r'\bDIOCESE\b|\bMINISTR(Y|IES)\b|\bPARISH\b|\bMONASTER|\bCONVENT\b|'
    r'\bARCHDIOCESE\b|\bCONGREGATION\b|\bSYNAGOGUE\b|\bTEMPLE\b|\bMOSQUE\b|'
    r'\bHOA\b|\bHOMEOWNERS?\s*ASS|\bCONDO\s*(MASTER|ASSOC)|\bCONDOMINIUM\s*ASS|'
    r'\bOWNERS?\s*ASSOC|\bMASTER\s*ASSOC|\bCOMMUNITY\s*ASSOC|\bMUSEUM\b|'
    r'\bCEMETERY\b|\bLIBRARY\b|\bFOUNDATION\b|\bUNIVERSIT(Y|IES)\b|'
    r'\bCOLLEGE\b|\bHOSPITAL\b|\bHEALTHCARE\b|\bMEDICAL\s*CENTER\b|'
    r'\bYMCA\b|\bYWCA\b|\bROTARY\b|\bLIONS\s*CLUB|\bELKS\b|\bVFW\b|'
    r'\bAMERICAN\s*LEGION|\bSALVATION\s*ARMY|\bHABITAT\b',
    re.IGNORECASE,
)

# Property tax agent (not the actual owner)
TAX_AGENT_RX = re.compile(
    r'\b(K\.?E\.?\s*ANDREWS|MARVIN\s*F\s*POER|RYAN\s*LLC|'
    r'RYAN\s*PROPERTY\s*TAX|ALTUS\s*GROUP|DUFF\s*&?\s*PHELPS|'
    r'TRUE\s*PARTNERS|PARADIGM\s*TAX|PROPERTY\s*TAX\s*ADVISORS)\b',
    re.IGNORECASE,
)

# REO / bank-owned
REO_RX = re.compile(
    r'\b(FANNIE\s*MAE|FREDDIE\s*MAC|FEDERAL\s*NATIONAL\s*MORTGAGE|'
    r'FEDERAL\s*HOME\s*LOAN\s*MORTGAGE|GINNIE\s*MAE|HUD\b|'
    r'SECRETARY\s*OF\s*HOUSING|SECRETARY\s*OF\s*VETERANS|'
    r'BANK\s*OF\s*AMERICA|WELLS\s*FARGO|JPMORGAN|JP\s*MORGAN|'
    r'CHASE\s*BANK|CITIBANK|MTGLQ\s*INVESTORS|NATIONSTAR|'
    r'MR\.?\s*COOPER|OCWEN|SHELLPOINT|CARRINGTON\s*MORTGAGE)\b',
    re.IGNORECASE,
)

# Real estate / brokerage entities
BROKERAGE_RX = re.compile(
    r'\bREAL ESTATE\b|\bREALTY\b|\bBROKERAGE\b|\bMORTGAGE\b|\bLENDING\b',
    re.IGNORECASE,
)


# ============================================================================
# Banding function
# ============================================================================

def determine_band(parcel: dict) -> float:
    """
    Assign a band to a parcel.

    Priority (first match wins):
      1. Hard disqualifiers → Band 0
      2. Oversized value (> $25M residential) → Band 0 (likely commercial)
      3. Recent buyer (< 2 yr tenure) → Band 0
      4. Archetype-to-band map
      5. Default → Band 1

    Args:
        parcel: dict with pin, owner_name, signal_family (archetype),
                total_value, tenure_years, prop_type, is_vacant_land

    Returns:
        float: 0 | 1 | 2 | 2.5 | 3 | 4
    """
    owner_name = (parcel.get('owner_name_raw') or parcel.get('owner_name') or '').upper()

    # ── Hard disqualifiers ──
    if INSTITUTIONAL_RX.search(owner_name):
        return 0
    if TAX_AGENT_RX.search(owner_name):
        return 0
    if REO_RX.search(owner_name):
        return 0
    if BROKERAGE_RX.search(owner_name):
        return 0

    # Oversized residential value → likely commercial/institutional
    value = parcel.get('total_value') or 0
    if value > 25_000_000:
        return 0

    # Commercial property type
    prop_type = (parcel.get('prop_type') or '').strip().lower()
    if 'commercial' in prop_type or 'industrial' in prop_type:
        return 0

    # Recent buyer hard cap
    tenure = parcel.get('tenure_years')
    if tenure is not None and tenure < 2:
        return 0

    # No owner name or no address → can't act on
    if not owner_name or len(owner_name) < 3:
        return 1
    if not parcel.get('address'):
        return 1

    # ── Archetype routing ──
    # parcels_v3.signal_family holds the archetype (written by classify stage)
    archetype = parcel.get('signal_family')
    if archetype in ARCHETYPE_TO_BAND:
        return ARCHETYPE_TO_BAND[archetype]

    return 1


# ============================================================================
# Batch apply
# ============================================================================

def apply_banding_to_zip(zip_code: str) -> dict:
    """
    Read all parcels in a ZIP, compute Band for each, update back.
    Returns stats.
    """
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured")

    # Paginated read — Supabase caps at 1000 per request
    parcels = []
    offset = 0
    page_size = 1000
    while True:
        page = (supa.table('parcels_v3')
                .select('pin, owner_name, owner_name_raw, total_value, '
                        'tenure_years, prop_type, signal_family, address, '
                        'is_vacant_land')
                .eq('zip_code', zip_code)
                .range(offset, offset + page_size - 1)
                .execute())
        rows = page.data or []
        parcels.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    if not parcels:
        return {'total': 0, 'by_band': {}}

    from collections import Counter, defaultdict
    band_counts = Counter()
    by_band = defaultdict(list)
    for p in parcels:
        band = determine_band(p)
        band_counts[band] += 1
        by_band[band].append(p['pin'])

    # Bulk update by band — one UPDATE per band group
    for band, pins in by_band.items():
        for i in range(0, len(pins), 200):
            chunk = pins[i:i + 200]
            (supa.table('parcels_v3')
             .update({'band': band})
             .in_('pin', chunk)
             .execute())

    # Stamp completion
    supa.table('zip_coverage_v3').update({
        'bands_assigned_at': datetime.now(timezone.utc).isoformat(),
        'updated_at':        datetime.now(timezone.utc).isoformat(),
    }).eq('zip_code', zip_code).execute()

    return {
        'total':   len(parcels),
        'by_band': dict(sorted(band_counts.items())),
    }
