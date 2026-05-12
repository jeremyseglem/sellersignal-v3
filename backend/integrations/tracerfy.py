"""
Tracerfy skip-trace integration.

This module is intentionally narrow: it knows how to call Tracerfy's
synchronous Instant Trace Lookup endpoint and return a normalized
result. It does not know about agents, parcels, caching, or the
monthly cap — those concerns live in backend/api/skip_trace.py.

The split exists so that swapping providers (BatchData, REISkip, etc.)
later means writing a new module here and changing one import in
skip_trace.py. The rest of the application stays unchanged.

Provider:    Tracerfy
Endpoint:    POST https://tracerfy.com/v1/api/trace/lookup/
Auth:        Authorization: Bearer <TRACERFY_API_TOKEN>
Cost:        5 credits per hit ($0.10 at $0.02/credit), 0 on miss
Rate limit:  500 requests/minute per account
Docs:        https://tracerfy.com/skip-tracing-api-documentation/

The response includes per-phone DNC flags and per-person litigator
flags, which the UI surfaces directly without a separate DNC scrub.
"""
from __future__ import annotations

import os
from typing import Any

import requests


# Hard-coded provider name used in cache rows and event_data. Stable
# across deploys — if Tracerfy is replaced, we keep this string in
# historical rows so analytics can distinguish old/new data.
PROVIDER_NAME = "tracerfy"

# Base URL and endpoint path. Easy to swap for a sandbox/test base
# later if Tracerfy publishes one.
_BASE_URL = "https://tracerfy.com"
_LOOKUP_PATH = "/v1/api/trace/lookup/"

# 15s timeout: Tracerfy's instant lookup advertises millisecond
# response times. 15s is generous enough that genuine slowness gets
# through but pathological hangs are bounded.
_HTTP_TIMEOUT_SEC = 15.0


class TracerfyError(Exception):
    """Raised when the Tracerfy API call fails for a non-recoverable
    reason. The caller turns this into a clean error response for the
    agent — it should not be silently swallowed.

    Attributes:
        message: human-readable error suitable for showing the agent
        status_code: HTTP status from Tracerfy, or None for network errors
        retryable: True if the agent could try again later (rate limit,
            transient network); False if the call should not be retried
            without changes (bad input, auth failure)
    """
    def __init__(self, message: str, *, status_code: int | None = None,
                 retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


def _get_api_token() -> str:
    """Pull the API token from environment. Raises if missing — the
    feature should not run at all without a configured token, and
    returning a generic error to the agent would mask the misconfig.
    """
    token = os.environ.get("TRACERFY_API_TOKEN", "").strip()
    if not token:
        raise TracerfyError(
            "Skip-trace is not configured on this deployment. "
            "Contact support.",
            retryable=False,
        )
    return token


def lookup_owner(
    address: str,
    city: str,
    state: str,
    zip_code: str | None = None,
) -> dict[str, Any]:
    """Look up the property owner(s) at the given address.

    This is the "find_owner: true" mode of the Tracerfy endpoint —
    we provide an address and Tracerfy returns whoever owns or lives
    there. We do not use the "find specific person" mode because our
    parcel data has owner names that may be outdated (PR's, trusts,
    etc.); the owner-finder gives Tracerfy the most freedom to find
    the current resident.

    Args:
        address: street address (e.g. "123 Main St")
        city:    city name
        state:   2-letter state code (e.g. "WA")
        zip_code: 5-digit ZIP. Optional but strongly recommended —
            Tracerfy's docs warn that without it, results may match a
            similarly-named property in the same city.

    Returns:
        A dict with the following shape:
          {
            'hit':              bool,
            'credits_deducted': int,
            'persons':          list of person dicts (may be empty),
            'provider':         'tracerfy',
            'raw':              the original Tracerfy response (for debugging),
          }

        Each person dict matches Tracerfy's schema:
          {
            'full_name': str, 'first_name': str, 'last_name': str,
            'dob': str | None, 'age': str | None,
            'deceased': bool, 'property_owner': bool, 'litigator': bool,
            'mailing_address': {'street', 'city', 'state', 'zip'},
            'phones': [{'number', 'type', 'dnc', 'carrier', 'rank'}, ...],
            'emails': [{'email', 'rank'}, ...],
          }

    Raises:
        TracerfyError: on auth failure, rate limit, invalid input,
            network error, or unexpected response shape.
    """
    token = _get_api_token()

    # Trim and validate inputs to catch obvious mistakes before
    # spending a credit. We do NOT enforce ZIP format because Tracerfy
    # accepts ZIP+4 and we shouldn't reject that.
    address = (address or "").strip()
    city = (city or "").strip()
    state = (state or "").strip().upper()
    zip_code = (zip_code or "").strip() or None

    if not address or not city or not state:
        raise TracerfyError(
            "Address, city, and state are required for skip-trace.",
            retryable=False,
        )
    if len(state) != 2:
        raise TracerfyError(
            f"State must be a 2-letter abbreviation; got '{state}'.",
            retryable=False,
        )

    body: dict[str, Any] = {
        "address":    address,
        "city":       city,
        "state":      state,
        "find_owner": True,
    }
    if zip_code:
        body["zip"] = zip_code

    url = _BASE_URL + _LOOKUP_PATH
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    try:
        resp = requests.post(url, json=body, headers=headers,
                             timeout=_HTTP_TIMEOUT_SEC)
    except requests.Timeout:
        raise TracerfyError(
            "Skip-trace timed out. Try again in a moment.",
            retryable=True,
        )
    except requests.RequestException as e:
        # Network-level error — DNS, connection refused, etc.
        raise TracerfyError(
            f"Skip-trace network error: {e}",
            retryable=True,
        )

    # Status-code handling. Order matters — auth failure is not
    # retryable, rate limit is, 5xx is.
    if resp.status_code == 401 or resp.status_code == 403:
        raise TracerfyError(
            "Skip-trace authentication failed. "
            "The API key is invalid or has been revoked.",
            status_code=resp.status_code,
            retryable=False,
        )
    if resp.status_code == 402:
        # Payment required — typically means credit balance exhausted.
        raise TracerfyError(
            "Skip-trace credit balance exhausted. Top up at tracerfy.com.",
            status_code=402,
            retryable=False,
        )
    if resp.status_code == 429:
        raise TracerfyError(
            "Skip-trace rate limit hit. Wait a minute and try again.",
            status_code=429,
            retryable=True,
        )
    if resp.status_code >= 500:
        raise TracerfyError(
            f"Skip-trace provider is having issues "
            f"(HTTP {resp.status_code}). Try again shortly.",
            status_code=resp.status_code,
            retryable=True,
        )
    if resp.status_code >= 400:
        # 400, 422, etc. — input problem. Surface Tracerfy's message
        # if it's JSON, otherwise fall back to a generic note.
        try:
            payload = resp.json()
            detail = payload.get("error") or payload.get("message") or resp.text
        except Exception:
            detail = resp.text[:200]
        raise TracerfyError(
            f"Skip-trace rejected the request: {detail}",
            status_code=resp.status_code,
            retryable=False,
        )

    # 200 — parse the body.
    try:
        data = resp.json()
    except Exception:
        raise TracerfyError(
            "Skip-trace returned an unexpected response.",
            retryable=True,
        )

    # Tracerfy guarantees `hit`, `persons_count`, `credits_deducted`,
    # and `persons` on a 200. Defensive: default each in case the
    # provider's schema drifts.
    hit = bool(data.get("hit"))
    credits = int(data.get("credits_deducted") or 0)
    persons = data.get("persons") or []

    return {
        "hit":              hit,
        "credits_deducted": credits,
        "persons":          persons,
        "provider":         PROVIDER_NAME,
        "raw":              data,
    }
