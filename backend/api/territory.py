"""
Territory API.

  POST /api/agent/claim-zip      — claim a ZIP as your territory.
                                   Validates: ZIP is live, not already
                                   claimed, agent doesn't already have one.
                                   Operators cannot claim (their job is
                                   oversight, not territory).

  GET  /api/agent/territory-status — for the authenticated user, returns:
                                   {
                                     role: 'agent' | 'operator',
                                     my_zip: string | null,
                                     zips: [{
                                       zip_code, city, state,
                                       parcel_count, current_call_now_count,
                                       status: 'mine' | 'available' | 'claimed_by_other' | 'unavailable',
                                       claimed_by_name?: string  // when claimed_by_other
                                     }, ...]
                                   }
                                   Status semantics for AGENTS:
                                     - 'mine'             : the agent's assigned_zip
                                     - 'claimed_by_other' : someone else claimed it
                                     - 'available'        : free to claim
                                   Status semantics for OPERATORS:
                                     - 'mine'             : never (operators don't claim)
                                     - 'available'        : ZIP exists, no agent claim yet
                                     - 'claimed_by_other' : an agent claims this ZIP
                                                            (still navigable for operators)

This module also exports require_zip_access(user, zip_code), used by
briefings and parcels endpoints to gate per-ZIP reads.
"""
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api.db import get_supabase_client
from backend.api.auth import user_from_authorization as _user_from_authorization


router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────

class ClaimZipBody(BaseModel):
    zip_code: str


# ── Internal helpers ───────────────────────────────────────────────

def _load_profile(user_id: str) -> dict:
    """Load the agent_profiles_v3 row for the given user. Raises 404
    if missing, which would only happen if the on-signup trigger
    failed to fire."""
    supa = get_supabase_client()
    res = (supa.table('agent_profiles_v3')
           .select('id, email, full_name, role, assigned_zip')
           .eq('id', user_id)
           .limit(1)
           .execute())
    rows = res.data or []
    if not rows:
        raise HTTPException(404, 'Agent profile not found.')
    return rows[0]


def _live_zips() -> list[dict]:
    """Pull the live-ZIP list from coverage. Falls back to live_zips_v3
    if zip_coverage_v3 isn't populated. Returns rows with at minimum
    {zip_code, city, state, parcel_count, current_call_now_count} —
    tolerant to missing fields."""
    supa = get_supabase_client()
    # NOTE: select('*') instead of explicit columns so this endpoint
    # survives a deploy that lands before migration 022 (per-bucket
    # contact_now_* columns) is applied to Supabase. The Python code
    # tolerates missing fields via `or 0` fallbacks.
    res = (supa.table('zip_coverage_v3')
           .select('*')
           .eq('status', 'live')
           .execute())
    return res.data or []


def _claims_map() -> dict[str, dict]:
    """Map zip_code → {agent_id, full_name} for currently claimed
    territories. Reads from agent_profiles_v3.assigned_zip (single
    source of truth). Joins to full_name for display."""
    supa = get_supabase_client()
    res = (supa.table('agent_profiles_v3')
           .select('id, full_name, email, assigned_zip, role')
           .neq('assigned_zip', None)
           .execute())
    out: dict[str, dict] = {}
    for r in res.data or []:
        z = r.get('assigned_zip')
        if not z:
            continue
        # Operators shouldn't have assigned_zip (we block in claim
        # endpoint), but handle defensively if one ever does.
        if r.get('role') == 'operator':
            continue
        out[z] = {
            'agent_id':  r['id'],
            'full_name': r.get('full_name') or r.get('email') or 'Another agent',
        }
    return out


def require_zip_access(user, zip_code: str) -> None:
    """
    Gate helper used by briefings/parcels endpoints. Allows access if:
      - the user is an operator (sees all)
      - the user's assigned_zip matches the requested zip_code
    Raises 403 otherwise.

    The user object is the Supabase auth user from
    user_from_authorization. It only has id/email; we load the
    profile to get role + assigned_zip.
    """
    profile = _load_profile(user.id)
    if profile.get('role') == 'operator':
        return
    if profile.get('assigned_zip') == zip_code:
        return
    raise HTTPException(
        403,
        f'This ZIP is not in your territory. Your territory: '
        f'{profile.get("assigned_zip") or "(not yet claimed)"}.',
    )


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/claim-zip")
async def claim_zip_endpoint(
    body: ClaimZipBody,
    authorization: Optional[str] = Header(None),
):
    """
    Claim a ZIP as the agent's territory.

    Validation:
      - User must be role='agent' (operators cannot claim — they have
        oversight, not territory)
      - User must not already have an assigned_zip
      - Requested ZIP must be in the live ZIP list
      - Requested ZIP must not already be claimed by another agent

    Side effects (atomic from the caller's perspective):
      1. Sets agent_profiles_v3.assigned_zip
      2. Inserts agent_territories_v3 row (status='active')

    These are two writes; if (2) fails after (1), we roll back (1)
    so the agent can retry. Concurrent claims on the same ZIP are
    resolved by the unique index on agent_profiles_v3.assigned_zip
    (set up in migration 010) — second writer gets a unique
    constraint violation, which we surface as a friendly 409.
    """
    user = _user_from_authorization(authorization)
    profile = _load_profile(user.id)

    # Operator block
    if profile.get('role') == 'operator':
        raise HTTPException(
            403,
            'Operators do not claim territories — operators have '
            'oversight access to all ZIPs.',
        )

    # Already-claimed-own block
    if profile.get('assigned_zip'):
        raise HTTPException(
            409,
            f'You already claimed {profile["assigned_zip"]} as your '
            f'territory. Each agent claims one ZIP. Contact the '
            f'SellerSignal team if you need to change it.',
        )

    zip_code = body.zip_code.strip()

    # Live-ZIP validation
    live = _live_zips()
    live_codes = {z['zip_code'] for z in live}
    if zip_code not in live_codes:
        raise HTTPException(
            400,
            f'{zip_code} is not a live ZIP. Available ZIPs: '
            f'{", ".join(sorted(live_codes))}',
        )

    # Already-claimed-by-other check (race-condition fallback handled
    # by the unique constraint below, but cheap to check first).
    claims = _claims_map()
    if zip_code in claims:
        raise HTTPException(
            409,
            f'{zip_code} is already claimed by another agent.',
        )

    supa = get_supabase_client()

    # Step 1: set assigned_zip on profile.
    upd = (supa.table('agent_profiles_v3')
           .update({'assigned_zip': zip_code})
           .eq('id', user.id)
           .execute())
    if not upd.data:
        raise HTTPException(500, 'Failed to assign ZIP to profile.')

    # Step 2: insert territory row.
    now = datetime.now(timezone.utc).isoformat()
    try:
        ins = (supa.table('agent_territories_v3').insert({
            'agent_id':     user.id,
            'zip_code':     zip_code,
            'status':       'active',
            'activated_at': now,
        }).execute())
        if not ins.data:
            raise RuntimeError('insert returned no data')
    except Exception as e:
        # Roll back the profile assignment so the agent can retry.
        supa.table('agent_profiles_v3') \
            .update({'assigned_zip': None}) \
            .eq('id', user.id) \
            .execute()
        raise HTTPException(
            500,
            f'Failed to register territory; profile rolled back. {e}',
        )

    return {
        'zip_code':  zip_code,
        'claimed':   True,
        'activated_at': now,
    }


@router.get("/territory-status")
async def territory_status_endpoint(
    authorization: Optional[str] = Header(None),
):
    """
    Returns the territory grid annotated with status for the
    authenticated user. See module docstring for status semantics.
    """
    user = _user_from_authorization(authorization)
    profile = _load_profile(user.id)
    role = profile.get('role') or 'agent'
    my_zip = profile.get('assigned_zip')

    live = _live_zips()
    claims = _claims_map()

    def _buckets_for(z: dict) -> dict:
        """Per-bucket Contact Now counts, with the total summed for
        the popup header. None → 0 for any not-yet-populated ZIP."""
        probate  = z.get('contact_now_probate')  or 0
        divorce  = z.get('contact_now_divorce')  or 0
        trust    = z.get('contact_now_trust')    or 0
        llc      = z.get('contact_now_llc')      or 0
        absentee = z.get('contact_now_absentee') or 0
        tenure   = z.get('contact_now_tenure')   or 0
        # Cap each bucket display at 100 to match the briefing's per-bucket
        # cap — the agent works the top 100, the rest are watch list.
        # Total is the sum of caps, so a fully populated ZIP shows 600.
        def cap(n): return n if n < 100 else 100
        capped = {
            'probate':  cap(probate),
            'divorce':  cap(divorce),
            'trust':    cap(trust),
            'llc':      cap(llc),
            'absentee': cap(absentee),
            'tenure':   cap(tenure),
        }
        return {
            'contact_now_buckets':       capped,
            'contact_now_total':         sum(capped.values()),
            'contact_now_buckets_raw': {
                'probate':  probate,
                'divorce':  divorce,
                'trust':    trust,
                'llc':      llc,
                'absentee': absentee,
                'tenure':   tenure,
            },
        }

    zips_out = []
    for z in live:
        zip_code = z['zip_code']
        claim = claims.get(zip_code)
        bucket_fields = _buckets_for(z)

        if role == 'operator':
            # Operators see everyone's claims but don't claim themselves.
            status = 'claimed_by_other' if claim else 'available'
            entry = {
                'zip_code':                zip_code,
                'city':                    z.get('city'),
                'state':                   z.get('state'),
                'parcel_count':            z.get('parcel_count'),
                'current_call_now_count':  z.get('current_call_now_count') or 0,
                'status':                  status,
                **bucket_fields,
            }
            if claim:
                entry['claimed_by_name'] = claim['full_name']
            zips_out.append(entry)
        else:
            # Agent perspective.
            if zip_code == my_zip:
                status = 'mine'
            elif claim:
                status = 'claimed_by_other'
            else:
                status = 'available'
            entry = {
                'zip_code':                zip_code,
                'city':                    z.get('city'),
                'state':                   z.get('state'),
                'parcel_count':            z.get('parcel_count'),
                'current_call_now_count':  z.get('current_call_now_count') or 0,
                'status':                  status,
                **bucket_fields,
            }
            if status == 'claimed_by_other':
                entry['claimed_by_name'] = claim['full_name']
            zips_out.append(entry)

    # Stable order: by zip_code ascending.
    zips_out.sort(key=lambda e: e['zip_code'])

    return {
        'role':   role,
        'my_zip': my_zip,
        'zips':   zips_out,
    }
