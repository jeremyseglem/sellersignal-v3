"""
Lead organization API — notes and tags.

Companion to lead_interactions.py. The interaction log answers
"what happened to this lead" (immutable event stream). This module
answers "how do I, the agent, organize and remember this lead"
(mutable notes + free-form tags).

Endpoints:

  Notes — mutable, multiple per (agent, parcel):
    POST   /api/lead-notes               body: {pin, zip_code, body}
    PUT    /api/lead-notes/{id}          body: {body}
    DELETE /api/lead-notes/{id}
    GET    /api/lead-notes/by-pin/{pin}

  Tags — flat (agent, pin, zip, tag) assignments:
    POST   /api/lead-tags                body: {pin, zip_code, tag}
    DELETE /api/lead-tags/{id}
    GET    /api/lead-tags                # this agent's distinct tags + counts
    GET    /api/lead-tags/by-pin/{pin}   # tags on one parcel
    GET    /api/lead-tags/by-tag/{tag}   # pins carrying this tag

Design from schema/019_lead_organization.sql:
  - Notes are mutable. Each note row has its own id; an agent can
    add, edit, or delete notes freely. Multiple notes per parcel
    is the norm — the spec calls for note history, not single
    overwrites.
  - Tags are flat. An agent's distinct tag strings form their own
    private taxonomy; there is no separate taxonomy table to
    manage. Tags are scoped per agent (your "Hot lead" and mine
    are unrelated).
  - Both tables enforce ownership via RLS — auth.uid() must match
    agent_id. This module additionally validates request input
    before hitting the DB so we return clean 400s rather than
    cryptic Postgres errors.
"""
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import user_from_authorization
from backend.api.db import get_supabase_client


router = APIRouter()


# ── Tag normalization ──────────────────────────────────────────────
# Keep this in sync with the frontend's tag input. Whitespace is
# collapsed and trimmed; case is preserved (agents may have stylistic
# preferences like 'Hot Lead' vs 'hot lead' — we don't force a choice,
# but we DO dedupe based on exact match, so 'Hot Lead' and 'hot lead'
# CAN coexist for the same agent. If that becomes annoying we'll
# normalize case here; for now, preserve.).

def _normalize_tag(raw: str) -> str:
    """Collapse internal whitespace and trim. Preserves case."""
    return ' '.join(raw.split())


# ════════════════════════════════════════════════════════════════════
#  NOTES
# ════════════════════════════════════════════════════════════════════

class NoteCreate(BaseModel):
    pin:      str = Field(..., min_length=1, max_length=64)
    zip_code: str = Field(..., min_length=3, max_length=10)
    body:     str = Field(..., min_length=1, max_length=4000)


class NoteUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


@router.post("/lead-notes")
async def create_note(
    payload: NoteCreate,
    authorization: Optional[str] = Header(None),
):
    """Create a new note on a parcel. Returns the inserted row."""
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    row = {
        'agent_id': user.id,
        'pin':      payload.pin,
        'zip_code': payload.zip_code,
        'body':     payload.body.strip(),
    }
    try:
        res = supa.table('lead_notes_v3').insert(row).execute()
    except Exception as e:
        raise HTTPException(400, f"Failed to create note: {e}")

    if not res.data:
        raise HTTPException(500, "Insert returned no row")
    return res.data[0]


@router.put("/lead-notes/{note_id}")
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    authorization: Optional[str] = Header(None),
):
    """Edit an existing note's body. Returns the updated row.

    RLS guarantees the update only affects the calling agent's own
    notes — even if a client sends a note_id belonging to someone
    else, the update will silently match zero rows and we return 404.
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    try:
        res = (supa.table('lead_notes_v3')
               .update({'body': payload.body.strip()})
               .eq('id', note_id)
               .eq('agent_id', user.id)
               .execute())
    except Exception as e:
        raise HTTPException(400, f"Failed to update note: {e}")

    if not res.data:
        raise HTTPException(404, "Note not found")
    return res.data[0]


@router.delete("/lead-notes/{note_id}")
async def delete_note(
    note_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a note. RLS scoped to caller; missing rows return 404."""
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    try:
        res = (supa.table('lead_notes_v3')
               .delete()
               .eq('id', note_id)
               .eq('agent_id', user.id)
               .execute())
    except Exception as e:
        raise HTTPException(400, f"Failed to delete note: {e}")

    if not res.data:
        raise HTTPException(404, "Note not found")
    return {'deleted': True, 'id': note_id}


@router.get("/lead-notes/by-pin/{pin}")
async def list_notes_by_pin(
    pin: str,
    authorization: Optional[str] = Header(None),
):
    """All this agent's notes for one parcel, newest first."""
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    res = (supa.table('lead_notes_v3')
           .select('id, pin, zip_code, body, created_at, updated_at')
           .eq('agent_id', user.id)
           .eq('pin', pin)
           .order('created_at', desc=True)
           .limit(200)  # defensive cap
           .execute())

    return {'pin': pin, 'notes': res.data or []}


# ════════════════════════════════════════════════════════════════════
#  TAGS
# ════════════════════════════════════════════════════════════════════

class TagCreate(BaseModel):
    pin:      str = Field(..., min_length=1, max_length=64)
    zip_code: str = Field(..., min_length=3, max_length=10)
    tag:      str = Field(..., min_length=1, max_length=40)


@router.post("/lead-tags")
async def create_tag(
    payload: TagCreate,
    authorization: Optional[str] = Header(None),
):
    """Assign a tag to a parcel.

    Normalizes whitespace before insert. If the (agent, pin, tag)
    combo already exists, the UNIQUE constraint raises and we return
    the existing row rather than erroring — clicking "add tag" twice
    is idempotent from the user's perspective.
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    tag = _normalize_tag(payload.tag)
    if not tag:
        raise HTTPException(400, "Tag is empty after normalization")

    row = {
        'agent_id': user.id,
        'pin':      payload.pin,
        'zip_code': payload.zip_code,
        'tag':      tag,
    }
    try:
        res = supa.table('lead_tags_v3').insert(row).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        # If the violation is the UNIQUE constraint, look up and
        # return the existing row. Anything else is a real error.
        if 'duplicate key' in str(e).lower() or '23505' in str(e):
            existing = (supa.table('lead_tags_v3')
                        .select('*')
                        .eq('agent_id', user.id)
                        .eq('pin', payload.pin)
                        .eq('tag', tag)
                        .limit(1)
                        .execute())
            if existing.data:
                return existing.data[0]
        raise HTTPException(400, f"Failed to create tag: {e}")

    raise HTTPException(500, "Insert returned no row")


@router.delete("/lead-tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    authorization: Optional[str] = Header(None),
):
    """Remove a tag assignment by id."""
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    try:
        res = (supa.table('lead_tags_v3')
               .delete()
               .eq('id', tag_id)
               .eq('agent_id', user.id)
               .execute())
    except Exception as e:
        raise HTTPException(400, f"Failed to delete tag: {e}")

    if not res.data:
        raise HTTPException(404, "Tag not found")
    return {'deleted': True, 'id': tag_id}


@router.get("/lead-tags")
async def list_tags(
    zip_code: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """List this agent's distinct tags with usage counts.

    Optionally filter by zip_code. Powers the briefing-page filter
    chip row: agents see only the tags they've actually used (plus
    counts for relevance ordering).

    Response shape:
      {
        tags: [
          {"tag": "Hot lead",       "count": 4},
          {"tag": "Out of state",   "count": 2},
          ...
        ]
      }
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    q = (supa.table('lead_tags_v3')
         .select('tag')
         .eq('agent_id', user.id))
    if zip_code:
        q = q.eq('zip_code', zip_code)
    res = q.execute()

    counts: dict[str, int] = {}
    for row in (res.data or []):
        t = row['tag']
        counts[t] = counts.get(t, 0) + 1

    # Sort by count desc, then alphabetically for stable display.
    tags = sorted(
        [{'tag': t, 'count': c} for t, c in counts.items()],
        key=lambda r: (-r['count'], r['tag'].lower()),
    )
    return {'tags': tags}


@router.get("/lead-tags/by-pin/{pin}")
async def list_tags_by_pin(
    pin: str,
    authorization: Optional[str] = Header(None),
):
    """All tags this agent has assigned to one parcel."""
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    res = (supa.table('lead_tags_v3')
           .select('id, pin, zip_code, tag, created_at')
           .eq('agent_id', user.id)
           .eq('pin', pin)
           .order('created_at', desc=False)
           .execute())

    return {'pin': pin, 'tags': res.data or []}


@router.get("/lead-tags/by-tag/{tag}")
async def list_pins_by_tag(
    tag: str,
    zip_code: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """All pins this agent has assigned this tag to.

    Powers "search by tag" in the briefing UI. zip_code filter is
    optional — without it, the response spans all the agent's ZIPs
    (useful once operators view across territories; agents
    realistically only have one).
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    tag_norm = _normalize_tag(tag)

    q = (supa.table('lead_tags_v3')
         .select('id, pin, zip_code, tag, created_at')
         .eq('agent_id', user.id)
         .eq('tag', tag_norm))
    if zip_code:
        q = q.eq('zip_code', zip_code)
    res = q.order('created_at', desc=True).execute()

    return {
        'tag':         tag_norm,
        'zip_code':    zip_code,
        'assignments': res.data or [],
    }


# ════════════════════════════════════════════════════════════════════
#  MY LEADS — agent's active pipeline view
# ════════════════════════════════════════════════════════════════════

# Funnel-status events. These are the event types that actually move
# a lead through the agent's pipeline. Other event types ('called',
# 'mailed', 'voicemail', 'skip_traced', 'got_response', 'no_response',
# 'reactivated') are actions or outcomes, not status changes.
_FUNNEL_STATUS_EVENTS = (
    'working',
    'listing_discussion',
    'sent_to_crm',
    'closed',
    'not_relevant',
)

# Statuses that EXIT the pipeline. A lead with one of these as its
# most recent funnel-status event does not appear in My Leads —
# the agent has actively decided this lead is done.
_EXIT_STATUSES = ('not_relevant', 'closed')


@router.get("/my-leads")
async def my_leads(
    authorization: Optional[str] = Header(None),
):
    """List every parcel this agent has any engagement signal on,
    minus dismissed/closed ones.

    A pin enters this list when the agent has:
      - any row in lead_interactions_v3 (called, mailed, working, etc.)
      - any row in lead_notes_v3 (wrote a note)
      - any row in lead_tags_v3 (assigned a tag)

    A pin EXITS when its most recent funnel-status event is
    'not_relevant' or 'closed'. Reactivation pulls it back in
    because 'reactivated' is not in the exit set; the next
    funnel-status event determines visibility.

    Returns a flat list (frontend groups by status). One round-trip
    to the database per signal table, no N+1.

    Response shape:
      {
        leads: [
          {pin, zip_code, address, owner_name, city, state,
           total_value, status, status_at, tags, notes_count,
           last_action_at, last_action_type},
          ...
        ],
        available_tags: [{tag, count}, ...],
        totals: {working, listing_discussion, engaged, total}
      }
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    agent_id = user.id

    # ── Step 1: gather every engaged pin from the three signal tables.
    # Pull (pin, created_at) so we can compute last_action_at across
    # all sources, and (pin, event_type) so we can find last funnel
    # status without a second query.
    interactions = (supa.table('lead_interactions_v3')
                    .select('pin, zip_code, event_type, created_at')
                    .eq('agent_id', agent_id)
                    .order('created_at', desc=True)
                    .execute()).data or []
    notes = (supa.table('lead_notes_v3')
             .select('pin, zip_code, updated_at')
             .eq('agent_id', agent_id)
             .order('updated_at', desc=True)
             .execute()).data or []
    tag_rows = (supa.table('lead_tags_v3')
                .select('pin, zip_code, tag, created_at')
                .eq('agent_id', agent_id)
                .order('created_at', desc=True)
                .execute()).data or []

    engaged_pins: set[str] = set()
    for row in interactions: engaged_pins.add(row['pin'])
    for row in notes:        engaged_pins.add(row['pin'])
    for row in tag_rows:     engaged_pins.add(row['pin'])

    if not engaged_pins:
        return {
            'leads':           [],
            'available_tags':  [],
            'totals':          {'working': 0, 'listing_discussion': 0,
                                'engaged': 0, 'total': 0},
        }

    # ── Step 2: compute most-recent funnel-status event per pin.
    # Iterate interactions in chronological order (already DESC by
    # created_at from query) and keep the FIRST funnel-status event
    # seen for each pin.
    status_by_pin: dict[str, dict] = {}
    for row in interactions:
        et = row['event_type']
        if et not in _FUNNEL_STATUS_EVENTS:
            continue
        pin = row['pin']
        if pin in status_by_pin:
            continue  # already have the newest
        status_by_pin[pin] = {
            'status':    et,
            'status_at': row['created_at'],
        }

    # ── Step 3: filter out pins whose most-recent funnel status is
    # in the exit set. Pins with no funnel status at all stay in
    # (they're "engaged" — touched but not yet formally classified).
    active_pins = [
        p for p in engaged_pins
        if status_by_pin.get(p, {}).get('status') not in _EXIT_STATUSES
    ]

    if not active_pins:
        return {
            'leads':           [],
            'available_tags':  [],
            'totals':          {'working': 0, 'listing_discussion': 0,
                                'engaged': 0, 'total': 0},
        }

    # ── Step 4: hydrate parcel data for active pins.
    parcels_res = (supa.table('parcels_v3')
                   .select('pin, zip_code, address, owner_name, city, state, '
                           'total_value, lat, lng')
                   .in_('pin', active_pins)
                   .execute()).data or []
    parcel_by_pin = {row['pin']: row for row in parcels_res}

    # ── Step 5: aggregate per-pin tags, note counts, and last_action.
    tags_by_pin: dict[str, list[str]] = {}
    for row in tag_rows:
        if row['pin'] not in active_pins:
            continue
        tags_by_pin.setdefault(row['pin'], []).append(row['tag'])

    note_counts: dict[str, int] = {}
    for row in notes:
        if row['pin'] not in active_pins:
            continue
        note_counts[row['pin']] = note_counts.get(row['pin'], 0) + 1

    # last_action_at = max(timestamp from interactions, notes, tags)
    # last_action_type = the source/type of that latest event
    last_action: dict[str, tuple[str, str]] = {}  # pin -> (ts, type)
    def record_last(pin, ts, type_label):
        if not ts:
            return
        cur = last_action.get(pin)
        if (cur is None) or (ts > cur[0]):
            last_action[pin] = (ts, type_label)

    for row in interactions:
        if row['pin'] in active_pins:
            record_last(row['pin'], row['created_at'], row['event_type'])
    for row in notes:
        if row['pin'] in active_pins:
            record_last(row['pin'], row['updated_at'], 'noted')
    for row in tag_rows:
        if row['pin'] in active_pins:
            record_last(row['pin'], row['created_at'], 'tagged')

    # ── Step 6: assemble lead rows.
    leads = []
    for pin in active_pins:
        parcel = parcel_by_pin.get(pin) or {}
        status_info = status_by_pin.get(pin, {})
        la = last_action.get(pin, (None, None))
        leads.append({
            'pin':              pin,
            'zip_code':         parcel.get('zip_code'),
            'address':          parcel.get('address'),
            'owner_name':       parcel.get('owner_name'),
            'city':             parcel.get('city'),
            'state':            parcel.get('state'),
            'total_value':      parcel.get('total_value'),
            'lat':              parcel.get('lat'),
            'lng':              parcel.get('lng'),
            'status':           status_info.get('status'),       # may be None
            'status_at':        status_info.get('status_at'),
            'tags':             tags_by_pin.get(pin, []),
            'notes_count':      note_counts.get(pin, 0),
            'last_action_at':   la[0],
            'last_action_type': la[1],
        })

    # Sort newest-touched first by default. Frontend can re-sort.
    leads.sort(
        key=lambda r: (r['last_action_at'] or ''),
        reverse=True,
    )

    # ── Step 7: tag taxonomy + totals for the page header.
    tag_counts: dict[str, int] = {}
    for tags in tags_by_pin.values():
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    available_tags = sorted(
        [{'tag': t, 'count': c} for t, c in tag_counts.items()],
        key=lambda r: (-r['count'], r['tag'].lower()),
    )

    totals = {
        'working':            sum(1 for L in leads if L['status'] == 'working'),
        'listing_discussion': sum(1 for L in leads if L['status'] == 'listing_discussion'),
        'sent_to_crm':        sum(1 for L in leads if L['status'] == 'sent_to_crm'),
        'engaged':            sum(1 for L in leads if not L['status']),
        'total':              len(leads),
    }

    return {
        'leads':          leads,
        'available_tags': available_tags,
        'totals':         totals,
    }
