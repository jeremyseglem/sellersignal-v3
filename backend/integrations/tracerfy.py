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
# Batch endpoint for async Enhanced Skip Tracing. Unlike the
# synchronous lookup endpoint, this one queues the job and delivers
# results via webhook (configured in the Tracerfy dashboard, fires to
# our /api/skip-trace/tracerfy-webhook handler).
_BATCH_PATH = "/v1/api/trace/"

# Tracerfy rate limit: 10 batch POSTs per 5-minute window per account.
# We're far below this in practice, but worth noting if we ever need
# to throttle.

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


def submit_enhanced_batch(
    address: str,
    city: str,
    state: str,
    zip_code: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    """Submit a single-address Enhanced Skip Tracing batch job.

    Tracerfy's instant-lookup endpoint silently ignores the trace_type
    parameter (we confirmed this experimentally on 2026-05-12). The
    Enhanced tier — which returns up to 8 relatives with contact info,
    5 aliases, 5 past addresses — is only available via the async
    batch endpoint POST /v1/api/trace/.

    Flow:
      1. This function POSTs the address as a single-row JSON batch
         with trace_type='enhanced'
      2. Tracerfy queues the job and returns immediately with
         {id, estimated_wait_seconds, ...}
      3. We store that id (queue_id) on the cache row
      4. 5-30 minutes later, Tracerfy POSTs the completed result to
         the webhook URL configured in their dashboard
      5. Webhook handler fetches the CSV from download_url, parses
         relatives, updates the cache row

    Args:
        address, city, state, zip_code: property address
        first_name, last_name: optional. Pass the named PR from court
            records so Tracerfy's enrichment can focus on them and
            their relatives.

    Returns:
        {
          'queue_id':                str,    # use this in webhook lookup
          'estimated_wait_seconds':  int | None,
          'credits_estimated':       int,    # what Tracerfy expects to charge
          'raw':                     dict,   # full response for debugging
        }

    Raises:
        TracerfyError on submission failure (auth, rate limit, etc.).
        Does NOT raise on successful queue submission — the job is
        considered submitted as soon as we have a queue_id.
    """
    token = _get_api_token()

    address = (address or "").strip()
    city = (city or "").strip()
    state = (state or "").strip().upper()
    zip_code = (zip_code or "").strip() or None
    first_name = (first_name or "").strip() or None
    last_name = (last_name or "").strip() or None

    if not address or not city or not state:
        raise TracerfyError(
            "Address, city, and state are required for Enhanced trace.",
            retryable=False,
        )

    # Batch endpoint requires multipart/form-data with a CSV file +
    # column-mapping form fields. The sync /lookup endpoint accepts
    # JSON, but the batch /trace/ endpoint does not — we confirmed
    # this experimentally on 2026-05-13: posting application/json
    # returned 'Unsupported media type "application/json"'.
    #
    # CSV body has a header row + a single data row for this single-
    # address submission. The column_* form fields tell Tracerfy
    # which CSV columns are which fields.
    import csv
    import io
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["address", "city", "state", "zip",
                     "first_name", "last_name"])
    writer.writerow([address, city, state, zip_code or "",
                     first_name or "", last_name or ""])
    csv_content = csv_buf.getvalue()

    files = {
        # Tracerfy expects the CSV under the 'csv_file' field name
        # (confirmed via API error response on 2026-05-13). The
        # alternative is a 'json_data' form field with JSON-encoded
        # rows — we use csv_file for clarity.
        "csv_file": ("enhanced_trace.csv", csv_content, "text/csv"),
    }
    form_data = {
        "trace_type":         "enhanced",
        "address_column":     "address",
        "city_column":        "city",
        "state_column":       "state",
        "zip_column":         "zip",
        "first_name_column":  "first_name",
        "last_name_column":   "last_name",
    }

    url = _BASE_URL + _BATCH_PATH
    headers = {
        # Note: do NOT set Content-Type here — requests sets the
        # multipart boundary automatically when `files=` is used.
        # Manually setting Content-Type breaks the boundary.
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.post(url, files=files, data=form_data,
                             headers=headers, timeout=_HTTP_TIMEOUT_SEC)
    except requests.Timeout:
        raise TracerfyError(
            "Enhanced trace submission timed out. Try again.",
            retryable=True,
        )
    except requests.RequestException as e:
        raise TracerfyError(
            f"Enhanced trace network error: {e}",
            retryable=True,
        )

    if resp.status_code == 401 or resp.status_code == 403:
        raise TracerfyError(
            "Skip-trace authentication failed.",
            status_code=resp.status_code,
            retryable=False,
        )
    if resp.status_code == 402:
        raise TracerfyError(
            "Skip-trace credit balance insufficient for Enhanced trace.",
            status_code=402,
            retryable=False,
        )
    if resp.status_code == 429:
        raise TracerfyError(
            "Enhanced trace rate limit hit (10 batch POSTs per 5 min).",
            status_code=429,
            retryable=True,
        )
    if resp.status_code >= 500:
        raise TracerfyError(
            f"Tracerfy is having issues (HTTP {resp.status_code}).",
            status_code=resp.status_code,
            retryable=True,
        )
    if resp.status_code >= 400:
        try:
            payload = resp.json()
            detail = payload.get("error") or payload.get("message") or resp.text
        except Exception:
            detail = resp.text[:200]
        raise TracerfyError(
            f"Enhanced trace rejected: {detail}",
            status_code=resp.status_code,
            retryable=False,
        )

    try:
        data = resp.json()
    except Exception:
        raise TracerfyError(
            "Tracerfy batch endpoint returned an unexpected response.",
            retryable=True,
        )

    # Per Tracerfy docs the queue response includes `id`,
    # `estimated_wait_seconds`, and `pending=true`. Use defensive
    # gets in case the schema drifts.
    queue_id = data.get("id")
    if queue_id is None:
        # Some payloads use queue_id directly. Try both.
        queue_id = data.get("queue_id")
    if queue_id is None:
        raise TracerfyError(
            f"Enhanced trace submission returned no queue id. "
            f"Response keys: {list(data.keys())}",
            retryable=False,
        )

    return {
        "queue_id":               str(queue_id),
        "estimated_wait_seconds": data.get("estimated_wait_seconds"),
        "credits_estimated":      data.get("credits_estimated") or 15,
        "raw":                    data,
    }


def fetch_enhanced_results(download_url: str) -> list[dict[str, Any]]:
    """Fetch and parse the completed-batch CSV that Tracerfy posts on
    webhook completion. Returns one dict per row in the CSV.

    The CSV columns for Enhanced traces include the standard fields
    (phones_1 through phones_8, emails_1 through emails_5, etc.) PLUS
    Enhanced-specific columns for relatives, aliases, past addresses.

    We don't know the exact column names until we see a real Enhanced
    completion in production. This function parses defensively:
    returns the raw row dict, and the caller (webhook handler) handles
    interpretation.

    Raises TracerfyError on fetch failure or non-CSV response.
    """
    if not download_url:
        raise TracerfyError(
            "No download URL in webhook payload.",
            retryable=False,
        )

    try:
        resp = requests.get(download_url, timeout=30.0)
    except requests.RequestException as e:
        raise TracerfyError(
            f"Failed to fetch Enhanced results CSV: {e}",
            retryable=True,
        )

    if resp.status_code != 200:
        raise TracerfyError(
            f"Enhanced results CSV returned HTTP {resp.status_code}",
            retryable=resp.status_code >= 500,
        )

    # Parse CSV defensively. csv.DictReader handles quoting and headers.
    import csv
    import io
    rows: list[dict[str, Any]] = []
    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            rows.append(dict(row))
    except Exception as e:
        raise TracerfyError(
            f"Could not parse Enhanced results CSV: {e}",
            retryable=False,
        )

    return rows


def parse_enhanced_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one row of the Enhanced CSV into our internal shape.

    Defensive parsing: Tracerfy may add or remove columns over time.
    Keys not present in the row are skipped, not errored on. The shape
    here is what the frontend expects in skip_trace_results_v3.enhanced_data.

    Output:
      {
        "owner": {"first_name", "last_name", "age", "phones", "emails"},
        "relatives":      [{"name", "relationship", "age",
                            "phones", "emails", "city", "state"}, ...],
        "aliases":        [str, ...],
        "past_addresses": [{"street", "city", "state", "zip"}, ...],
      }

    Tracerfy CSV column naming pattern (inferred from their normal-tier
    output we already see): suffixed numbers like phones_1, phones_2,
    emails_1, relatives_1_name, relatives_1_phone, etc. We'll discover
    the exact column names from the first real webhook delivery and
    log unknown columns for follow-up.
    """
    def collect_indexed(prefix: str, max_n: int = 10) -> list[str]:
        """Pull out values for keys like prefix_1, prefix_2, ...
        Skips empty/null values."""
        out = []
        for i in range(1, max_n + 1):
            v = (row.get(f"{prefix}_{i}") or "").strip()
            if v and v.lower() not in ("none", "null", "n/a"):
                out.append(v)
        return out

    # Owner-level fields (the named person, or the property owner)
    owner = {
        "first_name": (row.get("first_name") or "").strip(),
        "last_name":  (row.get("last_name") or "").strip(),
        "age":        (row.get("age") or "").strip() or None,
        "phones":     collect_indexed("phone", 8),
        "emails":     collect_indexed("email", 5),
    }

    # Relatives: Tracerfy may use relatives_1_name + relatives_1_phone
    # OR a single relatives_1 column with combined data. Try both.
    relatives: list[dict[str, Any]] = []
    for i in range(1, 9):  # up to 8 relatives per Enhanced spec
        rel_name = (row.get(f"relative_{i}_name")
                    or row.get(f"relatives_{i}_name")
                    or row.get(f"relative_{i}")
                    or "").strip()
        if not rel_name:
            continue
        relatives.append({
            "name":         rel_name,
            "relationship": (row.get(f"relative_{i}_relationship")
                             or row.get(f"relatives_{i}_relationship")
                             or "").strip() or None,
            "age":          (row.get(f"relative_{i}_age")
                             or row.get(f"relatives_{i}_age")
                             or "").strip() or None,
            "phone":        (row.get(f"relative_{i}_phone")
                             or row.get(f"relatives_{i}_phone")
                             or "").strip() or None,
            "email":        (row.get(f"relative_{i}_email")
                             or row.get(f"relatives_{i}_email")
                             or "").strip() or None,
            "city":         (row.get(f"relative_{i}_city")
                             or row.get(f"relatives_{i}_city")
                             or "").strip() or None,
            "state":        (row.get(f"relative_{i}_state")
                             or row.get(f"relatives_{i}_state")
                             or "").strip() or None,
        })

    # Aliases: list of past names
    aliases = collect_indexed("alias", 5)

    # Past addresses: variable column names. Try standard variants.
    past_addresses: list[dict[str, str]] = []
    for i in range(1, 6):  # up to 5 past addresses
        street = (row.get(f"past_address_{i}_street")
                  or row.get(f"prior_address_{i}_street")
                  or row.get(f"past_address_{i}")
                  or "").strip()
        if not street:
            continue
        past_addresses.append({
            "street": street,
            "city":   (row.get(f"past_address_{i}_city")
                       or row.get(f"prior_address_{i}_city")
                       or "").strip(),
            "state":  (row.get(f"past_address_{i}_state")
                       or row.get(f"prior_address_{i}_state")
                       or "").strip(),
            "zip":    (row.get(f"past_address_{i}_zip")
                       or row.get(f"prior_address_{i}_zip")
                       or "").strip(),
        })

    return {
        "owner":          owner,
        "relatives":      relatives,
        "aliases":        aliases,
        "past_addresses": past_addresses,
        # Keep the raw row so we can debug column-naming surprises
        # without re-parsing later.
        "_raw_csv_row":   row,
    }


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

    Note: this is for the SYNCHRONOUS endpoint only (5-credit standard
    trace). The trace_type parameter is silently ignored by this
    endpoint — we confirmed experimentally that 'enhanced', 'advanced',
    and even invalid values all produce identical 5-credit results.
    For Enhanced Skip Tracing (15 credits, with relatives), use
    submit_enhanced_batch() instead, which targets the async batch
    endpoint.

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
