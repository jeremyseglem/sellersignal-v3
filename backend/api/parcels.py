"""
Parcel detail API — the dossier shown when user clicks a pin.

  GET /api/parcels/:pin          — full parcel dossier with investigation data
  GET /api/parcels/:pin/why      — zero-API "why they're not selling yet" read
"""
from fastapi import APIRouter, HTTPException
from backend.api.db import get_supabase_client
from backend.scoring.why_not_selling import generate_why_not_selling

router = APIRouter()


@router.get("/{pin}")
async def get_parcel(pin: str):
    """
    Full parcel dossier. Returns parcel facts + investigation data if present.
    Used for the property-card overlay in the unified map+briefing UI.

    If no deep investigation exists, includes a why_not_selling forensic read
    derived from structural features (zero API cost).
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        parcel_result = (supa.table('parcels_v3')
                         .select('*')
                         .eq('pin', pin)
                         .maybe_single()
                         .execute())
        parcel = parcel_result.data if parcel_result else None

        if not parcel:
            raise HTTPException(404, f"Parcel {pin} not found")

        # Prefer deep, fall back to screen
        inv_deep = (supa.table('investigations_v3')
                    .select('*')
                    .eq('pin', pin)
                    .eq('mode', 'deep')
                    .maybe_single()
                    .execute())
        investigation = inv_deep.data if inv_deep else None

        if not investigation:
            inv_screen = (supa.table('investigations_v3')
                          .select('*')
                          .eq('pin', pin)
                          .eq('mode', 'screen')
                          .maybe_single()
                          .execute())
            investigation = inv_screen.data if inv_screen else None

        response = {
            'pin':          pin,
            'parcel':       parcel,
            'investigation': investigation,
            'recommended_action': None,
            'why_not_selling':    None,
        }

        if investigation and investigation.get('action_category'):
            response['recommended_action'] = {
                'category':  investigation['action_category'],
                'tone':      investigation.get('action_tone'),
                'pressure':  investigation.get('action_pressure'),
                'reason':    investigation.get('action_reason'),
                'next_step': investigation.get('action_next_step'),
            }

        # If no actionable investigation, include why-not-selling read
        if (not investigation or
            investigation.get('action_category') in (None, 'hold')):
            response['why_not_selling'] = generate_why_not_selling(parcel)

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching parcel: {e}")


@router.get("/{pin}/why")
async def get_why_not_selling_endpoint(pin: str):
    """
    Zero-API forensic read — no SerpAPI cost per lookup.
    Used when clicking a parcel pin that doesn't have an investigation record.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        result = (supa.table('parcels_v3')
                  .select('*')
                  .eq('pin', pin)
                  .maybe_single()
                  .execute())
        parcel = result.data if result else None

        if not parcel:
            raise HTTPException(404, f"Parcel {pin} not found")

        why = generate_why_not_selling(parcel)

        return {
            'pin':                  pin,
            'address':              parcel.get('address'),
            'owner_name':           parcel.get('owner_name'),
            'value':                parcel.get('total_value'),
            'why_not_selling':      why['why_not_selling'],
            'what_could_change_this': why['what_could_change_this'],
            'transition_window':    why['transition_window'],
            'base_rate_24mo':       why['base_rate_24mo'],
            'confidence':           why['confidence'],
            'archetype':            why['archetype'],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error fetching why-not-selling: {e}")
