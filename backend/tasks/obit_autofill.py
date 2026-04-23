"""
Obituary autofill background task — continuously harvests new obits.

Parallel to autofill.py but for the obituary harvester. Fires
POST /api/harvest/run with source=obituary on a slow cadence, since
obits are appended to the source lists (Seattle Times sitemap, Dignity
Memorial bellevue-wa/seattle-wa) a few times per day at most.

Behavior:
  - Ticks every TICK_INTERVAL seconds (default 12h = 43200s).
  - Each tick harvests obits from the last OBIT_SINCE_DAYS days. Since
    document_ref is a stable hash of (name, death_date, source), re-runs
    are idempotent — existing obits upsert-to-self, new ones append.
  - Runs match_after=true so newly harvested obits immediately pass
    through the parcel matcher and appear in /matches.
  - First tick fires OBIT_STARTUP_DELAY seconds after boot (default 60s)
    so the harvest + match cycle runs near each deploy, not just on
    the tick schedule.
  - On error, uses exponential backoff up to 60 min.
  - State exposed via /api/harvest/obit-autofill-status for observability.
  - Can be paused/resumed via /api/harvest/obit-autofill-{pause,resume}.

Independent of the KC court portal — obit sources are separate,
so no portal-health gating.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────
TICK_INTERVAL       = int(os.environ.get("OBIT_AUTOFILL_TICK_SECONDS", "43200"))  # 12h
OBIT_SINCE_DAYS     = int(os.environ.get("OBIT_AUTOFILL_SINCE_DAYS",   "7"))
OBIT_RUN_TIMEOUT    = int(os.environ.get("OBIT_AUTOFILL_RUN_TIMEOUT",  "600"))
OBIT_STARTUP_DELAY  = int(os.environ.get("OBIT_AUTOFILL_STARTUP_DELAY", "60"))
ZIP_FILTER          = os.environ.get("OBIT_AUTOFILL_ZIP_FILTER", "98004")
MAX_BACKOFF_SECS    = 3600

LOCAL_PORT = int(os.environ.get("PORT", "8000"))
BASE_URL   = f"http://127.0.0.1:{LOCAL_PORT}"

# ── Shared state ──────────────────────────────────────────────────────────
state: dict = {
    "enabled":              True,
    "started_at":           None,
    "last_tick_at":         None,
    "last_tick_result":     None,
    "consecutive_errors":   0,
    "backoff_until":        None,
    "total_ticks":          0,
    "total_harvested":      0,
    "total_upserted_new":   0,
    "total_matches":        0,
    "total_errors":         0,
    "last_error":           None,
    "last_error_at":        None,
    "config": {
        "tick_interval":    TICK_INTERVAL,
        "since_days":       OBIT_SINCE_DAYS,
        "zip_filter":       ZIP_FILTER,
    },
}


async def _run_one_tick(client: httpx.AsyncClient, admin_key: str) -> dict:
    """Fire one obit harvest cycle and return the parsed result."""
    r = await client.post(
        "/api/harvest/run",
        json={
            "source":          "obituary",
            "since_days_ago":  OBIT_SINCE_DAYS,
            "dry_run":         False,
            "match_after":     True,
            "zip_filter":      ZIP_FILTER,
        },
        headers={"X-Admin-Key": admin_key},
        timeout=OBIT_RUN_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


async def obit_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        log.error(
            "obit_autofill: ADMIN_KEY env var not set — disabling. "
            "Set ADMIN_KEY in Railway env to enable."
        )
        state["enabled"] = False
        return

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"obit_autofill: scheduled to tick every {TICK_INTERVAL}s "
        f"(since_days={OBIT_SINCE_DAYS}, zip={ZIP_FILTER}), "
        f"first tick in {OBIT_STARTUP_DELAY}s"
    )
    await asyncio.sleep(OBIT_STARTUP_DELAY)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
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

                # Do the work
                result = await _run_one_tick(client, admin_key)

                harvested     = result.get("harvested", 0) or 0
                upserted_new  = result.get("upserted_new", 0) or 0
                match_stats   = result.get("match_stats") or {}
                matched_count = match_stats.get("matched", 0) or 0

                state["last_tick_at"]     = datetime.now(timezone.utc).isoformat()
                state["last_tick_result"] = {
                    "harvested":      harvested,
                    "upserted_new":   upserted_new,
                    "upserted_dup":   result.get("upserted_dup", 0),
                    "match_stats":    match_stats,
                    "errors":         len(result.get("errors", []) or []),
                }
                state["total_ticks"]         += 1
                state["total_harvested"]     += harvested
                state["total_upserted_new"]  += upserted_new
                state["total_matches"]       += matched_count
                state["consecutive_errors"]   = 0

                log.info(
                    f"obit_autofill tick #{state['total_ticks']}: "
                    f"harvested={harvested} new={upserted_new} "
                    f"matched={matched_count}"
                )

                await asyncio.sleep(TICK_INTERVAL)

            except asyncio.CancelledError:
                log.info("obit_autofill: loop cancelled (shutdown)")
                raise
            except Exception as e:
                state["consecutive_errors"] += 1
                state["total_errors"]       += 1
                state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
                state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
                log.error(
                    f"obit_autofill tick failed "
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
