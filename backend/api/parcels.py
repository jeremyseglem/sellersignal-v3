"""
Parcel detail API — the dossier shown when user clicks a pin.

  GET /api/parcels/:pin          — full parcel dossier with investigation data
  GET /api/parcels/:pin/why      — zero-API "why they're not selling yet" read

Parcel endpoints are keyed on pin, not zip. But they enforce ZIP coverage
implicitly: we fetch the parcel, read its zip_code, then check that the
ZIP is in coverage. If not, we return 404 as if the parcel didn't exist.
"""
from fastapi import APIRouter, HTTPException
from backend.api.db import get_supabase_client
from backend.api.zip_gate import get_zip_status
from backend.scoring.why_not_selling import generate_why_not_selling
from backend.selection.parcel_state_tags import (
    derive_tags as derive_parcel_state_tags,
)

router = APIRouter()


def _assert_parcel_zip_is_live(parcel: dict) -> None:
    """Raise 404 if the parcel's ZIP isn't live in coverage."""
    zip_code = parcel.get('zip_code')
    if not zip_code:
        raise HTTPException(404, "Parcel has no ZIP assignment")
    status = get_zip_status(zip_code)
    if status != 'live':
        # Return 404 rather than leaking the fact that the parcel exists
        # but is in a non-live ZIP
        raise HTTPException(404, f"Parcel not found")


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

        # Enforce ZIP coverage — return 404 if parcel's ZIP isn't live
        _assert_parcel_zip_is_live(parcel)

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

        # Harvester overlay: pull raw_signal_matches_v3 for this pin and
        # translate to the investigation-shape dict so the dossier can show
        # "obituary (strict): Tina Jean Fee Han, 2026-03-31" style reasons
        # and an itemized list of signals. Same bridge used by the briefing
        # endpoint — see backend/selection/harvester_overlay.py.
        harvester_match_rows = (
            supa.table('raw_signal_matches_v3')
            .select('raw_signal_id, pin, match_strength, '
                    'match_method, matched_at')
            .eq('pin', pin)
            .limit(50)
            .execute()
        ).data or []

        harvester_signals_by_id: dict = {}
        if harvester_match_rows:
            sig_ids = list({m['raw_signal_id'] for m in harvester_match_rows})
            sigs_res = (
                supa.table('raw_signals_v3')
                .select('id, source_type, signal_type, trust_level, '
                        'party_names, event_date, document_ref')
                .in_('id', sig_ids)
                .execute()
            )
            for r in (sigs_res.data or []):
                harvester_signals_by_id[r['id']] = r

        from backend.selection.harvester_overlay import (
            build_investigation_overlay, merge_with_existing,
        )
        overlay = build_investigation_overlay(
            pin, harvester_match_rows, harvester_signals_by_id
        )

        # Shape the SerpAPI row (if any) to match the overlay structure
        # so merge_with_existing can compare them apples-to-apples.
        existing_shaped = None
        if investigation:
            rec_existing = None
            if investigation.get('action_category'):
                rec_existing = {
                    'category':  investigation['action_category'],
                    'tone':      investigation.get('action_tone'),
                    'pressure':  investigation.get('action_pressure'),
                    'reason':    investigation.get('action_reason'),
                    'next_step': investigation.get('action_next_step'),
                }
            existing_shaped = {
                'mode':               investigation.get('mode'),
                'has_blocker':        investigation.get('has_blocker', False),
                'has_life_event':     investigation.get('has_life_event', False),
                'has_financial':      investigation.get('has_financial', False),
                'recommended_action': rec_existing,
            }
        merged = merge_with_existing(existing_shaped, overlay)

        # Per-pin last arms-length sale (from sales_history_v3 via the
        # parcel_last_arms_length_v3 view). Only queries when the view
        # exists; silently falls through on empty/error so derive_tags
        # uses the legacy last_transfer_price path.
        al_row: dict = {}
        try:
            al_res = (supa.table('parcel_last_arms_length_v3')
                      .select('last_arms_length_price, '
                              'last_arms_length_date, '
                              'last_arms_length_buyer, '
                              'last_arms_length_seller')
                      .eq('pin', pin)
                      .maybe_single()
                      .execute())
            if al_res and al_res.data:
                al_row = al_res.data
        except Exception:
            al_row = {}

        # Full sales history — all transfers the eReal Property harvester
        # parsed for this parcel, ordered most-recent-first. Includes
        # is_arms_length flag set at parse time. Parcels not yet
        # harvested return []. The UI renders a "Sales history" block
        # when this list is non-empty; it surfaces divorces (Property
        # Settlement reason), estate distributions, trust moves, and
        # genuine arms-length purchases for narrative context.
        sales_history: list = []
        try:
            sales_res = (supa.table('sales_history_v3')
                         .select('recording_number, excise_number, '
                                 'sale_date, sale_price, seller_name, '
                                 'buyer_name, instrument, sale_reason, '
                                 'is_arms_length')
                         .eq('pin', pin)
                         .order('sale_date', desc=True)
                         .limit(20)
                         .execute())
            sales_history = sales_res.data or []
        except Exception:
            sales_history = []

        response = {
            'pin':          pin,
            'parcel':       parcel,
            'investigation': investigation,
            'recommended_action': None,
            'why_not_selling':    None,
            # Harvester sidecar fields — always present (empty list if no
            # matches) so UI code can render unconditionally.
            'harvester_matches':   [],
            'convergence':         False,
            'strict_match_count':  0,
            # Parcel-state situational tags, enriched with arms-length
            # data when the parcel has sales history. See
            # backend/selection/parcel_state_tags.py.
            'parcel_state_tags':   derive_parcel_state_tags({**parcel, **al_row}),
            # Expose arms-length fields directly so the dossier UI can
            # show them in the facts block. None when no sales history
            # has been fetched yet.
            'last_arms_length_price':  al_row.get('last_arms_length_price'),
            'last_arms_length_date':   al_row.get('last_arms_length_date'),
            'last_arms_length_buyer':  al_row.get('last_arms_length_buyer'),
            'last_arms_length_seller': al_row.get('last_arms_length_seller'),
            # Full sales history — empty list if parcel not harvested yet.
            'sales_history':       sales_history,
        }

        # The merged recommended_action reflects the highest-pressure of
        # (SerpAPI-era action, harvester overlay). This is what the
        # dossier's "Recommended Action" block renders.
        if merged and merged.get('recommended_action'):
            response['recommended_action'] = merged['recommended_action']

        if merged:
            response['harvester_matches']  = merged.get('harvester_matches') or []
            response['convergence']        = bool(merged.get('convergence'))
            response['strict_match_count'] = int(merged.get('strict_match_count') or 0)

        # If there's no actionable signal (no investigation AND no
        # harvester match promoting this parcel), include the why-not-selling
        # structural read. With a strict harvester match, the agent already
        # has a clear "why call now" story; why_not_selling would just
        # muddy the card.
        has_actionable_recommendation = bool(
            response['recommended_action']
            and (response['recommended_action'].get('category') or '') != 'hold'
        )
        if not has_actionable_recommendation:
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

        _assert_parcel_zip_is_live(parcel)

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
