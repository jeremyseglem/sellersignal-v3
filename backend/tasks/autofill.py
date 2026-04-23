"""
Autofill background task — continuously backfills case parties data.

The KC Superior Court portal is slow and transiently degrades, so full
coverage of the ~14,000 existing signals takes many hours of portal-available
wall-clock time. This task runs those backfill batches autonomously in the
background, without needing a human to poll Claude-in-chat.

Behavior:
  - Runs one backfill-parties batch (default 25 cases) every TICK_INTERVAL
    seconds.
  - Before each tick, checks portal health. If degraded, skips and sleeps.
  - On error, uses exponential backoff up to 30 min.
  - Tracks current offset internally; advances when a batch returns 0
    processed (meaning we've exhausted signals at that offset).
  - When offset exceeds max signal id, resets to 0 (picks up new signals
    added since last sweep, plus any cases that failed previously).
  - State exposed via /api/harvest/autofill-status for observability.
  - Can be paused/resumed via /api/harvest/autofill-pause|resume.

This task calls the existing HTTP endpoints via loopback (localhost:8000)
so the code path is identical to a human-triggered backfill.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────
TICK_INTERVAL     = int(os.environ.get("AUTOFILL_TICK_SECONDS", "180"))
BATCH_SIZE        = int(os.environ.get("AUTOFILL_BATCH_SIZE",   "10"))
OFFSET_STEP       = int(os.environ.get("AUTOFILL_OFFSET_STEP",  "500"))
BACKFILL_TIMEOUT  = int(os.environ.get("AUTOFILL_BACKFILL_TIMEOUT", "420"))
MAX_BACKOFF_SECS  = 1800
STARTUP_DELAY     = 45  # wait after boot before first tick

# Internal port the HTTP server listens on. Railway sets PORT env var.
LOCAL_PORT = int(os.environ.get("PORT", "8000"))
BASE_URL   = f"http://127.0.0.1:{LOCAL_PORT}"

# ── Shared state (read via /autofill-status) ──────────────────────────────
state: dict = {
    "enabled":              True,
    "started_at":           None,
    "last_tick_at":         None,
    "last_tick_result":     None,
    "current_offset":       0,
    "consecutive_errors":   0,
    "consecutive_empty":    0,   # ticks in a row returning 0 processed
    "backoff_until":        None,
    "total_ticks":          0,
    "total_processed":      0,
    "total_inserted":       0,
    "total_errors":         0,
    "full_sweeps_done":     0,
    "last_health_check":    None,
    "last_health_verdict":  None,
    "last_error":           None,       # str — most recent exception message
    "last_error_at":        None,       # ISO timestamp
    "config": {
        "tick_interval":  TICK_INTERVAL,
        "batch_size":     BATCH_SIZE,
        "offset_step":    OFFSET_STEP,
    },
}


async def _check_portal_health(client: httpx.AsyncClient, admin_key: str) -> bool:
    """Return True if KC portal is responding with real data."""
    try:
        r = await client.get(
            "/api/harvest/diag/portal-health",
            headers={"X-Admin-Key": admin_key},
            timeout=30,
        )
        data = r.json()
        healthy = bool(data.get("portal_healthy"))
        state["last_health_check"]   = datetime.now(timezone.utc).isoformat()
        state["last_health_verdict"] = "healthy" if healthy else "degraded"
        return healthy
    except Exception as e:
        log.warning(f"autofill health-check failed: {e}")
        state["last_health_verdict"] = f"error: {str(e)[:80]}"
        return False


async def _run_one_tick(client: httpx.AsyncClient, admin_key: str) -> dict:
    """Fire one backfill-parties batch and return the parsed result."""
    offset = state["current_offset"]
    r = await client.post(
        "/api/harvest/backfill-parties",
        params={
            "confirm": "true",
            "limit":   BATCH_SIZE,
            "offset":  offset,
        },
        headers={"X-Admin-Key": admin_key},
        timeout=BACKFILL_TIMEOUT,
    )
    # 200 with JSON body is the happy path. HTTP errors become exceptions.
    r.raise_for_status()
    return r.json()


async def _advance_offset_if_needed(result: dict) -> None:
    """If this batch processed nothing, bump the offset forward."""
    processed = result.get("processed", 0)
    if processed > 0:
        state["consecutive_empty"] = 0
        return

    state["consecutive_empty"] += 1
    # After one empty batch at the current offset, advance.
    state["current_offset"] += OFFSET_STEP

    # If we've advanced past the end of the signals table, do a full reset.
    # Signals count is loosely bounded — we use 20,000 as a safe cap that
    # covers current ~14,049 with headroom for future ingestion.
    if state["current_offset"] > 20000:
        log.info(
            f"autofill: offset {state['current_offset']} > 20000, "
            f"resetting to 0 (sweep #{state['full_sweeps_done'] + 1})"
        )
        state["current_offset"]   = 0
        state["full_sweeps_done"] += 1
        state["consecutive_empty"] = 0


async def autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        log.error(
            "autofill: ADMIN_KEY env var not set — disabling. "
            "Set ADMIN_KEY in Railway env to enable autofill."
        )
        state["enabled"] = False
        return

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"autofill: scheduled to tick every {TICK_INTERVAL}s, "
        f"batch size {BATCH_SIZE}, first tick in {STARTUP_DELAY}s"
    )
    await asyncio.sleep(STARTUP_DELAY)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        while True:
            try:
                # Respect pause flag
                if not state["enabled"]:
                    await asyncio.sleep(30)
                    continue

                # Respect backoff window
                if state["backoff_until"]:
                    now = datetime.now(timezone.utc)
                    try:
                        until = datetime.fromisoformat(state["backoff_until"])
                    except Exception:
                        until = now
                    if now < until:
                        await asyncio.sleep(30)
                        continue
                    state["backoff_until"] = None

                # Portal health gate
                if not await _check_portal_health(client, admin_key):
                    log.info("autofill: portal degraded, skipping this tick")
                    await asyncio.sleep(TICK_INTERVAL)
                    continue

                # Do the work
                result = await _run_one_tick(client, admin_key)
                await _advance_offset_if_needed(result)

                state["last_tick_at"]     = datetime.now(timezone.utc).isoformat()
                state["last_tick_result"] = {
                    "offset":             state["current_offset"],
                    "processed":          result.get("processed"),
                    "inserted_parties":   result.get("inserted_parties"),
                    "no_parties_found":   result.get("no_parties_found"),
                    "weeks_processed":    result.get("weeks_processed"),
                    "errors":             len(result.get("errors", []) or []),
                }
                state["total_ticks"]      += 1
                state["total_processed"]  += result.get("processed", 0) or 0
                state["total_inserted"]   += result.get("inserted_parties", 0) or 0
                state["consecutive_errors"] = 0

                log.info(
                    f"autofill tick #{state['total_ticks']}: "
                    f"offset={state['current_offset']} "
                    f"processed={result.get('processed')} "
                    f"parties={result.get('inserted_parties')}"
                )

                await asyncio.sleep(TICK_INTERVAL)

            except asyncio.CancelledError:
                log.info("autofill: loop cancelled (shutdown)")
                raise
            except Exception as e:
                state["consecutive_errors"] += 1
                state["total_errors"]       += 1
                state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
                state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
                log.error(
                    f"autofill tick failed "
                    f"(consecutive_errors={state['consecutive_errors']}): {e}"
                )
                backoff = min(
                    MAX_BACKOFF_SECS,
                    60 * (2 ** min(state["consecutive_errors"], 5)),
                )
                state["backoff_until"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=backoff)
                ).isoformat()
                await asyncio.sleep(60)
