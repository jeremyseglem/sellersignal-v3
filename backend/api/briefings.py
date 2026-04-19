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
    call_now_limit: int = Query(5, ge=1, le=50,
        description="Max CALL NOW leads to return (default 5)"),
    build_now_limit: int = Query(3, ge=0, le=50,
        description="Max BUILD NOW leads to return (default 3)"),
    hold_limit: int = Query(2, ge=0, le=50,
        description="Max STRATEGIC HOLD leads to return (default 2)"),
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

        # ── Load investigations (one query for all pins in this zip) ──
        inv_rows = _fetch_all('investigations_v3', zip_code)
        inv_by_pin = {}
        for row in inv_rows:
            pin = row['pin']
            # Deep preferred over screen
            if pin not in inv_by_pin or row['mode'] == 'deep':
                inv_by_pin[pin] = row

        # ── Filter blockers ──
        filtered = []
        for p in parcels:
            inv = inv_by_pin.get(p['pin'])
            if inv and inv.get('has_blocker'):
                continue
            filtered.append((p, inv))

        # ── Build selection pools ──
        # CALL NOW pool: Band 3 + investigation-promoted Band 2 (pressure=3)
        # BUILD NOW pool: Band 2 with pressure=2
        # STRATEGIC HOLDS: Band 2+ trust_aging without other actionable signals
        call_now_pool   = []
        build_now_pool  = []
        hold_pool       = []

        for p, inv in filtered:
            band = p.get('band')
            action_cat = (inv or {}).get('action_category')

            if band == 3 or action_cat == 'call_now':
                if action_cat == 'call_now' or action_cat is None:
                    call_now_pool.append((p, inv))
            elif band in (2, 2.5) and action_cat == 'build_now':
                build_now_pool.append((p, inv))
            elif band in (2, 2.5) and p.get('signal_family') == 'trust_aging':
                hold_pool.append((p, inv))

        # ── Select with slot reservations ──
        # Slots 1-2: Band 3 financial_stress (trustee sale / NOD)
        call_now_picks = []
        used_pins = set()
        used_owner_keys = set()

        # Entity suffixes to strip before finding the "family name" token.
        _ENTITY_SUFFIXES = {
            'TRUST', 'TRUSTEE', 'TRUSTEES', 'LIVING', 'REVOCABLE',
            'IRREVOCABLE', 'FAMILY', 'LLC', 'LLP', 'INC', 'CORP', 'CO',
            'COMPANY', 'LP', 'LTD', 'PARTNERSHIP', 'PARTNERS', 'ESTATE',
            'HEIRS', 'SURVIVOR', 'DECEASED', 'ET', 'AL', 'AND', '&',
        }

        def _owner_key(p):
            """
            Dedup key. Used to prevent showing multiple parcels with the
            same underlying owner family. Uses the last non-suffix token
            (usually the surname), not the first token — so 'John Frank',
            'John Galando', 'John Visich' are three different leads, but
            'Henderson Family Trust' and 'Henderson Estate' share a key.
            """
            name = (p.get('owner_name') or '').upper().strip()
            if not name:
                return ''
            # Strip punctuation that split surnames weirdly
            tokens = name.replace('/', ' ').replace(',', ' ').split()
            # Walk tokens right-to-left; first non-entity-suffix token wins
            for tok in reversed(tokens):
                clean = tok.strip('.')
                if clean and clean not in _ENTITY_SUFFIXES and not clean.isdigit():
                    return clean
            return tokens[-1] if tokens else ''

        def _push(pool, picks_list, target_count):
            for p, inv in pool:
                if len(picks_list) >= target_count: break
                if p['pin'] in used_pins: continue
                if dedup:
                    ok = _owner_key(p)
                    if ok and ok in used_owner_keys: continue
                picks_list.append(_format_pick(p, inv))
                used_pins.add(p['pin'])
                if dedup:
                    ok = _owner_key(p)
                    if ok: used_owner_keys.add(ok)

        # Reserve slots 1-2 for financial_stress
        fin_stress_picks = sorted(
            [(p, inv) for p, inv in call_now_pool
             if p.get('signal_family') == 'financial_stress'],
            key=lambda t: -_rank_parcel(t[0], t[1]),
        )
        _push(fin_stress_picks, call_now_picks, min(2, call_now_limit))

        # Fill remaining CALL NOW slots
        remaining_call_now = sorted(
            [(p, inv) for p, inv in call_now_pool if p['pin'] not in used_pins],
            key=lambda t: -_rank_parcel(t[0], t[1]),
        )
        _push(remaining_call_now, call_now_picks, call_now_limit)

        # BUILD NOW
        build_now_sorted = sorted(build_now_pool,
                                  key=lambda t: -_rank_parcel(t[0], t[1]))
        build_now_picks = []
        _push(build_now_sorted, build_now_picks, build_now_limit)

        # STRATEGIC HOLDS
        holds_sorted = sorted(hold_pool,
                              key=lambda t: -_rank_parcel(t[0], t[1]))
        hold_picks = []
        _push(holds_sorted, hold_picks, hold_limit)

        # ── Compute week_of (Monday of current week) ──
        today = date.today()
        week_monday = today - timedelta(days=today.weekday())

        # ── Stats ──
        investigated = sum(1 for _, inv in filtered if inv)
        stats = {
            'total_parcels':       len(parcels),
            'filtered_after_blockers': len(filtered),
            'investigated_count':  investigated,
            'call_now_count':      len(call_now_picks),
            'build_now_count':     len(build_now_picks),
            'strategic_holds_count': len(hold_picks),
            'pool_sizes': {
                'call_now_pool':  len(call_now_pool),
                'build_now_pool': len(build_now_pool),
                'hold_pool':      len(hold_pool),
            },
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
