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

Resilience (added 2026-05-18 after sign-in outage):
  The Supabase client shares one HTTP/2 connection across all
  callers — including batch background tasks that periodically
  exhaust the stream pool. When that happens, a brand-new sign-in
  request fails with RemoteProtocolError / ReadError / Broken pipe
  even though the JWT is perfectly valid. To prevent these
  transport blips from being visible as auth failures, the
  verification call retries once on connection-layer errors.
  Real auth failures (bad token, expired session) raise on the
  first attempt without retry.
"""
import logging
import time
from typing import Optional

from fastapi import HTTPException

from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

# Substrings that mark a connection-layer error worth retrying. These
# are not auth failures — they're transport issues where the HTTP/2
# stream got dropped mid-request. A retry on a fresh stream typically
# succeeds within ~50-200ms.
_TRANSIENT_MARKERS = (
    "RemoteProtocolError",
    "ConnectionTerminated",
    "Server disconnected",
    "Broken pipe",
    "ReadError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "Connection reset",
)

# Sleep between retry attempts. Short enough not to hurt sign-in
# latency on the rare retry; long enough for httpx to recycle the
# underlying HTTP/2 stream pool.
_RETRY_BACKOFF_SECS = 0.25


def _is_transient(exc: Exception) -> bool:
    """True if the exception looks like a recoverable transport error."""
    msg = f"{type(exc).__name__}: {exc}"
    return any(m in msg for m in _TRANSIENT_MARKERS)


def user_from_authorization(authorization: Optional[str]):
    """Verify a Bearer JWT and return the authenticated user.

    Raises HTTPException with one of:
      401 — header is missing, malformed, or fails verification
      503 — Supabase client is unavailable

    Returns the Supabase auth user object (has .id, .email, etc.)
    on success.

    On transient connection errors (Supabase HTTP/2 stream pool
    blips) automatically retries once before surfacing a 401.
    """
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Missing or malformed Authorization header')
    token = authorization.split(' ', 1)[1].strip()
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, 'Supabase unavailable')

    last_exc: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            result = supa.auth.get_user(token)
            user = getattr(result, 'user', None)
            if user is None:
                # Not a transport error — the token resolved but produced
                # no user. Don't retry; it's a real auth failure.
                raise HTTPException(401, 'Invalid session')
            return user
        except HTTPException:
            raise
        except Exception as e:
            last_exc = e
            if attempt == 1 and _is_transient(e):
                log.info(
                    f"user_from_authorization: transient error on attempt 1, "
                    f"retrying: {type(e).__name__}: {e}"
                )
                time.sleep(_RETRY_BACKOFF_SECS)
                continue
            # Non-transient on first attempt, or transient that's already
            # been retried — surface as 401.
            break

    raise HTTPException(401, f'Auth verification failed: {last_exc}')
