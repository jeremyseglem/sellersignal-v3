"""
KC Treasury autofill background task — continuously harvests the
tax-foreclosure parcel feed.

Parallel to obit_autofill.py but for the KC Treasury harvester. Fires
POST /api/harvest/run with source=kc_treasury on a once-a-day cadence.

Cadence rationale:
  - The Treasury feed is a point-in-time snapshot. Parcels enter/exit
    foreclosure as tax debts are filed or paid off — typically once per
    day on the county's side.
  - Running hourly would hammer the SODA API with zero new information.
  - Running nightly (24h) keeps the DB fresh with ~1-day lag, which is
    fine for a distress signal whose timeline is measured in months
    (WA requires 3 years delinquent before tax foreclosure can proceed).

Behavior:
  - Ticks every TICK_INTERVAL seconds (default 24h = 86400s).
  - Since/until are IGNORED by the Treasury harvester (snapshot-only,
    not a time-series), but the API requires them — we pass a nominal
    since_days_ago=1.
  - Idempotent: document_ref is the parcel id, so re-runs upsert-to-self.
  - Runs match_after=true so new tax-foreclosure signals immediately
    surface in /matches/{zip}.
  - First tick fires TREASURY_STARTUP_DELAY seconds after boot.
  - On error, exponential backoff up to 60 min.

No portal-health gate — KC Open Data Socrata API is independent of the
superior court portal.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────
TICK_INTERVAL          = int(os.environ.get("TREASURY_AUTOFILL_TICK_SECONDS", "86400"))  # 24h
TREASURY_SINCE_DAYS    = int(os.environ.get("TREASURY_AUTOFILL_SINCE_DAYS",    "1"))
TREASURY_RUN_TIMEOUT   = int(os.environ.get("TREASURY_AUTOFILL_RUN_TIMEOUT",   "300"))
TREASURY_STARTUP_DELAY = int(os.environ.get("TREASURY_AUTOFILL_STARTUP_DELAY", "120"))
ZIP_FILTER             = os.environ.get("TREASURY_AUTOFILL_ZIP_FILTER", "98004")
MAX_BACKOFF_SECS       = 3600

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
        "since_days":       TREASURY_SINCE_DAYS,
        "zip_filter":       ZIP_FILTER,
    },
}


async def _run_one_tick(client: httpx.AsyncClient, admin_key: str) -> dict:
    """Fire one Treasury harvest cycle and return the parsed result."""
    r = await client.post(
        "/api/harvest/run",
        json={
            "source":          "kc_treasury",
            "since_days_ago":  TREASURY_SINCE_DAYS,
            "dry_run":         False,
            "match_after":     True,
            "zip_filter":      ZIP_FILTER,
        },
        headers={"X-Admin-Key": admin_key},
        timeout=TREASURY_RUN_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


async def treasury_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        log.error(
            "treasury_autofill: ADMIN_KEY env var not set — disabling. "
            "Set ADMIN_KEY in Railway env to enable."
        )
        state["enabled"] = False
        return

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"treasury_autofill: scheduled to tick every {TICK_INTERVAL}s "
        f"(since_days={TREASURY_SINCE_DAYS}, zip={ZIP_FILTER}), "
        f"first tick in {TREASURY_STARTUP_DELAY}s"
    )
    await asyncio.sleep(TREASURY_STARTUP_DELAY)

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
                    f"treasury_autofill tick #{state['total_ticks']}: "
                    f"harvested={harvested} new={upserted_new} "
                    f"matched={matched_count}"
                )

                await asyncio.sleep(TICK_INTERVAL)

            except asyncio.CancelledError:
                log.info("treasury_autofill: loop cancelled (shutdown)")
                raise
            except Exception as e:
                state["consecutive_errors"] += 1
                state["total_errors"]       += 1
                state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
                state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
                log.error(
                    f"treasury_autofill tick failed "
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
