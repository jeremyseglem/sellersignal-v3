"""
Lead interactions API.

Powers the Lead Memory layer described in the v4 spec: the agent's
"working / not relevant / sent to CRM" state per parcel, plus the
outcome dropdown that appears once a lead is being worked.

  POST /api/lead-interactions
        body: {pin, zip_code, event_type, event_data?}
        Logs a new event for the authenticated agent.

  GET /api/lead-interactions/by-pin/{pin}
        Returns the full event log for one parcel from the
        authenticated agent's history. Used by the dossier to
        compute current status + show the history line.

  GET /api/lead-interactions/by-zip/{zip}
        Returns a per-pin status map for the authenticated agent
        across an entire ZIP. Used by the briefing page to overlay
        status on the action list and pipeline (e.g., pin a
        "working" lead to the top of its section).

Design notes from schema/011_lead_interactions.sql:
  - Event log, not state row. Each click writes a new row;
    "current state" is the most recent status-changing event.
  - "Undo" works by writing a superseding event, never DELETE.
  - RLS denies UPDATE/DELETE entirely — events are immutable.
  - event_data is a JSONB field for forward-compatible metadata
    (outcome notes, CRM destination, etc.) without future migrations.

The constrained event_type vocabulary lives in the table CHECK
constraint (working / not_relevant / sent_to_crm / got_response /
no_response / listing_discussion / closed / reactivated). Inserts
that violate it return 400 from this endpoint after the DB rejects
them.
"""
from typing import Optional, Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import user_from_authorization
from backend.api.db import get_supabase_client


router = APIRouter()


# ── Models ──────────────────────────────────────────────────────

# The vocabulary mirrors the CHECK constraint in
# schema/011_lead_interactions.sql. Adding a new value here without
# a matching schema migration will cause inserts to fail.
_VALID_EVENT_TYPES = frozenset({
    'working',
    'not_relevant',
    'sent_to_crm',
    'got_response',
    'no_response',
    'listing_discussion',
    'closed',
    'reactivated',
})


class InteractionCreate(BaseModel):
    pin:        str = Field(..., min_length=1, max_length=64)
    zip_code:   str = Field(..., min_length=3, max_length=10)
    event_type: str
    # Free-form structured metadata. Examples:
    #   {} for working / not_relevant
    #   {"crm": "follow_up_boss"} for sent_to_crm
    #   {"channel": "phone"} for got_response
    # Field is required at the API level but defaults to {} so the
    # client can send it as null/missing for events without metadata.
    event_data: Optional[dict] = None


# ── Endpoints ───────────────────────────────────────────────────

@router.post("")
async def create_interaction(
    body: InteractionCreate,
    authorization: Optional[str] = Header(None),
):
    """Log a new lead interaction event.

    Returns the inserted row on success. Status changes (working,
    not_relevant, sent_to_crm) supersede any prior status; the
    consumer side computes "current status" by taking the most
    recent status-changing event.

    Outcome events (got_response, no_response, listing_discussion,
    closed) record the result of an outreach attempt and don't
    change status — they're additive history, surfaced in the
    dossier's history line.

    'reactivated' is the canonical undo for not_relevant — write
    a reactivated event after a not_relevant to put the lead back
    in the active pipeline. We never DELETE events; the supersede
    pattern preserves the full audit trail.
    """
    if body.event_type not in _VALID_EVENT_TYPES:
        raise HTTPException(
            400,
            f"Unknown event_type {body.event_type!r}. Valid: "
            f"{sorted(_VALID_EVENT_TYPES)}"
        )

    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    row = {
        'agent_id':   user.id,
        'pin':        body.pin,
        'zip_code':   body.zip_code,
        'event_type': body.event_type,
        'event_data': body.event_data or {},
    }
    try:
        res = (supa.table('lead_interactions_v3')
               .insert(row)
               .execute())
    except Exception as e:
        # Most likely cause: CHECK constraint mismatch (caught above)
        # or RLS denying because token user.id != row.agent_id, which
        # shouldn't happen since we set agent_id from the verified
        # user. Surface as 400 so the client sees a real error.
        raise HTTPException(400, f"Failed to log interaction: {e}")

    if not res.data:
        raise HTTPException(500, "Insert returned no row")
    return res.data[0]


@router.get("/by-pin/{pin}")
async def list_by_pin(
    pin: str,
    authorization: Optional[str] = Header(None),
):
    """Return the agent's full event history for one parcel.

    Newest events first. The dossier uses this to:
      - Show current status pill ("Working since Apr 28")
      - Render the history line at the bottom of the dossier
      - Decide which action buttons to show (e.g., hide "Mark as
        working" when status already == working)
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    res = (supa.table('lead_interactions_v3')
           .select('id, pin, zip_code, event_type, event_data, created_at')
           .eq('agent_id', user.id)
           .eq('pin', pin)
           .order('created_at', desc=True)
           .limit(200)  # defensive cap; one parcel shouldn't have hundreds
           .execute())

    return {
        'pin':    pin,
        'events': res.data or [],
    }


@router.get("/by-zip/{zip_code}")
async def status_by_zip(
    zip_code: str,
    authorization: Optional[str] = Header(None),
):
    """Return current per-pin status for the entire ZIP.

    Reads from the lead_status_v3 view (created in migration 011),
    which already does the "most recent status event per pin"
    distinct-on logic. The client consumes this once on briefing
    load and overlays status on every row.

    Response shape:
      {
        zip_code: "98004",
        statuses: {
          "5627300903": {"status": "working", "status_at": "...",
                         "event_data": {}},
          ...
        }
      }
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    res = (supa.table('lead_status_v3')
           .select('pin, status, event_data, status_at')
           .eq('agent_id', user.id)
           .eq('zip_code', zip_code)
           .execute())

    statuses: dict = {}
    for row in (res.data or []):
        statuses[row['pin']] = {
            'status':     row['status'],
            'status_at':  row['status_at'],
            'event_data': row.get('event_data') or {},
        }

    return {
        'zip_code': zip_code,
        'statuses': statuses,
    }
