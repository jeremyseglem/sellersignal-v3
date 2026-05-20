"""
Snohomish daily new-case report autofill task.

Parallel to obit_autofill.py but for backend/harvesters/snohomish_daily_
report.py. Fires POST /api/harvest/run with source=snohomish_daily on a
daily cadence, since Snohomish County Clerk publishes new reports once
per business day (after court close).

Behavior:
  - Ticks every TICK_INTERVAL seconds (default 24h = 86400s).
  - Each tick harvests the last SNO_SINCE_DAYS days of reports. The
    raw_signals_v3 (source_type, document_ref) unique constraint makes
    re-runs idempotent, so a 3-7 day lookback safely covers any
    weekend / holiday gap without duplicating signals.
  - Runs match_after=true so newly harvested signals immediately pass
    through the parcel matcher and appear in /matches.
  - First tick fires SNO_STARTUP_DELAY seconds after boot (default 90s).
  - On error, uses exponential backoff up to 60 min.
  - State exposed via /api/harvest/snohomish-daily-autofill-status.
  - Can be paused/resumed via /api/harvest/snohomish-daily-autofill-
    {pause,resume}.

Why a single daily tick (vs obit's 12h cadence):
  Snohomish publishes reports once per business day. Polling more often
  doesn't surface new data — it just adds unnecessary load on the county
  document server and on our matcher. The 7-day lookback handles holidays
  and any tick we miss (e.g., a deploy that lands during the daily window).

Independent of KC: this autofill has no portal-health dependency on the
KC Superior Court portal. Snohomish's source is a static PDF endpoint —
no captcha, no session, no portal state to track.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────
TICK_INTERVAL      = int(os.environ.get("SNO_DAILY_AUTOFILL_TICK_SECONDS", "86400"))   # 24h
SNO_SINCE_DAYS     = int(os.environ.get("SNO_DAILY_AUTOFILL_SINCE_DAYS",   "7"))
SNO_RUN_TIMEOUT    = int(os.environ.get("SNO_DAILY_AUTOFILL_RUN_TIMEOUT",  "600"))    # 10min
SNO_STARTUP_DELAY  = int(os.environ.get("SNO_DAILY_AUTOFILL_STARTUP_DELAY", "90"))

# ZIP scoping for the matcher phase. Like the obit autofill: empty string
# is treated as None below, which means "match against all covered ZIPs"
# — appropriate now that 98290 is live and 98020/98026 are being onboarded.
_ZIP_FILTER_RAW    = os.environ.get("SNO_DAILY_AUTOFILL_ZIP_FILTER", "").strip()
ZIP_FILTER         = _ZIP_FILTER_RAW or None
MAX_BACKOFF_SECS   = 3600

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
        "since_days":       SNO_SINCE_DAYS,
        "zip_filter":       ZIP_FILTER,
    },
}


async def _run_one_tick(client: httpx.AsyncClient, admin_key: str) -> dict:
    """Fire one Snohomish daily harvest cycle and return the parsed result."""
    r = await client.post(
        "/api/harvest/run",
        json={
            "source":          "snohomish_daily",
            "since_days_ago":  SNO_SINCE_DAYS,
            "dry_run":         False,
            "match_after":     True,
            "zip_filter":      ZIP_FILTER,
        },
        headers={"X-Admin-Key": admin_key},
        timeout=SNO_RUN_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


async def snohomish_daily_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        log.error(
            "snohomish_daily_autofill: ADMIN_KEY env var not set — disabling. "
            "Set ADMIN_KEY in Railway env to enable."
        )
        state["enabled"] = False
        return

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"snohomish_daily_autofill: scheduled to tick every {TICK_INTERVAL}s "
        f"(since_days={SNO_SINCE_DAYS}, zip={ZIP_FILTER}), "
        f"first tick in {SNO_STARTUP_DELAY}s"
    )
    await asyncio.sleep(SNO_STARTUP_DELAY)

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
                    f"snohomish_daily_autofill tick #{state['total_ticks']}: "
                    f"harvested={harvested} new={upserted_new} "
                    f"matched={matched_count}"
                )

                await asyncio.sleep(TICK_INTERVAL)

            except asyncio.CancelledError:
                log.info("snohomish_daily_autofill: loop cancelled (shutdown)")
                raise
            except Exception as e:
                state["consecutive_errors"] += 1
                state["total_errors"]       += 1
                state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
                state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
                log.error(
                    f"snohomish_daily_autofill tick failed "
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
