"""
backend/tasks/letter_scheduler.py — background task that fires scheduled
letters at their stannp_send_date.

Lob's API has a native send_date parameter — you could submit all 6 letters
of a sequence at once and Lob would queue and dispatch on schedule. Stannp
has no equivalent: every create_letter call prints + dispatches within 1-2
business days. To preserve the 6-letter campaign behavior (0/30/60/90/135/
180-day cadence), letters 2-6 of a sequence are stored in letters_sent_v3
with status='scheduled', stannp_send_date set to the target send date, and
stannp_letter_id NULL.

This task runs on a tick (default every 6 hours) and:
  1. Queries letters_sent_v3 for rows where status='scheduled',
     stannp_letter_id IS NULL, and stannp_send_date <= NOW().
  2. For each row, reads the snapshot rendered_html, converts to PDF via
     WeasyPrint, and submits to Stannp's /letters/create endpoint.
  3. On success: updates the row with stannp_letter_id, status='created',
     stannp_tracking_url.
  4. On failure: logs and leaves the row for the next tick to retry. After
     MAX_RETRIES failed attempts (tracked via the new fail_count column,
     bumped each failure), marks the row 'failed'.

Cancelled rows (status='cancelled', set by the cancel-sequence endpoint
when a scheduled letter is cancelled before being sent) are not picked up
by the scheduler — the WHERE clause filters them out.

State and pause/resume controls follow the autofill.py pattern:
  GET  /api/letters/scheduler/status
  POST /api/letters/scheduler/pause
  POST /api/letters/scheduler/resume
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from backend.api.db import get_supabase_client
from backend.services.stannp_client import (
    get_client as get_stannp_client,
    StannpAddressError,
    StannpAuthError,
    StannpConfigError,
    StannpError,
)
from backend.services.letter_pdf_renderer import render_html_to_pdf


log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

# How often the scheduler ticks. Letters are scheduled at day-granularity
# (30/60/90/135/180), so hourly is overkill — every 6 hours is enough.
TICK_INTERVAL = int(os.environ.get("LETTER_SCHEDULER_TICK_SECONDS", str(6 * 3600)))

# How many letters to process per tick. Keep small — each one does an
# HTML→PDF render + Stannp HTTP call. At our scale (few sequences active
# at any one due-date moment) 25 is plenty.
BATCH_SIZE = int(os.environ.get("LETTER_SCHEDULER_BATCH_SIZE", "25"))

# Max retry attempts before marking a row 'failed'. After this many ticks
# in which the same row failed, give up and stop attempting.
MAX_RETRIES = int(os.environ.get("LETTER_SCHEDULER_MAX_RETRIES", "5"))

# Delay after server startup before the first tick fires. Lets the rest
# of the app fully boot first (DB pools, WeasyPrint native libs, etc.).
STARTUP_DELAY = int(os.environ.get("LETTER_SCHEDULER_STARTUP_DELAY", "60"))


# ── Shared state (mirrors autofill.py pattern) ────────────────────────────

state: dict[str, Any] = {
    "enabled":             True,
    "started_at":          None,
    "last_tick_at":        None,
    "last_tick_result":    None,
    "consecutive_errors":  0,
    "total_ticks":         0,
    "total_letters_sent":  0,
    "total_errors":        0,
    "last_error":          None,
    "last_error_at":       None,
    "config": {
        "tick_interval":  TICK_INTERVAL,
        "batch_size":     BATCH_SIZE,
        "max_retries":    MAX_RETRIES,
    },
}


# ── Per-tick logic ────────────────────────────────────────────────────────


def _fetch_due_rows(supa, limit: int) -> list[dict[str, Any]]:
    """
    Return scheduled letters whose stannp_send_date has arrived (or passed)
    and which haven't already been submitted to Stannp.

    Ordering by stannp_send_date ASC so the oldest-due letters go first —
    if the scheduler has been paused for a while, this fires the catch-up
    in chronological order.

    The fail_count gate is permissive (NULL OR < MAX_RETRIES) so legacy rows
    that don't have fail_count yet still get picked up. After the column is
    populated, retries are capped.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    resp = (
        supa.table("letters_sent_v3")
        .select(
            "id, agent_id, pin, zip_code, sequence_id, letter_index, "
            "rendered_html, recipient_name, recipient_line1, recipient_line2, "
            "recipient_city, recipient_state, recipient_zip, "
            "stannp_send_date, fail_count"
        )
        .eq("status", "scheduled")
        .is_("stannp_letter_id", "null")
        .lte("stannp_send_date", now_iso)
        .order("stannp_send_date", desc=False)
        .limit(limit)
        .execute()
    )
    rows = (resp.data if resp else None) or []
    # Filter out rows past retry limit at app-level (Supabase doesn't
    # support OR-with-null in a clean way in the chain we're using).
    return [
        r for r in rows
        if (r.get("fail_count") or 0) < MAX_RETRIES
    ]


def _send_one(row: dict[str, Any]) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Attempt to submit one scheduled letter to Stannp. Returns:
        (success, error_message_or_None, stannp_response_or_None)

    On success the caller updates the row with stannp_letter_id + status.
    On failure the caller bumps fail_count and leaves status='scheduled'
    so the next tick retries — unless fail_count hits MAX_RETRIES.
    """
    html = row.get("rendered_html")
    if not html:
        return False, "Missing rendered_html snapshot", None

    try:
        pdf_bytes = render_html_to_pdf(html)
    except RuntimeError as e:
        return False, f"PDF render failed: {e}", None

    recipient = {
        "lastname":  row.get("recipient_name")  or "Property Owner",
        "address1":  row.get("recipient_line1") or "",
        "city":      row.get("recipient_city")  or "",
        "state":     row.get("recipient_state") or "WA",
        "zipcode":   row.get("recipient_zip")   or "",
        "country":   "US",
    }
    if row.get("recipient_line2"):
        recipient["address2"] = row["recipient_line2"]

    if not recipient["address1"]:
        return False, "Missing recipient address line 1", None

    sequence_id = row.get("sequence_id")
    letter_index = row.get("letter_index")
    idem_key = f"ss-sched-{sequence_id}-{letter_index}" if sequence_id else f"ss-sched-{row['id']}"

    try:
        client = get_stannp_client()
        stannp_letter = client.create_letter(
            pdf_bytes=pdf_bytes,
            recipient=recipient,
            first_class=True,
            tags=f"seq-{sequence_id},letter-{letter_index},pin-{row.get('pin')}",
            idempotency_key=idem_key,
            post_unverified=False,
        )
        return True, None, stannp_letter
    except StannpAddressError as e:
        return False, f"Address validation failed: {e}", None
    except (StannpAuthError, StannpConfigError) as e:
        return False, f"Stannp config error: {e}", None
    except StannpError as e:
        return False, f"Stannp error: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {type(e).__name__}: {e}", None


def _update_row_success(supa, row_id: str, stannp_letter: dict, stannp_mode: str) -> None:
    """Update a scheduled row after a successful Stannp send."""
    supa.table("letters_sent_v3").update({
        "stannp_letter_id":    str(stannp_letter.get("id")),
        "stannp_mode":         stannp_mode,
        "stannp_tracking_url": stannp_letter.get("pdf"),
        "status":              "created",
        "status_updated_at":   datetime.now(timezone.utc).isoformat(),
    }).eq("id", row_id).execute()


def _update_row_failure(supa, row_id: str, error_msg: str, current_fail_count: int) -> None:
    """
    Increment fail_count and possibly mark the row 'failed' if we've hit
    the retry ceiling. Leaves status='scheduled' for retries below the cap.
    """
    new_fail_count = current_fail_count + 1
    update: dict[str, Any] = {
        "fail_count":   new_fail_count,
        "fail_reason":  error_msg[:500],  # truncate just in case
        "last_failed_at": datetime.now(timezone.utc).isoformat(),
    }
    if new_fail_count >= MAX_RETRIES:
        update["status"]     = "failed"
        update["failed_at"]  = datetime.now(timezone.utc).isoformat()
    supa.table("letters_sent_v3").update(update).eq("id", row_id).execute()


async def _run_one_tick() -> dict[str, Any]:
    """
    One scheduler pass: fetch due rows, send each, update status.
    Returns a result dict for state observability.
    """
    supa = get_supabase_client()
    if not supa:
        return {"ok": False, "error": "Supabase client unavailable", "processed": 0}

    try:
        rows = _fetch_due_rows(supa, BATCH_SIZE)
    except Exception as e:
        log.exception("letter scheduler: failed to fetch due rows")
        return {"ok": False, "error": str(e), "processed": 0}

    if not rows:
        return {"ok": True, "processed": 0, "sent": 0, "failed": 0}

    log.info("letter scheduler: %d letters due for send", len(rows))

    # Resolve mode once per tick — same client instance for all sends.
    try:
        client_mode = get_stannp_client().mode
    except StannpConfigError as e:
        log.error("letter scheduler: Stannp not configured: %s", e)
        return {"ok": False, "error": f"Stannp config: {e}", "processed": 0}

    sent_count = 0
    failed_count = 0

    for row in rows:
        row_id = row["id"]
        fail_count = int(row.get("fail_count") or 0)

        success, error_msg, stannp_letter = _send_one(row)
        if success and stannp_letter:
            try:
                _update_row_success(supa, row_id, stannp_letter, client_mode)
                sent_count += 1
                log.info(
                    "letter scheduler: sent row=%s seq=%s idx=%s stannp_id=%s",
                    row_id, row.get("sequence_id"), row.get("letter_index"),
                    stannp_letter.get("id"),
                )
            except Exception as e:
                log.error(
                    "letter scheduler: Stannp sent letter %s but row update failed: %s",
                    stannp_letter.get("id"), e,
                )
                # Don't bump fail_count — the letter went out.
        else:
            failed_count += 1
            log.warning(
                "letter scheduler: failed row=%s seq=%s idx=%s err=%s (attempt %d/%d)",
                row_id, row.get("sequence_id"), row.get("letter_index"),
                error_msg, fail_count + 1, MAX_RETRIES,
            )
            try:
                _update_row_failure(supa, row_id, error_msg or "unknown", fail_count)
            except Exception as e:
                log.error("letter scheduler: failed-row update itself failed: %s", e)

    return {
        "ok": True,
        "processed": len(rows),
        "sent": sent_count,
        "failed": failed_count,
    }


# ── Task loop ─────────────────────────────────────────────────────────────


async def _scheduler_loop() -> None:
    """The actual async task. Started by the lifespan in backend/main.py."""
    state["started_at"] = datetime.now(timezone.utc).isoformat()

    # Wait for the rest of the app to settle before the first tick.
    await asyncio.sleep(STARTUP_DELAY)

    while True:
        if not state["enabled"]:
            await asyncio.sleep(30)
            continue

        try:
            result = await _run_one_tick()
            state["last_tick_at"]     = datetime.now(timezone.utc).isoformat()
            state["last_tick_result"] = result
            state["total_ticks"]     += 1
            if result.get("ok"):
                state["consecutive_errors"] = 0
                state["total_letters_sent"] += result.get("sent", 0)
                state["total_errors"]       += result.get("failed", 0)
            else:
                state["consecutive_errors"] += 1
                state["total_errors"]       += 1
                state["last_error"]    = result.get("error")
                state["last_error_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            log.exception("letter scheduler tick raised")
            state["consecutive_errors"] += 1
            state["total_errors"]       += 1
            state["last_error"]    = f"{type(e).__name__}: {e}"
            state["last_error_at"] = datetime.now(timezone.utc).isoformat()

        # Sleep until next tick. Errors don't extend the interval — Stannp
        # outages are uncommon enough that we don't need backoff here.
        await asyncio.sleep(TICK_INTERVAL)


# Public entry — backend/main.py lifespan calls this once at startup.
_task: Optional[asyncio.Task] = None


def start() -> None:
    """Spawn the scheduler task. Idempotent — safe to call multiple times."""
    global _task
    if _task and not _task.done():
        return
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_scheduler_loop(), name="letter_scheduler")
    log.info("letter scheduler task started")


def get_state() -> dict[str, Any]:
    """Snapshot for the status admin endpoint."""
    return dict(state)


def pause() -> None:
    state["enabled"] = False
    log.info("letter scheduler paused")


def resume() -> None:
    state["enabled"] = True
    log.info("letter scheduler resumed")
