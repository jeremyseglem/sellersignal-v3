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

    Uses Tracerfy's find_owner=true mode: returns whoever owns or
    lives at this address. Good for non-probate leads (obit,
    divorce, treasury) where the target IS the property owner.

    For probate leads where the target is the named Personal
    Representative (who often doesn't live at the property), use
    lookup_person() instead with the PR's name from court records.
    """
    return _do_lookup(
        address=address, city=city, state=state, zip_code=zip_code,
        find_owner=True,
        first_name=None, last_name=None,
    )


def lookup_person(
    first_name: str,
    last_name: str,
    address: str,
    city: str,
    state: str,
    zip_code: str | None = None,
) -> dict[str, Any]:
    """Look up a specific named person associated with an address.

    Uses Tracerfy's find_owner=false mode. The first_name/last_name
    pair is required by the API. Tracerfy searches for someone
    matching the name at this address. If the named person isn't
    associated with this address (e.g., a probate PR who lives in
    another state), the result will be a miss — no fallback to
    owner-search is performed here, because that would double-charge
    credits silently. The caller decides whether to retry differently.

    Address is required even when the target person doesn't live
    there — Tracerfy uses it as a search anchor.
    """
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    if not first_name or not last_name:
        raise TracerfyError(
            "First name and last name are required for person lookup.",
            retryable=False,
        )
    return _do_lookup(
        address=address, city=city, state=state, zip_code=zip_code,
        find_owner=False,
        first_name=first_name, last_name=last_name,
    )


def _do_lookup(
    *,
    address: str,
    city: str,
    state: str,
    zip_code: str | None,
    find_owner: bool,
    first_name: str | None,
    last_name: str | None,
) -> dict[str, Any]:
    """Shared implementation for both lookup_owner() and lookup_person().

    Args:
        address: street address (e.g. "123 Main St")
        city:    city name
        state:   2-letter state code (e.g. "WA")
        zip_code: 5-digit ZIP. Optional but strongly recommended —
            Tracerfy's docs warn that without it, results may match a
            similarly-named property in the same city.
        find_owner: True for owner search, False for person search.
        first_name, last_name: required when find_owner=False.

    Returns:
        A dict with the following shape:
          {
            'hit':              bool,
            'credits_deducted': int,
            'persons':          list of person dicts (may be empty),
            'provider':         'tracerfy',
            'search_mode':      'owner' or 'person',
            'raw':              the original Tracerfy response (for debugging),
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
        "find_owner": find_owner,
    }
    if zip_code:
        body["zip"] = zip_code
    if not find_owner:
        body["first_name"] = first_name
        body["last_name"] = last_name

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
        "search_mode":      "owner" if find_owner else "person",
        "raw":              data,
    }
