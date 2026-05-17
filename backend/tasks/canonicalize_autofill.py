"""
Canonicalize autofill background task — completes deferred and partial
owner_canonical_v3 work without manual orchestrator re-triggers.

Why this exists:
  The onboarding orchestrator (backend/tasks/zip_onboarding.py) serializes
  the canonicalize step via _CANONICALIZE_LOCK so only one ZIP canonicalizes
  at a time per Railway instance. When multiple ZIPs are onboarded close
  together (the 2026-05-17 5-ZIP batch is the canonical case), the second
  through Nth ZIPs land in live_canonicalize_pending — they're fully live
  for Build Now, but their canon work is parked behind the lock.

  Without this task, completing those ZIPs requires an operator to
  manually re-fire onboard-zip on each one in sequence. At any meaningful
  scale (multi-county expansion) that's untenable.

  This task wakes up on a tick interval, looks for ZIPs that need canon
  work, and runs backfill_zip on one of them — using the same lock the
  orchestrator uses, so canon-vs-canon serialization stays correct.

Behavior:
  - First tick fires STARTUP_DELAY seconds after boot (default 60s).
  - Each tick checks _CANONICALIZE_LOCK; if held by an active onboarding,
    skips and sleeps.
  - Two-tier ZIP picking:
      Priority 1: any ZIP in orchestrator state live_canonicalize_pending
                  or live_canonicalize_failed (explicit knowledge of work).
                  Cleared first.
      Priority 2: round-robin sweep across all live ZIPs (handles
                  drift — newly-seeded parcels in already-live ZIPs).
  - If nothing to do anywhere, sleeps IDLE_INTERVAL.
  - On error, exponential backoff up to 30 min.
  - State exposed via /api/harvest/canonicalize-autofill-status.
  - Can be paused/resumed via /api/harvest/canonicalize-autofill-{pause,resume}.

Wall-clock expectations:
  - Per-tick when a ZIP has pending canon: minutes to hours depending on
    how many pending parcels (a fresh 15k-parcel ZIP at concurrency=3
    takes ~2 hours).
  - Per-tick when no work: ~30 seconds of DB scanning, then sleeps
    IDLE_INTERVAL.

Unlike obit_autofill and treasury_autofill, this task does NOT call back
to its own HTTP API — it imports backfill_zip directly and runs it
in-process via asyncio.to_thread (backfill_zip is synchronous).
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────

# How long between active ticks (after processing a ZIP with pending work).
TICK_INTERVAL = int(os.environ.get(
    "CANONICALIZE_AUTOFILL_TICK_SECONDS", "300"  # 5 minutes
))

# How long between idle polls (when no ZIP has any pending work).
IDLE_INTERVAL = int(os.environ.get(
    "CANONICALIZE_AUTOFILL_IDLE_SECONDS", "3600"  # 1 hour
))

# Concurrency for the Haiku 4.5 calls inside backfill_zip. Matches the
# value zip_onboarding uses; raising this can saturate the Supabase HTTP/2
# stream pool and cause cascading failures (we learned this empirically
# 2026-05-17 — see the orchestrator commit message).
CONCURRENCY = int(os.environ.get(
    "CANONICALIZE_AUTOFILL_CONCURRENCY", "3"
))

# First-tick delay. Lets the rest of the app finish booting cleanly.
STARTUP_DELAY = int(os.environ.get(
    "CANONICALIZE_AUTOFILL_STARTUP_DELAY", "60"
))

# Master enable. Set to "false" in Railway env to disable on boot.
ENABLED_DEFAULT = os.environ.get(
    "CANONICALIZE_AUTOFILL_ENABLED", "true"
).lower() == "true"

MAX_BACKOFF_SECS = 1800

# ── Shared state (read via /canonicalize-autofill-status) ─────────────────

state: dict = {
    "enabled":              ENABLED_DEFAULT,
    "started_at":           None,
    "last_tick_at":         None,
    "last_tick_result":     None,
    "current_zip":          None,   # zip being actively canonicalized, if any
    "current_zip_started":  None,   # when current_zip work started
    "consecutive_errors":   0,
    "backoff_until":        None,
    "total_ticks":          0,
    "total_processed":      0,
    "total_zips_completed": 0,      # ZIPs cycled through the priority-1 queue
    "total_errors":         0,
    "last_error":           None,
    "last_error_at":        None,
    # Round-robin pointer (Priority 2 fallback)
    "_rr_idx":              -1,
    "config": {
        "tick_interval":    TICK_INTERVAL,
        "idle_interval":    IDLE_INTERVAL,
        "concurrency":      CONCURRENCY,
        "startup_delay":    STARTUP_DELAY,
    },
}


def _find_priority_1_zip() -> Optional[str]:
    """
    Priority 1: ZIPs the orchestrator explicitly marked as having
    deferred or failed canon work. Returns one zip_code or None.

    Reads zip_onboarding._STATE (in-memory). This catches the exact case
    that motivated this task — multi-ZIP batches where the lock deferred
    later ZIPs' canon. Cleared first.

    Note: orchestrator state is wiped on Railway redeploy. Priority-2
    round-robin still catches these ZIPs after a deploy by detecting
    the actual DB gap.
    """
    try:
        from backend.tasks.zip_onboarding import _STATE as orch_state
    except Exception:
        return None

    pending_states = ("live_canonicalize_pending", "live_canonicalize_failed")
    for zip_code, st in orch_state.items():
        if (st or {}).get("state") in pending_states:
            return zip_code
    return None


def _find_priority_2_zip(supa, state_dict: dict) -> Optional[str]:
    """
    Priority 2: round-robin through all live ZIPs.

    Advances the round-robin index by one each call. Returns the next
    live zip_code, or None if there are no live ZIPs at all.

    Even on ZIPs with nothing to do, calling backfill_zip is fast (it
    pulls parcels + canonical PINs and computes the diff, finds nothing,
    returns). Acceptable per-tick cost. The big work is processing ZIPs
    that DO have pending canon; those happen one at a time anyway.
    """
    zips_resp = (
        supa.table("zip_coverage_v3")
        .select("zip_code")
        .eq("status", "live")
        .order("zip_code")
        .execute()
    )
    live_zips = [r["zip_code"] for r in (zips_resp.data or [])]
    if not live_zips:
        return None

    state_dict["_rr_idx"] = (state_dict.get("_rr_idx", -1) + 1) % len(live_zips)
    return live_zips[state_dict["_rr_idx"]]


async def canonicalize_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    # Lazy imports so module load can't break test harnesses
    from backend.api.db import get_supabase_client
    from backend.ingest.backfill_owner_canonical import backfill_zip
    from backend.tasks.zip_onboarding import _CANONICALIZE_LOCK

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"canonicalize_autofill: tick every {TICK_INTERVAL}s, "
        f"idle every {IDLE_INTERVAL}s, concurrency={CONCURRENCY}, "
        f"first tick in {STARTUP_DELAY}s, enabled={ENABLED_DEFAULT}"
    )
    await asyncio.sleep(STARTUP_DELAY)

    while True:
        try:
            # Pause flag
            if not state["enabled"]:
                await asyncio.sleep(30)
                continue

            # Backoff window
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

            # If onboarding is actively canonicalizing right now, defer
            # cleanly — the lock would block us anyway, but checking first
            # lets us log the deferral and skip the DB scan.
            if _CANONICALIZE_LOCK.locked():
                log.info("canonicalize_autofill: lock held by onboarding, sleeping")
                state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
                state["last_tick_result"] = {
                    "action": "deferred",
                    "reason": "_CANONICALIZE_LOCK held by onboarding task",
                }
                await asyncio.sleep(TICK_INTERVAL)
                continue

            supa = get_supabase_client()
            if supa is None:
                log.warning("canonicalize_autofill: supa unavailable, sleeping")
                await asyncio.sleep(60)
                continue

            # Pick a ZIP: Priority 1 (orchestrator-flagged) > Priority 2 (round-robin)
            zip_code = _find_priority_1_zip()
            priority = "1-orchestrator-flagged"
            if not zip_code:
                zip_code = _find_priority_2_zip(supa, state)
                priority = "2-round-robin"

            if not zip_code:
                # No live ZIPs at all — long idle sleep
                state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
                state["last_tick_result"] = {
                    "action": "idle",
                    "reason": "no live ZIPs",
                }
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            log.info(f"canonicalize_autofill: processing {zip_code} (priority={priority})")
            state["current_zip"] = zip_code
            state["current_zip_started"] = datetime.now(timezone.utc).isoformat()

            # Acquire the same lock the orchestrator uses. Other onboardings
            # will defer to live_canonicalize_pending if they hit step 7
            # while we hold it. After backfill_zip returns, we release.
            async with _CANONICALIZE_LOCK:
                def _run() -> dict:
                    return backfill_zip(
                        zip_code=zip_code,
                        dry_run=False,
                        limit=None,
                        force=False,
                        sleep_ms=50,
                        verbose=False,
                        concurrency=CONCURRENCY,
                    )
                stats = await asyncio.to_thread(_run)

            state["current_zip"] = None
            state["current_zip_started"] = None

            # If this was Priority 1, mark the orchestrator state as completed
            # so subsequent ticks don't re-pick the same ZIP.
            if priority.startswith("1") and (stats.get("errors") or []) == []:
                try:
                    from backend.tasks.zip_onboarding import _STATE as orch_state
                    if zip_code in orch_state:
                        orch_state[zip_code]["state"] = "completed"
                        orch_state[zip_code]["completed_at"] = (
                            datetime.now(timezone.utc).isoformat()
                        )
                        orch_state[zip_code]["completed_by"] = "canonicalize_autofill"
                    state["total_zips_completed"] += 1
                except Exception as orch_exc:
                    log.warning(
                        f"canonicalize_autofill: couldn't update orchestrator "
                        f"state for {zip_code}: {orch_exc}"
                    )

            processed = stats.get("processed", 0) or 0
            errors_count = len(stats.get("errors") or [])

            state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
            state["last_tick_result"] = {
                "zip_code":     zip_code,
                "priority":     priority,
                "eligible":     stats.get("eligible"),
                "already_done": stats.get("already_done"),
                "processed":    processed,
                "low_conf":     stats.get("low_conf"),
                "errors":       errors_count,
                "cost_usd":     stats.get("cost_usd", 0),
                "wall_time_s":  stats.get("wall_time_s", 0),
            }
            state["total_ticks"] += 1
            state["total_processed"] += processed
            state["consecutive_errors"] = 0

            log.info(
                f"canonicalize_autofill: done {zip_code} "
                f"processed={processed} errors={errors_count} "
                f"cost=${stats.get('cost_usd', 0):.2f}"
            )

            # If we DID work, brief sleep before next tick (someone else may
            # have queued up while we were busy). If nothing was processed,
            # advance to the next ZIP quickly via shorter sleep — we're
            # cycling through the round-robin looking for actual work.
            if processed > 0:
                await asyncio.sleep(TICK_INTERVAL)
            else:
                # Quick advance to find pending work. Cap so we don't
                # hammer Supabase too hard in idle.
                await asyncio.sleep(max(30, TICK_INTERVAL // 10))

        except asyncio.CancelledError:
            log.info("canonicalize_autofill: cancelled, exiting cleanly")
            raise

        except Exception as e:
            state["consecutive_errors"] += 1
            state["total_errors"] += 1
            state["last_error"] = f"{type(e).__name__}: {e}"
            state["last_error_at"] = datetime.now(timezone.utc).isoformat()
            state["current_zip"] = None
            state["current_zip_started"] = None

            # Exponential backoff capped at MAX_BACKOFF_SECS
            wait = min(MAX_BACKOFF_SECS, 30 * (2 ** min(state["consecutive_errors"], 10)))
            backoff_dt = datetime.now(timezone.utc) + timedelta(seconds=wait)
            state["backoff_until"] = backoff_dt.isoformat()
            log.exception(
                f"canonicalize_autofill: error in tick; "
                f"backing off {wait}s (errors={state['consecutive_errors']})"
            )
            await asyncio.sleep(min(wait, 60))
