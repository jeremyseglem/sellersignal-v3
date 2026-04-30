"""
Rematch autofill background task — drains the unmatched-signals queue
in small chunks, regardless of HTTP request lifecycles.

Why this exists:
  process_unmatched is too slow to finish in one HTTP request when there
  are thousands of signals to chew through (the owners_db load alone
  takes ~50 seconds, and per-signal matching adds ~0.5s each). Railway's
  HTTP timeout is 10 minutes; processing 14k+ signals in one shot would
  need ~1-2 hours.

  This background task wakes up every TICK_INTERVAL seconds, calls
  process_unmatched(max_batches=N) for one bounded chunk, then sleeps.
  Each tick processes ~200-500 signals. Over 30-90 minutes, the queue
  drains. No HTTP request is involved — the matcher runs directly
  in-process, so timeouts don't apply.

Behavior:
  - First tick fires REMATCH_STARTUP_DELAY seconds after boot (default 30s).
  - Each tick processes up to (BATCH_SIZE * MAX_BATCHES) signals.
  - When signals_remaining drops to 0, the task sleeps for IDLE_INTERVAL
    instead of TICK_INTERVAL (default 1 hour vs 60 sec) until something
    creates new unmatched signals (e.g. a fresh harvest, another
    /rematch-reset call).
  - State exposed via /api/harvest/rematch-autofill-status.

Unlike obit_autofill and treasury_autofill, this task does NOT call back
to its own HTTP API. It imports backend.harvesters.matcher.process_unmatched
directly and calls it in-process. This avoids the HTTP timeout problem
that motivated this task in the first place.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────

# How long between active ticks (when there are still unmatched signals).
TICK_INTERVAL = int(os.environ.get("REMATCH_AUTOFILL_TICK_SECONDS", "60"))

# How long between idle polls (when the queue is drained — we still
# wake up periodically to check whether anything new appeared).
IDLE_INTERVAL = int(os.environ.get("REMATCH_AUTOFILL_IDLE_SECONDS", "3600"))

# How many signals to process per tick. Inner matcher batch x batches.
BATCH_SIZE   = int(os.environ.get("REMATCH_AUTOFILL_BATCH_SIZE", "100"))
MAX_BATCHES  = int(os.environ.get("REMATCH_AUTOFILL_MAX_BATCHES", "3"))

# First-tick delay. Lets the rest of the app finish booting.
REMATCH_STARTUP_DELAY = int(
    os.environ.get("REMATCH_AUTOFILL_STARTUP_DELAY", "30")
)

# ZIP scoping. Empty string -> None means "all covered ZIPs."
_ZIP_FILTER_RAW = os.environ.get("REMATCH_AUTOFILL_ZIP_FILTER", "").strip()
ZIP_FILTER: Optional[str] = _ZIP_FILTER_RAW or None

MAX_BACKOFF_SECS = 1800

# ── Shared state ──────────────────────────────────────────────────────────
state: dict = {
    "enabled":              True,
    "started_at":           None,
    "last_tick_at":         None,
    "last_tick_result":     None,
    "consecutive_errors":   0,
    "backoff_until":        None,
    "total_ticks":          0,
    "total_processed":      0,
    "total_matched":        0,
    "total_errors":         0,
    "last_error":           None,
    "last_error_at":        None,
    "signals_remaining":    None,  # unmatched count after most recent tick
    "config": {
        "tick_interval":    TICK_INTERVAL,
        "idle_interval":    IDLE_INTERVAL,
        "batch_size":       BATCH_SIZE,
        "max_batches":      MAX_BATCHES,
        "zip_filter":       ZIP_FILTER,
    },
}


def _count_unmatched(supa) -> int:
    """How many signals currently have matched_at IS NULL."""
    try:
        res = (supa.table('raw_signals_v3')
               .select('id', count='exact')
               .is_('matched_at', 'null')
               .execute())
        return res.count or 0
    except Exception as e:
        log.warning(f"rematch_autofill: count query failed: {e}")
        return -1


async def _trigger_coverage_refresh() -> None:
    """
    Hit the local /api/coverage/refresh-counts endpoint to update
    zip_coverage_v3.current_call_now_count for every live ZIP. Called
    after a rematch finishes so the territories list page shows fresh
    counts without manual intervention.

    Best-effort. Logs failures but never raises.
    """
    import httpx
    admin_key  = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        log.info("_trigger_coverage_refresh: no ADMIN_KEY, skipping")
        return
    local_port = int(os.environ.get("PORT", "8000"))
    base_url   = f"http://127.0.0.1:{local_port}"
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
        r = await client.post(
            "/api/coverage/refresh-counts",
            params={'confirm': 'true'},
            headers={'X-Admin-Key': admin_key},
        )
        r.raise_for_status()
        body = r.json()
        log.info(
            f"coverage-counts refreshed: targets={body.get('targets')} "
            f"updated={body.get('updated')}"
        )


async def rematch_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    # Lazy imports so module load doesn't fail in test harnesses
    from backend.api.db import get_supabase_client
    from backend.harvesters import matcher as M

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"rematch_autofill: tick every {TICK_INTERVAL}s, "
        f"idle every {IDLE_INTERVAL}s, "
        f"batch_size={BATCH_SIZE} x max_batches={MAX_BATCHES} "
        f"(~{BATCH_SIZE * MAX_BATCHES} signals/tick), "
        f"zip_filter={ZIP_FILTER}, first tick in {REMATCH_STARTUP_DELAY}s"
    )
    await asyncio.sleep(REMATCH_STARTUP_DELAY)

    while True:
        try:
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

            supa = get_supabase_client()
            if supa is None:
                log.warning("rematch_autofill: supa client unavailable, sleeping")
                await asyncio.sleep(60)
                continue

            unmatched_before = _count_unmatched(supa)
            if unmatched_before == 0:
                # Nothing to do. Idle poll.
                state["signals_remaining"] = 0
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            # Run the matcher in-process. No HTTP, no timeout.
            # process_unmatched is sync, so wrap in a thread to avoid
            # blocking the asyncio loop (which is also handling other
            # background tasks and the FastAPI request loop).
            stats = await asyncio.to_thread(
                M.process_unmatched,
                supa,
                ZIP_FILTER,
                BATCH_SIZE,
                MAX_BATCHES,
            )

            unmatched_after = _count_unmatched(supa)

            processed = (stats or {}).get("processed", 0) or 0
            matched   = (stats or {}).get("matched", 0) or 0
            errors    = (stats or {}).get("errors", []) or []

            state["last_tick_at"]     = datetime.now(timezone.utc).isoformat()
            state["last_tick_result"] = {
                "processed":          processed,
                "matched":            matched,
                "by_type":            (stats or {}).get("by_type", {}),
                "errors":             len(errors),
                "unmatched_before":   unmatched_before,
                "unmatched_after":    unmatched_after,
            }
            state["total_ticks"]      += 1
            state["total_processed"]  += processed
            state["total_matched"]    += matched
            state["signals_remaining"] = unmatched_after
            state["consecutive_errors"] = 0

            log.info(
                f"rematch_autofill tick #{state['total_ticks']}: "
                f"processed={processed} matched={matched} "
                f"remaining={unmatched_after} (was {unmatched_before})"
            )

            # If matches were produced AND the queue has fully drained
            # this tick, trigger a coverage-counts refresh so the
            # territories list page reflects the new totals. (We skip
            # this on every tick because it makes 11 briefing-builder
            # round trips and we don't want to do that 50+ times during
            # a big rematch.) The refresh is best-effort; failures are
            # logged but don't disrupt the rematch loop.
            if matched > 0 and unmatched_after == 0:
                try:
                    await _trigger_coverage_refresh()
                except Exception as e:
                    log.warning(f"coverage-counts refresh failed: {e}")

            # Active or idle sleep based on whether the queue is drained.
            sleep_for = IDLE_INTERVAL if unmatched_after == 0 else TICK_INTERVAL
            await asyncio.sleep(sleep_for)

        except asyncio.CancelledError:
            log.info("rematch_autofill: loop cancelled (shutdown)")
            raise
        except Exception as e:
            state["consecutive_errors"] += 1
            state["total_errors"]       += 1
            state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
            state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
            log.exception(
                f"rematch_autofill tick failed "
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
