"""
Skip-trace API — agent-facing endpoints wrapping the Tracerfy provider
with caching, monthly cap, TCPA compliance ack, and event logging.

Policy in one place:

  1. Compliance gate.   Agent must have acknowledged TCPA/DNC
                        responsibility (one-time per account) before
                        any trace fires. /lookup returns 412 if not
                        ack'd; /status reports ack state to the UI.

  2. Cache.             30-day TTL keyed on (agent_id, pin). Hits
                        return immediately, do not call the provider,
                        and do not count against the cap. Misses
                        within the TTL also count as cache hits — no
                        re-trace of known-empty addresses for a month.

  3. Monthly cap.       50 fresh traces per agent per calendar month
                        (configurable via SKIP_TRACE_MONTHLY_CAP env
                        var). Cap counts FRESH calls only, not cache
                        hits. Cap resets at the start of each UTC month.

  4. Event log.         Every fresh trace logs a 'skip_traced' event
                        in lead_interactions_v3 with event_data
                        {provider, hit, credits_deducted, source}.
                        This keeps the skip-trace action visible in
                        the dossier history line and feeds the My
                        Leads list as engagement.

Endpoints:
  GET  /api/skip-trace/status              → ack state + monthly usage
  POST /api/skip-trace/ack-compliance      → record TCPA ack
  POST /api/skip-trace/lookup  {pin}       → run trace (cached or fresh)

The provider is imported as a module rather than passed as a
dependency. Swapping providers means changing the import statement
and the value of PROVIDER_NAME — no other code changes.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import user_from_authorization
from backend.api.db import get_supabase_client
from backend.integrations import tracerfy
from backend.integrations.tracerfy import TracerfyError


log = logging.getLogger(__name__)

router = APIRouter()


# Per-agent monthly cap on fresh traces. Cache hits do not count.
# Env-tunable so we can raise/lower without a deploy.
_MONTHLY_CAP = int(os.environ.get("SKIP_TRACE_MONTHLY_CAP", "50"))

# Current ack version. Bump and force re-ack only when the legal
# language we show changes materially.
_ACK_VERSION = "v1"


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════

def _utc_month_start() -> datetime:
    """Start of the current UTC calendar month, used for the cap query."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def _has_acked(supa, agent_id: str) -> bool:
    """True if this agent has a current ack on file."""
    res = (supa.table("skip_trace_compliance_acks_v3")
           .select("ack_version")
           .eq("agent_id", agent_id)
           .eq("ack_version", _ACK_VERSION)
           .limit(1)
           .execute())
    return bool(res.data)


def _count_fresh_this_month(supa, agent_id: str) -> int:
    """Count fresh (non-error) trace rows for this agent in the
    current UTC calendar month. Used for cap enforcement.

    Includes both hits and misses — Tracerfy charges 0 on miss, but
    a miss is still a fresh call we made, and the cap is about
    discouraging abuse, not just cost. Errored rows are excluded
    because the agent didn't get usable data.
    """
    month_start = _utc_month_start().isoformat()
    res = (supa.table("skip_trace_results_v3")
           .select("id", count="exact")
           .eq("agent_id", agent_id)
           .gte("created_at", month_start)
           .is_("error", "null")
           .execute())
    return int(res.count or 0)


def _is_operator(supa, agent_id: str) -> bool:
    """True if this user is a platform operator (Jeremy, Brian, etc.).
    Operators bypass the monthly skip-trace cap — they need unrestricted
    access for product validation, demos, and beta-agent support.

    Defaults to False on any failure: a missing profile or DB error
    falls through to standard agent treatment rather than silently
    handing out unlimited credits.
    """
    try:
        res = (supa.table("agent_profiles_v3")
               .select("role")
               .eq("id", agent_id)
               .limit(1)
               .execute())
        if res.data and res.data[0].get("role") == "operator":
            return True
    except Exception:
        pass
    return False


def _load_parcel(supa, pin: str) -> dict[str, Any] | None:
    """Load the address fields needed for a trace. Returns None if
    the pin doesn't exist in parcels_v3.
    """
    res = (supa.table("parcels_v3")
           .select("pin, zip_code, address, city, state")
           .eq("pin", pin)
           .limit(1)
           .execute())
    return res.data[0] if res.data else None


def _get_pr_for_pin(supa, pin: str) -> dict[str, str] | None:
    """For a probate parcel, return the Personal Representative's
    first/last name from court records. Returns None for non-probate
    parcels or probate cases where the PR isn't scraped yet.

    Path: parcels_v3.pin → raw_signal_matches_v3 → raw_signals_v3
    (document_ref = case_number) → case_parties_v3 (role='personal_
    representative'). Mirrors the enrichment logic in parcels.py
    around line 270.

    Returns {name_first, name_last, name_raw, classification} or None.
    """
    try:
        # Step 1: find any court-record matches on this pin
        matches_res = (supa.table("raw_signal_matches_v3")
                       .select("raw_signal_id")
                       .eq("pin", pin)
                       .execute())
        signal_ids = [m["raw_signal_id"] for m in (matches_res.data or [])]
        if not signal_ids:
            return None

        # Step 2: get document_ref (case_number) for KC court signals
        signals_res = (supa.table("raw_signals_v3")
                       .select("id, document_ref, source_type")
                       .in_("id", signal_ids)
                       .eq("source_type", "kc_superior_court")
                       .execute())
        case_numbers = [s["document_ref"] for s in (signals_res.data or [])
                        if s.get("document_ref")]
        if not case_numbers:
            return None

        # Step 3: find the PR row for any of those cases
        parties_res = (supa.table("case_parties_v3")
                       .select("name_raw, name_first, name_last, "
                               "pr_classification")
                       .in_("case_number", case_numbers)
                       .eq("role", "personal_representative")
                       .limit(1)
                       .execute())
        if not parties_res.data:
            return None

        p = parties_res.data[0]
        first = (p.get("name_first") or "").strip()
        last = (p.get("name_last") or "").strip()
        if not first or not last:
            # Name didn't parse cleanly — skip-trace can't use a
            # half-name. Falls through to owner-search.
            return None

        return {
            "name_first":     first,
            "name_last":      last,
            "name_raw":       p.get("name_raw"),
            "classification": p.get("pr_classification"),
        }
    except Exception:
        # Any DB hiccup here falls through to owner-search rather than
        # blocking the trace entirely.
        return None


def _cached_result_if_fresh(supa, agent_id: str, pin: str
                             ) -> dict[str, Any] | None:
    """Return the cached row for (agent, pin) if it exists and isn't
    expired. Returns None on cache miss OR expired row OR error row.

    Errored cache rows are treated as misses so the agent can retry
    immediately without waiting for the TTL.
    """
    res = (supa.table("skip_trace_results_v3")
           .select("*")
           .eq("agent_id", agent_id)
           .eq("pin", pin)
           .limit(1)
           .execute())
    if not res.data:
        return None
    row = res.data[0]

    # Errored row → treat as miss.
    if row.get("error"):
        return None

    # Expired? expires_at comes back as ISO string.
    expires_str = row.get("expires_at")
    if expires_str:
        try:
            expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if expires_at <= datetime.now(timezone.utc):
                return None
        except Exception:
            # Parse failure — treat as expired, safer to re-trace.
            return None

    return row


def _upsert_result(supa, agent_id: str, pin: str, zip_code: str,
                   *, hit: bool, credits_deducted: int,
                   persons: list[dict], error: Optional[str] = None
                   ) -> dict[str, Any]:
    """Insert or update the cache row for (agent, pin). Server-side
    triggers handle expires_at via the DEFAULT; we pass it explicitly
    on UPDATE to refresh the TTL on a fresh trace.

    Note: supabase-py's upsert with on_conflict relies on the UNIQUE
    constraint we set on (agent_id, pin) in migration 020.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    row = {
        "agent_id":         agent_id,
        "pin":              pin,
        "zip_code":         zip_code,
        "provider":         tracerfy.PROVIDER_NAME,
        "hit":              hit,
        "credits_deducted": credits_deducted,
        "persons":          persons,
        "error":            error,
        "created_at":       now.isoformat(),
        "expires_at":       expires.isoformat(),
    }
    res = (supa.table("skip_trace_results_v3")
           .upsert(row, on_conflict="agent_id,pin")
           .execute())
    if not res.data:
        # Upsert should always return the row on success.
        raise HTTPException(500, "Failed to cache skip-trace result")
    return res.data[0]


def _log_skip_traced_event(supa, agent_id: str, pin: str, zip_code: str,
                            *, hit: bool, credits_deducted: int,
                            source: str) -> None:
    """Log a 'skip_traced' interaction event so the action appears in
    the dossier history line and engages the lead for My Leads.

    source:    'fresh' for a real provider call, 'cache' for cache hits
    """
    try:
        supa.table("lead_interactions_v3").insert({
            "agent_id":   agent_id,
            "pin":        pin,
            "zip_code":   zip_code,
            "event_type": "skip_traced",
            "event_data": {
                "provider":         tracerfy.PROVIDER_NAME,
                "hit":              hit,
                "credits_deducted": credits_deducted,
                "source":           source,
            },
        }).execute()
    except Exception as e:
        # Event log failure is non-fatal — the trace itself succeeded
        # and the agent got their data. Log and move on.
        log.warning("skip_traced event log failed for %s: %s", pin, e)


# ════════════════════════════════════════════════════════════════════
#  Enhanced Skip Tracing helpers (async batch via Tracerfy webhook)
# ════════════════════════════════════════════════════════════════════

def _pr_in_persons(pr: dict[str, str],
                    persons: list[dict[str, Any]]) -> bool:
    """Check whether the named PR appears in a list of persons (from a
    standard Tracerfy result).

    Tolerant matching: case-insensitive, ignores middle names/initials.
    A PR named PARKER, JANICE matches "Janice Parker", "Janice M Parker",
    or "Janice Marie Parker" in Tracerfy's response.

    Used to decide whether to fire the more-expensive Enhanced batch
    follow-up. If the PR is already in the standard result, Enhanced
    would just duplicate work.
    """
    if not pr or not persons:
        return False
    pr_first = (pr.get("name_first") or "").strip().lower()
    pr_last = (pr.get("name_last") or "").strip().lower()
    if not pr_first or not pr_last:
        return False
    for p in persons:
        # Tracerfy returns first_name + last_name; some rows also have
        # a single 'full_name'. Check both.
        f = (p.get("first_name") or "").strip().lower()
        l = (p.get("last_name") or "").strip().lower()
        if f == pr_first and l == pr_last:
            return True
        full = (p.get("full_name") or "").strip().lower()
        if full and pr_first in full and pr_last in full:
            return True
    return False


def _mark_enhanced_submitted(supa, *, agent_id: str, pin: str,
                              queue_id: str) -> None:
    """Update the cache row to record an in-flight Enhanced batch."""
    try:
        (supa.table("skip_trace_results_v3")
            .update({
                "enhanced_pending":      True,
                "enhanced_queue_id":     queue_id,
                "enhanced_submitted_at": _utc_now_iso(),
                "enhanced_error":        None,
            })
            .eq("agent_id", agent_id)
            .eq("pin", pin)
            .execute())
    except Exception as e:
        # Non-fatal — the standard trace already succeeded. Log and
        # move on; the webhook will still arrive but won't find a
        # pending row to update. That's OK: we'll just log the orphan
        # in the webhook handler.
        log.warning("Could not mark enhanced submitted for %s: %s", pin, e)


def _mark_enhanced_error(supa, *, agent_id: str, pin: str,
                          error_msg: str) -> None:
    """Record a submission error on the cache row for diagnostics."""
    try:
        (supa.table("skip_trace_results_v3")
            .update({
                "enhanced_pending": False,
                "enhanced_error":   (error_msg or "")[:500],
            })
            .eq("agent_id", agent_id)
            .eq("pin", pin)
            .execute())
    except Exception as e:
        log.warning("Could not record enhanced error for %s: %s", pin, e)


def _utc_now_iso() -> str:
    """UTC timestamp in ISO format. Defined here so the helper file
    doesn't need to import datetime at the top scope."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ════════════════════════════════════════════════════════════════════
#  Tracerfy webhook handler
# ════════════════════════════════════════════════════════════════════
#
# Tracerfy POSTs to our webhook URL when a batch trace completes. The
# URL must be configured ONCE in the Tracerfy account dashboard. We
# protect it with a path-based secret token so unauthenticated callers
# can't fake completion events.
#
# Expected payload shape (per Tracerfy docs):
#   {
#     "id": 365,
#     "created_at": "2025-07-13T18:55:02.962332Z",
#     "pending": false,
#     "download_url": "https://tracerfy.nyc3.cdn.digitaloceanspaces.com/...csv",
#     "rows_uploaded": 1,
#     "credits_deducted": 15,
#     "queue_type": "api",
#     "trace_type": "enhanced",
#     "credits_per_lead": 15
#   }

_TRACERFY_WEBHOOK_SECRET = os.environ.get("TRACERFY_WEBHOOK_SECRET", "")


@router.post("/skip-trace/tracerfy-webhook/{secret}")
async def tracerfy_webhook(secret: str, payload: dict[str, Any]):
    """Receive completed Enhanced batch results from Tracerfy.

    Authentication: path-based secret. Tracerfy doesn't sign webhook
    requests, so we use a long random token in the URL path as a
    shared secret. The full webhook URL is configured once in the
    Tracerfy dashboard.

    Side effects:
      - Fetches the CSV from payload['download_url']
      - Parses the first row (we submit single-address batches)
      - Updates the matching skip_trace_results_v3 row by queue_id
      - Idempotent: re-delivery of the same queue_id is safe

    Returns:
      {"status": "ok"} on success
      {"status": "ignored"} if no matching cache row (orphan webhook)
      {"status": "auth_failed"} with 404 on wrong secret
    """
    # Path-secret auth. Return 404 (not 401) so probes can't tell
    # whether the endpoint exists.
    if not _TRACERFY_WEBHOOK_SECRET or secret != _TRACERFY_WEBHOOK_SECRET:
        raise HTTPException(404, "Not found")

    queue_id = str(payload.get("id") or payload.get("queue_id") or "")
    download_url = payload.get("download_url") or ""

    if not queue_id:
        log.warning("Tracerfy webhook missing queue id: %s", payload)
        return {"status": "ignored", "reason": "no_queue_id"}

    supa = get_supabase_client()
    if not supa:
        log.warning("Tracerfy webhook: Supabase unavailable")
        return {"status": "error", "reason": "supabase_unavailable"}

    # Locate the matching cache row by queue_id. There may be more
    # than one if the same address was traced for multiple agents,
    # but each row carries its own queue_id (unique per submission).
    try:
        rows = (supa.table("skip_trace_results_v3")
                  .select("*")
                  .eq("enhanced_queue_id", queue_id)
                  .execute()
                  .data or [])
    except Exception as e:
        log.warning("Webhook supabase lookup failed for queue %s: %s",
                    queue_id, e)
        return {"status": "error", "reason": "supabase_lookup_failed"}

    if not rows:
        # Orphan webhook — could be a re-delivery after we already
        # processed and cleared the row, or a submission we never
        # successfully recorded. Either way, 200 OK so Tracerfy
        # doesn't retry indefinitely.
        log.info("Tracerfy webhook for unknown queue %s — ignoring",
                 queue_id)
        return {"status": "ignored", "reason": "no_matching_row"}

    # Fetch and parse the results CSV
    try:
        csv_rows = tracerfy.fetch_enhanced_results(download_url)
    except tracerfy.TracerfyError as e:
        # Mark each pending row with the error so we don't leave them
        # spinning in the UI forever.
        for r in rows:
            try:
                (supa.table("skip_trace_results_v3")
                    .update({
                        "enhanced_pending":      False,
                        "enhanced_completed_at": _utc_now_iso(),
                        "enhanced_error":        f"CSV fetch/parse failed: {e.message}"[:500],
                    })
                    .eq("id", r["id"])
                    .execute())
            except Exception:
                pass
        return {"status": "error", "reason": "csv_fetch_failed"}

    if not csv_rows:
        # Tracerfy returned an empty CSV — the trace completed but
        # found no data. Mark the row complete with empty enhanced_data
        # so the UI stops the "searching..." banner.
        for r in rows:
            (supa.table("skip_trace_results_v3")
                .update({
                    "enhanced_pending":      False,
                    "enhanced_completed_at": _utc_now_iso(),
                    "enhanced_data":         {},
                })
                .eq("id", r["id"])
                .execute())
        return {"status": "ok", "rows_updated": len(rows), "data": "empty"}

    # Single-address batch → single CSV row
    parsed = tracerfy.parse_enhanced_row(csv_rows[0])

    for r in rows:
        try:
            (supa.table("skip_trace_results_v3")
                .update({
                    "enhanced_pending":      False,
                    "enhanced_completed_at": _utc_now_iso(),
                    "enhanced_data":         parsed,
                    "enhanced_error":        None,
                })
                .eq("id", r["id"])
                .execute())
        except Exception as e:
            log.warning("Webhook update failed for row %s: %s",
                        r.get("id"), e)

    return {"status": "ok", "rows_updated": len(rows),
            "relatives_found": len(parsed.get("relatives") or [])}


# ════════════════════════════════════════════════════════════════════
#  Status endpoint — ack state + monthly usage
# ════════════════════════════════════════════════════════════════════

@router.get("/skip-trace/status")
async def status(authorization: Optional[str] = Header(None)):
    """Return the agent's current skip-trace eligibility:
      {
        acked:              bool,
        ack_version:        str,
        monthly_used:       int,
        monthly_cap:        int | null,    # null = unlimited (operators)
        monthly_remaining:  int | null,    # null = unlimited
        monthly_resets_at:  ISO datetime (start of next UTC month),
        is_operator:        bool,
      }

    Operators (Jeremy, Brian, etc.) have no cap — they need
    unrestricted access for demos, product validation, and helping
    beta agents. The UI shows "unlimited" rather than a counter for
    these users.

    The UI reads this on dossier mount to know whether to show the
    TCPA modal or proceed straight to the skip-trace button.
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase unavailable")

    acked = _has_acked(supa, user.id)
    is_op = _is_operator(supa, user.id)
    used = _count_fresh_this_month(supa, user.id)

    # Start of next month for the reset hint
    month_start = _utc_month_start()
    if month_start.month == 12:
        next_reset = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_reset = month_start.replace(month=month_start.month + 1)

    return {
        "acked":             acked,
        "ack_version":       _ACK_VERSION,
        "monthly_used":      used,
        "monthly_cap":       None if is_op else _MONTHLY_CAP,
        "monthly_remaining": None if is_op else max(0, _MONTHLY_CAP - used),
        "monthly_resets_at": next_reset.isoformat(),
        "is_operator":       is_op,
    }


# ════════════════════════════════════════════════════════════════════
#  Ack endpoint — record TCPA acknowledgment
# ════════════════════════════════════════════════════════════════════

@router.post("/skip-trace/ack-compliance")
async def ack_compliance(authorization: Optional[str] = Header(None)):
    """Record this agent's one-time TCPA / DNC acknowledgment.

    Idempotent: re-acking returns the existing row rather than
    erroring. Returns {acked: true, ack_version, acked_at}.
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase unavailable")

    row = {
        "agent_id":    user.id,
        "ack_version": _ACK_VERSION,
    }
    try:
        res = supa.table("skip_trace_compliance_acks_v3").insert(row).execute()
        if res.data:
            return {
                "acked":       True,
                "ack_version": _ACK_VERSION,
                "acked_at":    res.data[0].get("acked_at"),
            }
    except Exception as e:
        # UNIQUE violation = already ack'd. Return success.
        msg = str(e).lower()
        if "duplicate key" in msg or "23505" in msg or "unique" in msg:
            existing = (supa.table("skip_trace_compliance_acks_v3")
                        .select("acked_at, ack_version")
                        .eq("agent_id", user.id)
                        .limit(1)
                        .execute())
            if existing.data:
                return {
                    "acked":       True,
                    "ack_version": existing.data[0].get("ack_version"),
                    "acked_at":    existing.data[0].get("acked_at"),
                }
        raise HTTPException(400, f"Failed to record acknowledgment: {e}")

    raise HTTPException(500, "Unexpected ack state")


# ════════════════════════════════════════════════════════════════════
#  Cached endpoint — pure read of existing cache, no provider call
# ════════════════════════════════════════════════════════════════════

@router.get("/skip-trace/cached/{pin}")
async def cached(pin: str,
                  authorization: Optional[str] = Header(None)):
    """Return the cached skip-trace result for this (agent, pin), if
    one exists and is unexpired. Returns null if no cache.

    Unlike /lookup, this endpoint:
      - Never calls the provider (zero cost, never spends credits)
      - Never logs a skip_traced event (the agent didn't take an action,
        they just re-opened a dossier)
      - Does not require TCPA ack — if data is already cached, the
        agent already ack'd at the time of original trace
      - Does not enforce the monthly cap

    The frontend calls this on dossier mount to show any existing
    cached result without making the agent click "Find owner contact
    info" again.

    Response (cache present):
      {
        cached:           true,
        source:           'cache',
        hit:              bool,
        persons:          [...],
        retrieved_at:     ISO datetime,
        expires_at:       ISO datetime,
      }

    Response (no cache or expired):
      {cached: false}
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase unavailable")

    row = _cached_result_if_fresh(supa, user.id, pin)
    if not row:
        return {"cached": False}

    return {
        "cached":           True,
        "source":           "cache",
        "hit":              row["hit"],
        "persons":          row["persons"] or [],
        "retrieved_at":     row["created_at"],
        "expires_at":       row["expires_at"],
        # Enhanced data — present once the async Tracerfy batch webhook
        # has fired. Frontend shows the "Family decision-makers"
        # section when enhanced_data is non-null and non-empty.
        "enhanced_pending": _enhanced_still_pending(row),
        "enhanced_data":    row.get("enhanced_data"),
    }


def _enhanced_still_pending(row: dict[str, Any]) -> bool:
    """True if Enhanced was submitted but the webhook hasn't fired yet
    AND we're within the expected wait window. After 30 min we treat
    the submission as silently failed and stop showing the spinner.
    """
    if not row.get("enhanced_pending"):
        return False
    submitted = row.get("enhanced_submitted_at")
    if not submitted:
        return False
    try:
        from datetime import datetime, timezone, timedelta
        ts = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ts
        return age < timedelta(minutes=30)
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
#  Lookup endpoint — the actual trace
# ════════════════════════════════════════════════════════════════════

class LookupRequest(BaseModel):
    pin: str = Field(..., min_length=1, max_length=64)
    # When true, bypass the 30-day cache and run a fresh provider
    # call. Wired to the "Refresh" link in the dossier panel — agents
    # who think their cached data is stale (number changed, person
    # moved) can force a re-trace. Costs the same as a normal fresh
    # trace and counts against the monthly cap.
    force_refresh: bool = False


@router.post("/skip-trace/lookup")
async def lookup(payload: LookupRequest,
                  authorization: Optional[str] = Header(None)):
    """Run a skip-trace on the parcel identified by `pin`.

    Flow:
      1. Verify agent ack'd TCPA → 412 if not
      2. Check cache (30-day TTL) → return cached if fresh
         (UNLESS payload.force_refresh is true)
      3. Check monthly cap → 429 if at limit
      4. Load parcel address from parcels_v3 → 404 if missing
      5. Call Tracerfy (PR-name search for probate, owner search else)
      6. Upsert result into cache
      7. Log skip_traced event
      8. Return result
    """
    user = user_from_authorization(authorization)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Supabase unavailable")

    pin = payload.pin

    # ── Step 1: ack gate ────────────────────────────────────────────
    if not _has_acked(supa, user.id):
        raise HTTPException(
            status_code=412,
            detail={
                "code": "compliance_not_acked",
                "message": "TCPA/DNC acknowledgment required before "
                           "running skip-trace.",
            },
        )

    # ── Step 2: cache check (skipped when force_refresh) ──────────
    if not payload.force_refresh:
        cached = _cached_result_if_fresh(supa, user.id, pin)
        if cached:
            # Log a cache-hit event so engagement still flows to My Leads,
            # but skip the cap and skip the provider call.
            zip_code = cached.get("zip_code") or ""
            _log_skip_traced_event(
                supa, user.id, pin, zip_code,
                hit=bool(cached["hit"]),
                credits_deducted=0,  # 0 because we didn't call the provider
                source="cache",
            )
            is_op_cache = _is_operator(supa, user.id)
            used = _count_fresh_this_month(supa, user.id)
            return {
                "source":           "cache",
                "hit":              cached["hit"],
                "credits_deducted": 0,
                "persons":          cached["persons"] or [],
                "retrieved_at":     cached["created_at"],
                "expires_at":       cached["expires_at"],
                "monthly_used":     used,
                "monthly_cap":      None if is_op_cache else _MONTHLY_CAP,
                "enhanced_pending": _enhanced_still_pending(cached),
                "enhanced_data":    cached.get("enhanced_data"),
            }

    # ── Step 3: monthly cap ────────────────────────────────────────
    # Operators (Jeremy, Brian, etc.) are exempt from the cap.
    is_op = _is_operator(supa, user.id)
    used = _count_fresh_this_month(supa, user.id)
    if not is_op and used >= _MONTHLY_CAP:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "monthly_cap_reached",
                "message": f"Skip-trace monthly limit reached "
                           f"({used}/{_MONTHLY_CAP}). Resets at the "
                           f"start of next month.",
                "monthly_used": used,
                "monthly_cap":  _MONTHLY_CAP,
            },
        )

    # ── Step 4: load parcel address ────────────────────────────────
    parcel = _load_parcel(supa, pin)
    if not parcel:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "parcel_not_found",
                "message": f"Parcel {pin} not found.",
            },
        )
    address = (parcel.get("address") or "").strip()
    city    = (parcel.get("city") or "").strip()
    state   = (parcel.get("state") or "").strip()
    zip_code = (parcel.get("zip_code") or "").strip()
    if not address or not city or not state:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "parcel_address_incomplete",
                "message": "Parcel is missing address, city, or state — "
                           "skip-trace cannot run.",
            },
        )

    # ── Step 5: call Tracerfy ──────────────────────────────────────
    # For probate leads with a known PR, search by the PR's name —
    # not by find_owner. The property's owner-of-record in skip-trace
    # data is typically the deceased homeowner, which is useless for
    # contacting the actual decision-maker. The PR's name from court
    # records is the right query.
    pr = _get_pr_for_pin(supa, pin)
    try:
        if pr:
            provider_result = tracerfy.lookup_person(
                first_name=pr["name_first"],
                last_name=pr["name_last"],
                address=address, city=city, state=state, zip_code=zip_code,
            )

            # ── Household fallback ──────────────────────────────────
            # If the PR-name search missed, the PR likely doesn't live
            # at the property — common when the PR is an adult child
            # living elsewhere. Retry with find_owner=true to find
            # anyone else at the address (typically the surviving
            # spouse or other family members at the home). They are
            # NOT the decision-maker, but a handwritten letter often
            # gets forwarded by household members to the PR.
            #
            # Filter out anyone flagged deceased — that removes the
            # dead homeowner who would otherwise dominate results in
            # a probate context. Each remaining person is tagged with
            # _household_fallback=True so the UI can render the
            # "household contact, not PR directly" framing.
            #
            # Credits: lookup_person miss costs 0; lookup_owner hit
            # costs 5. Net cost per probate-fallback that finds a
            # household member: 5 credits. Misses on both: 0 credits.
            if not provider_result["hit"]:
                fallback_result = tracerfy.lookup_owner(
                    address=address, city=city, state=state, zip_code=zip_code,
                )
                household = [
                    p for p in (fallback_result.get("persons") or [])
                    if not p.get("deceased")
                ]
                if household:
                    for p in household:
                        p["_household_fallback"] = True
                    provider_result = {
                        "hit":              True,
                        "credits_deducted": (
                            provider_result.get("credits_deducted", 0)
                            + fallback_result.get("credits_deducted", 0)
                        ),
                        "persons":     household,
                        "provider":    fallback_result.get("provider"),
                        "search_mode": "household_fallback",
                        "raw": {
                            "primary":  provider_result.get("raw"),
                            "fallback": fallback_result.get("raw"),
                        },
                    }
                else:
                    # Owner-search also returned nothing usable.
                    # Aggregate credits but keep the hit=False so the
                    # frontend renders the probate-specific miss
                    # message ("PR not at this address, likely lives
                    # elsewhere").
                    provider_result["credits_deducted"] = (
                        provider_result.get("credits_deducted", 0)
                        + fallback_result.get("credits_deducted", 0)
                    )
        else:
            provider_result = tracerfy.lookup_owner(
                address=address, city=city, state=state, zip_code=zip_code,
            )
    except TracerfyError as e:
        # Record the error in the cache so we can see the pattern later
        # via analytics. Errored rows DO NOT count against the cap and
        # DO NOT block immediate retries (see _cached_result_if_fresh).
        _upsert_result(
            supa, user.id, pin, zip_code,
            hit=False, credits_deducted=0, persons=[], error=e.message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code":      "provider_error",
                "message":   e.message,
                "retryable": e.retryable,
            },
        )

    # ── Step 6: cache the result ───────────────────────────────────
    cached_row = _upsert_result(
        supa, user.id, pin, zip_code,
        hit=provider_result["hit"],
        credits_deducted=provider_result["credits_deducted"],
        persons=provider_result["persons"],
    )

    # ── Step 6.5: Enhanced Skip Tracing follow-up ──────────────────
    # If this is a probate lead with a known PR, and the standard
    # synchronous trace did NOT return the PR, fire an async Enhanced
    # batch job. Enhanced ($0.30/hit) returns up to 8 relatives — one
    # of whom is often the PR who lives at a different address. The
    # result arrives via webhook 5-30 min later and updates this same
    # cache row.
    #
    # We only spend the extra credits when:
    #   - probate lead (pr is not None — only probate has PRs)
    #   - PR is not already in the standard result (no need to spend
    #     more if we already have their contact info)
    enhanced_pending = False
    if pr and not _pr_in_persons(pr, provider_result.get("persons") or []):
        try:
            batch = tracerfy.submit_enhanced_batch(
                address=address, city=city, state=state, zip_code=zip_code,
                first_name=pr["name_first"], last_name=pr["name_last"],
            )
            _mark_enhanced_submitted(
                supa, agent_id=user.id, pin=pin,
                queue_id=batch["queue_id"],
            )
            enhanced_pending = True
        except tracerfy.TracerfyError as e:
            # Enhanced submission failed — log but do not surface to
            # agent. The standard trace already returned successfully,
            # and the agent shouldn't be confused by a partial failure.
            # The cache row stays without enhanced_pending=true, so
            # the frontend just doesn't show the "searching for
            # relatives" banner.
            _mark_enhanced_error(
                supa, agent_id=user.id, pin=pin, error_msg=e.message,
            )

    # ── Step 7: log skip_traced event ──────────────────────────────
    _log_skip_traced_event(
        supa, user.id, pin, zip_code,
        hit=provider_result["hit"],
        credits_deducted=provider_result["credits_deducted"],
        source="fresh",
    )

    # ── Step 8: return ─────────────────────────────────────────────
    used_after = used + 1
    return {
        "source":           "fresh",
        "hit":              provider_result["hit"],
        "credits_deducted": provider_result["credits_deducted"],
        "persons":          provider_result["persons"],
        "retrieved_at":     cached_row["created_at"],
        "expires_at":       cached_row["expires_at"],
        "monthly_used":     used_after,
        "monthly_cap":      None if is_op else _MONTHLY_CAP,
        "search_mode":      provider_result.get("search_mode"),
        "searched_for":     (f"{pr['name_first']} {pr['name_last']}"
                             if pr else None),
        "enhanced_pending": enhanced_pending,
    }
