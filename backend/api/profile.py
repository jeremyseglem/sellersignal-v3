"""
Agent profile API.

  GET  /api/profile          — current agent's profile (requires auth)
  PUT  /api/profile          — update fields on the current agent's profile
  GET  /api/profile/by-zip/:zip — public lookup of who owns a ZIP (just
                                  full_name + brokerage; used by the
                                  territories grid to show 'claimed by
                                  Jeremy Seglem')

Authentication is via the Bearer token in the Authorization header.
The frontend sends the Supabase Auth session's access_token; this
module verifies it via supabase.auth.get_user(token) and pulls the
profile row keyed on user.id.

Profile row creation happens server-side on signup via the
create_agent_profile_on_signup trigger (see schema/010_agent_profiles.sql).
This endpoint never inserts; it only reads and updates.
"""
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api.db import get_supabase_client


router = APIRouter()


# ── Auth helper ─────────────────────────────────────────────────
# Pulls the current user from a 'Authorization: Bearer <jwt>' header.
# Returns the user dict or raises 401. Cached by the supabase client
# internally so calling this repeatedly inside one request is cheap.

def _user_from_authorization(authorization: Optional[str]):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Missing or malformed Authorization header')
    token = authorization.split(' ', 1)[1].strip()
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')
    try:
        result = supa.auth.get_user(token)
    except Exception as e:
        raise HTTPException(401, f'Auth verification failed: {e}')
    user = getattr(result, 'user', None)
    if user is None:
        raise HTTPException(401, 'Invalid session')
    return user


# ── Models ──────────────────────────────────────────────────────
# Request body for PUT /api/profile. Every field is optional; only
# fields the client actually sends get updated, leaving the rest
# untouched. This keeps the form forgiving — a partial save during
# onboarding doesn't blow away other fields.

class ProfileUpdate(BaseModel):
    full_name:      Optional[str] = None
    phone:          Optional[str] = None
    brokerage:      Optional[str] = None
    license_number: Optional[str] = None
    license_state:  Optional[str] = None
    headshot_url:   Optional[str] = None
    signature_url:  Optional[str] = None
    logo_url:       Optional[str] = None
    onboarding_completed_at: Optional[str] = None  # ISO timestamp


# ── Endpoints ───────────────────────────────────────────────────

@router.get("")
async def get_profile(authorization: Optional[str] = Header(None)):
    """Return the current agent's profile row.

    The row is created automatically by the create_agent_profile_on_signup
    trigger when a user first signs up via Supabase Auth, so this
    endpoint always finds a row for an authenticated user.
    """
    user = _user_from_authorization(authorization)
    supa = get_supabase_client()
    res = (supa.table('agent_profiles_v3')
           .select('*')
           .eq('id', user.id)
           .limit(1)
           .execute())
    rows = res.data or []
    if not rows:
        # Trigger should have created this. If we're here something
        # broke during signup — return a stub so the UI still renders
        # rather than 404'ing.
        return {
            'id':    user.id,
            'email': getattr(user, 'email', None),
        }
    return rows[0]


@router.put("")
async def update_profile(
    body: ProfileUpdate,
    authorization: Optional[str] = Header(None),
):
    """Patch the current agent's profile. Only fields present in the
    request body are updated.
    """
    user = _user_from_authorization(authorization)
    supa = get_supabase_client()

    payload = body.model_dump(exclude_unset=True)
    if not payload:
        # No-op update — return current row unchanged.
        return await get_profile(authorization=authorization)

    res = (supa.table('agent_profiles_v3')
           .update(payload)
           .eq('id', user.id)
           .execute())
    rows = res.data or []
    if not rows:
        raise HTTPException(404, 'Profile not found')
    return rows[0]


@router.get("/by-zip/{zip_code}")
async def get_profile_by_zip(zip_code: str):
    """Public lookup: who claims this ZIP? Returns just the public
    fields (full_name, brokerage) so the territories grid can show
    'Claimed by Jeremy Seglem · The Agency'. Returns null when no
    agent has claimed the ZIP.

    No auth required — agents need to see who has neighboring
    territories to understand the market.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')
    res = (supa.table('agent_profiles_v3')
           .select('full_name, brokerage')
           .eq('assigned_zip', zip_code)
           .limit(1)
           .execute())
    rows = res.data or []
    if not rows:
        return {'claimed': False}
    return {'claimed': True, **rows[0]}
