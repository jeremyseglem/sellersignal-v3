"""
Briefings API — the main weekly-playbook + map-data payload.

  GET  /api/briefings/:zip              — full briefing (playbook + optional map)
  GET  /api/briefings/:zip/summary      — compact summary (counts + top 3)
  GET  /api/briefings/:zip/history      — past briefings for this ZIP

All endpoints gated by require_live_zip — ZIPs not in coverage return 404.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime, date, timedelta, timezone
from backend.api.db import get_supabase_client
from backend.api.zip_gate import require_live_zip
from backend.selection import weekly_selector as _ws

router = APIRouter()


# ============================================================================
# Helper: score a parcel for selection ranking
# ============================================================================
# The selection score combines investigation pressure (if present) with
# structural features. Parcels with pressure=3 always rank above pressure=2,
# which always ranks above unscored.
# ============================================================================

def _rank_parcel(parcel_row: dict, investigation_row: dict = None) -> float:
    """
    Compute a selection rank score.

    Higher = more likely to appear on playbook.
    """
    base = 50.0

    # Value tier bonus (log-dampened — a $30M parcel isn't 10x a $3M parcel)
    value = parcel_row.get('total_value') or 0
    if value > 0:
        import math
        base += min(20, math.log10(value / 1_000_000) * 8) if value >= 1_000_000 else 0

    # Band-based baseline
    band = parcel_row.get('band')
    if band == 3:     base += 30
    elif band == 2.5: base += 20
    elif band == 2:   base += 10

    # Investigation pressure is the dominant factor
    if investigation_row:
        pressure = investigation_row.get('action_pressure') or 0
        base += pressure * 15

    return base


# ============================================================================
# Main briefing endpoint
# ============================================================================

@router.get("/{zip_code}")
async def get_briefing(
    zip_code: str = Depends(require_live_zip),
    include_map: bool = Query(True, description="Include full-ZIP map data"),
    call_now_limit: int = Query(0, ge=0, le=500,
        description="Max CALL NOW leads; 0 = return every pressure-3 signal (default)"),
    build_now_limit: int = Query(0, ge=0, le=500,
        description="Max BUILD NOW leads; 0 = return all (default)"),
    hold_limit: int = Query(0, ge=0, le=500,
        description="Max STRATEGIC HOLD leads; 0 = return all (default)"),
    dedup: bool = Query(True,
        description="Dedup by owner surname (one lead per family)"),
):
    """
    Full briefing for a ZIP. Returns:
      - week_of: ISO date (Monday of current week)
      - playbook: { call_now, build_now, strategic_holds }
      - stats: counts, cost, last run info
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        # ── Load parcels ──
        # Supabase PostgREST enforces a server-side max-rows cap (typically
        # 1000) regardless of client .limit(). Paginate with .range() to
        # get past it.
        def _fetch_all(table, zip_col_val, page_size=1000):
            """Paginate a zip-scoped table until empty."""
            out = []
            offset = 0
            while True:
                res = (supa.table(table)
                       .select('*')
                       .eq('zip_code', zip_col_val)
                       .range(offset, offset + page_size - 1)
                       .execute())
                batch = res.data or []
                out.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
                if offset > 100000:  # hard safety stop
                    break
            return out

        parcels = _fetch_all('parcels_v3', zip_code)
        if not parcels:
            raise HTTPException(404, f"No parcels in ZIP {zip_code}")

        # ── Load investigations ──
        inv_rows = _fetch_all('investigations_v3', zip_code)
        inv_by_pin = {}
        for row in inv_rows:
            pin = row['pin']
            # Deep preferred over screen
            if pin not in inv_by_pin or row['mode'] == 'deep':
                inv_by_pin[pin] = row

        # ── Shape leads for the real weekly_selector ──
        # The selector expects dicts with: pin, band, signal_family,
        # sub_signal, address, owner, value, zip, rank_score (or
        # calibrated_rank_score), investigation (nested with mode,
        # has_blocker, has_life_event, has_financial, recommended_action{
        # category, tone, pressure, reason, next_step}).
        #
        # Supabase rows give us flat columns; we translate to nested.
        #
        # Archetype name mapping: why_not_selling.py (v3) uses archetype
        # names that differ from the sandbox COPY_TEMPLATES keys. Map them
        # so resolve_copy finds the right template and we get the
        # pressure-scored copy that matches the PRESSURE PDF.
        _ARCHETYPE_TO_SIGNAL_FAMILY = {
            # Trust patterns — aging maps 1:1; young/mature use trust_aging
            # copy for STRATEGIC HOLDS sections or fall through for CALL NOW.
            'trust_aging':              'trust_aging',
            'trust_mature':             'trust_aging',
            'trust_young':              'trust_aging',
            # LLC investor patterns
            'llc_investor_mature':      'investor_disposition',
            'llc_investor_early':       'investor_disposition',
            'llc_long_hold':            'investor_disposition',
            # Individual tenure → silent transition
            'individual_long_tenure':   'silent_transition',
            'individual_settled':       'silent_transition',
            'individual_recent':        'silent_transition',
            # Absentee
            'absentee_dormant':         'dormant_absentee',
            'absentee_active':          'dormant_absentee',
            # Estate markers in owner name → hard pressure
            'estate_heirs':             'family_event_cluster',
        }

        def _shape_lead(p, inv):
            raw_archetype = p.get('signal_family')
            sig_family = _ARCHETYPE_TO_SIGNAL_FAMILY.get(
                raw_archetype, raw_archetype)

            # Sub-signal inferred from investigation action_reason text
            sub_signal = None
            if inv and inv.get('action_reason'):
                reason = (inv.get('action_reason') or '').lower()
                if 'trustee sale' in reason:         sub_signal = 'trustee_sale'
                elif 'notice of default' in reason or 'nod' in reason: sub_signal = 'nod'
                elif 'overdue' in reason or 'hold-period' in reason:   sub_signal = 'overdue'
                elif 'expired' in reason:            sub_signal = 'caution'

            lead = {
                'pin':          p['pin'],
                'band':         float(p.get('band') or 0),
                'signal_family': sig_family,
                'archetype':    raw_archetype,
                'sub_signal':   sub_signal,
                'address':      p.get('address'),
                'owner':        p.get('owner_name'),
                'owner_type':   p.get('owner_type'),
                'is_absentee':  bool(p.get('is_absentee')),
                'value':        p.get('total_value') or 0,
                'zip':          p.get('zip_code'),
                'tenure_years': p.get('tenure_years'),
                'rank_score':   p.get('rank_score') or (p.get('total_value') or 0),
                'calibrated_rank_score': p.get('calibrated_rank_score'),
                'timeline_months': p.get('timeline_months'),
                'inevitability':   p.get('inevitability'),
            }
            if inv:
                rec = None
                if inv.get('action_category'):
                    rec = {
                        'category':  inv.get('action_category'),
                        'tone':      inv.get('action_tone'),
                        'pressure':  inv.get('action_pressure'),
                        'reason':    inv.get('action_reason'),
                        'next_step': inv.get('action_next_step'),
                    }
                lead['investigation'] = {
                    'mode':              inv.get('mode'),
                    'has_blocker':       inv.get('has_blocker', False),
                    'has_life_event':    inv.get('has_life_event', False),
                    'has_financial':     inv.get('has_financial', False),
                    'recommended_action': rec,
                }
            return lead

        leads = [_shape_lead(p, inv_by_pin.get(p['pin'])) for p in parcels]

        # ── Delegate to the real selector (same code that produced the
        #    sandbox PRESSURE PDF) ──
        # Semantics: limit=0 means "no cap, return every real signal".
        # Any positive integer caps at that number.
        exclude_pins = set()         # no recency exclusion for live API yet
        used_owner_keys = set()
        cn_n = None if call_now_limit == 0 else call_now_limit
        bn_n = None if build_now_limit == 0 else build_now_limit
        hd_n = None if hold_limit == 0 else hold_limit

        call_now_leads = _ws.select_call_now(leads, exclude_pins, used_owner_keys,
                                             n=cn_n)
        build_now_leads = _ws.select_build_now(leads, exclude_pins, used_owner_keys,
                                               n=bn_n if bn_n is not None else 1000)
        hold_leads     = _ws.select_strategic_holds(leads, exclude_pins, used_owner_keys,
                                                    n=hd_n if hd_n is not None else 1000)

        # ── Resolve pressure-scored copy for each pick ──
        for L in call_now_leads:  L['_section'] = 'CALL NOW'
        for L in build_now_leads: L['_section'] = 'BUILD NOW'
        for L in hold_leads:      L['_section'] = 'STRATEGIC HOLDS'
        for L in call_now_leads + build_now_leads + hold_leads:
            L['_copy'] = _ws.resolve_copy(L, section=L['_section'])

        def _shape_pick(L):
            rec = (L.get('investigation') or {}).get('recommended_action')
            return {
                'pin':           L['pin'],
                'address':       L.get('address'),
                'owner_name':    L.get('owner'),
                'owner_type':    L.get('owner_type'),
                'is_absentee':   L.get('is_absentee', False),
                'value':         L.get('value'),
                'band':          L.get('band'),
                'signal_family': L.get('signal_family'),
                'archetype':     L.get('archetype'),
                'tenure_years':  L.get('tenure_years'),
                'copy': {
                    'happening': L['_copy'].get('happening'),
                    'why':       L['_copy'].get('why'),
                    'action':    L['_copy'].get('action'),
                },
                'recommended_action': rec,
            }

        call_now_picks  = [_shape_pick(L) for L in call_now_leads]
        build_now_picks = [_shape_pick(L) for L in build_now_leads]
        hold_picks      = [_shape_pick(L) for L in hold_leads]

        # ── Compute week_of (Monday of current week) ──
        today = date.today()
        week_monday = today - timedelta(days=today.weekday())

        # ── Stats ──
        stats = {
            'total_parcels':       len(parcels),
            'investigated_count':  len(inv_by_pin),
            'call_now_count':      len(call_now_picks),
            'build_now_count':     len(build_now_picks),
            'strategic_holds_count': len(hold_picks),
        }

        return {
            'zip':       zip_code,
            'week_of':   week_monday.isoformat(),
            'playbook':  {
                'call_now':        call_now_picks,
                'build_now':       build_now_picks,
                'strategic_holds': hold_picks,
            },
            'stats':     stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error generating briefing: {e}")


def _format_pick(parcel: dict, investigation: dict = None) -> dict:
    """Shape a (parcel, investigation) pair for the playbook payload."""
    rec = investigation or {}
    return {
        'pin':           parcel['pin'],
        'address':       parcel.get('address'),
        'owner_name':    parcel.get('owner_name'),
        'value':         parcel.get('total_value'),
        'lat':           float(parcel['lat']) if parcel.get('lat') else None,
        'lng':           float(parcel['lng']) if parcel.get('lng') else None,
        'band':          parcel.get('band'),
        'signal_family': parcel.get('signal_family'),
        'tenure_years':  parcel.get('tenure_years'),
        'recommended_action': {
            'category':  rec.get('action_category'),
            'tone':      rec.get('action_tone'),
            'pressure':  rec.get('action_pressure'),
            'reason':    rec.get('action_reason'),
            'next_step': rec.get('action_next_step'),
        } if rec.get('action_category') else None,
    }


# ============================================================================
# Summary + history endpoints
# ============================================================================

@router.get("/{zip_code}/summary")
async def get_briefing_summary(zip_code: str = Depends(require_live_zip)):
    """Compact version — just counts and top 3 CALL NOW leads."""
    full = await get_briefing(zip_code, include_map=False)
    return {
        'zip':              zip_code,
        'week_of':          full['week_of'],
        'call_now_count':   full['stats']['call_now_count'],
        'build_now_count':  full['stats']['build_now_count'],
        'strategic_holds_count': full['stats']['strategic_holds_count'],
        'top_3':            full['playbook']['call_now'][:3],
    }


@router.get("/{zip_code}/history")
async def get_briefing_history(
    zip_code: str = Depends(require_live_zip),
    limit: int = Query(12, ge=1, le=52),
):
    """Past briefings for this ZIP (persisted snapshots in briefings_v3)."""
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        result = (supa.table('briefings_v3')
                  .select('id, week_of, total_parcels, investigated_count, cost_usd, published_at')
                  .eq('zip_code', zip_code)
                  .order('week_of', desc=True)
                  .limit(limit)
                  .execute())
        return {
            'zip':     zip_code,
            'history': result.data or [],
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching history: {e}")
