"""
Shared authentication helper for the SellerSignal API.

Lifted out of api/profile.py so multiple routers can import
the same JWT-verification logic without duplicating it. The
function signature and behavior are unchanged from the original
implementation in profile.py — that file now imports from here.

  user_from_authorization(authorization: Optional[str]) -> User

Pulls the current user from an 'Authorization: Bearer <jwt>'
header. Returns the user object or raises FastAPI HTTPException
(401 missing/invalid, 503 if Supabase is unreachable).

Verifies the token via supabase.auth.get_user(token). The
Supabase client caches verifications internally for the duration
of a request, so calling this multiple times within one
request handler is cheap.
"""
from typing import Optional
from fastapi import HTTPException

from backend.api.db import get_supabase_client


def user_from_authorization(authorization: Optional[str]):
    """Verify a Bearer JWT and return the authenticated user.

    Raises HTTPException with one of:
      401 — header is missing, malformed, or fails verification
      503 — Supabase client is unavailable

    Returns the Supabase auth user object (has .id, .email, etc.)
    on success.
    """
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
