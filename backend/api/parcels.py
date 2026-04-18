"""
Parcel detail API — the dossier shown when user clicks a pin.

  GET /api/parcels/:pin          — full parcel dossier with investigation data
  GET /api/parcels/:pin/why      — zero-API "why they're not selling yet" read

The zero-API variant is the key insight: for parcels that aren't in any
action category, the map-click popover shows a forensic read derived from
structural features (owner_type, tenure, value, band, signal_family). No
SerpAPI calls, so agents can click around all day for free.
"""
from fastapi import APIRouter, HTTPException
from backend.api.db import get_supabase_client

router = APIRouter()


@router.get("/{pin}")
async def get_parcel(pin: str):
    """
    Full parcel dossier. Used when the parcel has an investigation record
    and we have the full signal inventory to display.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")
    # TODO: Wire to Supabase read of parcels + investigations joined
    return {
        "pin": pin,
        "status": "scaffold_only",
        "parcel": None,
        "investigation": None,
        "recommended_action": None,
    }


@router.get("/{pin}/why")
async def get_why_not_selling(pin: str):
    """
    Zero-API forensic read: 'why this parcel isn't a seller yet'.
    Generated from structural features, no search budget consumed.

    Returns a templated explanation based on:
      - Owner type (individual / trust / LLC / estate)
      - Tenure years
      - Value tier
      - Band assignment
      - Signal family (if any was assigned)

    Used for map-click on non-action leads.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")
    # TODO: Port the template generator from the "why not selling" logic
    return {
        "pin": pin,
        "status": "scaffold_only",
        "why_not_selling": None,
        "what_would_change_this": None,
        "estimated_transition_window": None,
    }
