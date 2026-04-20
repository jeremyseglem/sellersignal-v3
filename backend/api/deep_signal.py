"""
Deep Signal API — serves LLM-generated outreach narrative + scripts for
an investigated parcel.

  POST /api/deep-signal/{pin}   — generate (cache-first)
  GET  /api/deep-signal/{pin}   — read cached only, return 404 if absent

Cache table: deep_signals_v3 (see schema/005_deep_signals.sql).
Synthesis engine: backend/research/deep_signal.py.

Only investigated parcels (those with a row in investigations_v3) can
produce a Deep Signal — the whole point is to ground the LLM in verified
research, and non-investigated parcels have no research surface.

Call cost: ~$0.02 per fresh synthesis (Claude Sonnet 4, ~1500 tokens out).
Cached hits are free. Synthesis latency: 3-8 seconds.
"""
from fastapi import APIRouter, HTTPException, Path

from backend.api.db import get_supabase_client
from backend.api.zip_gate import get_zip_status
from backend.research.deep_signal import generate_deep_signal

router = APIRouter()


def _load_parcel_and_investigation(supa, pin: str) -> tuple[dict, dict]:
    """Fetch parcel + best-available investigation. Raises 404 as needed."""
    parcel_res = (supa.table('parcels_v3')
                  .select('*')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
    parcel = parcel_res.data if parcel_res else None
    if not parcel:
        raise HTTPException(404, f"Parcel {pin} not found")

    # ZIP coverage gate — same rule as /api/parcels/:pin
    zip_code = parcel.get('zip_code')
    if not zip_code or get_zip_status(zip_code) != 'live':
        raise HTTPException(404, f"Parcel {pin} not found")

    # Prefer deep mode, fall back to screen mode
    deep = (supa.table('investigations_v3')
            .select('*').eq('pin', pin).eq('mode', 'deep')
            .maybe_single().execute())
    investigation = deep.data if deep else None
    if not investigation:
        scr = (supa.table('investigations_v3')
               .select('*').eq('pin', pin).eq('mode', 'screen')
               .maybe_single().execute())
        investigation = scr.data if scr else None

    if not investigation:
        raise HTTPException(
            409,
            f"Parcel {pin} has not been investigated yet — Deep Signal "
            "requires verified research to ground its output"
        )

    return parcel, investigation


def _shape_response(row: dict) -> dict:
    """Shape the cached row into the response payload the frontend expects."""
    return {
        'pin':              row.get('pin'),
        'motivation':       row.get('motivation') or '',
        'timeline':         row.get('timeline') or '',
        'best_channel':     row.get('best_channel') or '',
        'call_script':      row.get('call_script') or '',
        'mail_script':      row.get('mail_script') or '',
        'door_script':      row.get('door_script') or '',
        'what_not_to_say':  row.get('what_not_to_say') or '',
        'model':            row.get('model'),
        'generated_at':     row.get('generated_at'),
        'cached':           True,
    }


@router.post("/{pin}")
async def generate_or_fetch_deep_signal(
    pin: str = Path(..., pattern=r'^\d{6,12}$'),
    force: bool = False,
):
    """
    Return the Deep Signal for this parcel.

    Cache-first: if a row exists in deep_signals_v3 for this pin, return it
    immediately unless ?force=true, which re-synthesizes.

    On cache miss (or force=true):
      1. Load parcel + investigation from Supabase
      2. Call Claude Sonnet 4 with the grounded prompt
      3. Parse + validate the JSON response
      4. Upsert into deep_signals_v3
      5. Return the payload

    Returns 409 if the parcel hasn't been investigated yet (Deep Signal
    has no verified research to ground on in that case).
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Cache check (unless force)
    if not force:
        try:
            cached = (supa.table('deep_signals_v3')
                      .select('*')
                      .eq('pin', pin)
                      .maybe_single()
                      .execute())
            if cached and cached.data:
                return _shape_response(cached.data)
        except Exception:
            # Non-fatal — fall through to fresh synthesis
            pass

    # Fresh synthesis path
    parcel, investigation = _load_parcel_and_investigation(supa, pin)

    try:
        result = generate_deep_signal(parcel, investigation)
    except ImportError as e:
        raise HTTPException(503, f"Anthropic SDK not available: {e}")
    except Exception as e:
        raise HTTPException(502, f"Deep Signal synthesis failed: {e}")

    # Persist to cache
    row = {
        'pin':             pin,
        'zip_code':        parcel.get('zip_code'),
        'report':          result.get('_raw'),
        'motivation':      result.get('motivation'),
        'timeline':        result.get('timeline'),
        'best_channel':    result.get('best_channel'),
        'call_script':     result.get('call_script'),
        'mail_script':     result.get('mail_script'),
        'door_script':     result.get('door_script'),
        'what_not_to_say': result.get('what_not_to_say'),
        'model':           result.get('model'),
        'tokens_in':       result.get('tokens_in'),
        'tokens_out':      result.get('tokens_out'),
    }
    try:
        supa.table('deep_signals_v3').upsert(row, on_conflict='pin').execute()
    except Exception as e:
        # Cache write failure is non-fatal — we still return the fresh result
        print(f"[deep_signal] cache write failed for {pin}: {e}")

    return {
        'pin':              pin,
        'motivation':       row['motivation'] or '',
        'timeline':         row['timeline'] or '',
        'best_channel':     row['best_channel'] or '',
        'call_script':      row['call_script'] or '',
        'mail_script':      row['mail_script'] or '',
        'door_script':      row['door_script'] or '',
        'what_not_to_say':  row['what_not_to_say'] or '',
        'model':            row['model'],
        'tokens_in':        row['tokens_in'],
        'tokens_out':       row['tokens_out'],
        'cached':           False,
    }


@router.get("/{pin}")
async def read_cached_deep_signal(
    pin: str = Path(..., pattern=r'^\d{6,12}$'),
):
    """
    Return the cached Deep Signal if it exists, else 404.

    Used by the frontend to check existence before showing the "Deep Signal"
    button in an active vs. idle state.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        cached = (supa.table('deep_signals_v3')
                  .select('*')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
    except Exception as e:
        raise HTTPException(500, f"Error reading cache: {e}")

    if not cached or not cached.data:
        raise HTTPException(404, f"No Deep Signal cached for {pin}")
    return _shape_response(cached.data)
