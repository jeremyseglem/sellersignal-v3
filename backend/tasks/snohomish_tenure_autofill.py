"""
Snohomish SCOPI tenure autofill — fills last_transfer_date for parcels
missing tenure data by scraping the per-parcel detail page.

Why this exists:
  The Snohomish bulk Sales Excel only goes back 5 years. About 74% of
  98290 parcels have no sale in that window. Without older transfer
  dates, the bander classifies those parcels as `unknown` and they
  never surface as Tier-2 leads — even though most are individual-owned
  homes held for >5 years (the actionable long-tenure cohort).

  SCOPI's per-parcel detail page exposes the full Sales History,
  going back decades. This task scrapes it for parcels missing tenure
  and writes the most-recent sale date back to parcels_v3.

  Same architectural pattern as rematch_autofill: in-process loop, no
  HTTP loopback, paginates through work in bounded ticks so Railway's
  10-minute HTTP timeout doesn't apply.

Behavior:
  - First tick fires SCOPI_AUTOFILL_STARTUP_DELAY seconds after boot
    (default 30s).
  - Each tick processes up to BATCH_SIZE parcels (default 50).
  - Politeness: POLITENESS_DELAY seconds between parcels (default 0.5).
  - Tick interval: TICK_INTERVAL seconds active, IDLE_INTERVAL idle.
  - Once a parcel is scraped, tenure_checked_at is stamped so it's
    never scraped twice (regardless of whether sales were found).
  - State exposed via /api/admin/snohomish-tenure-autofill-status.

Schema dependency: requires `parcels_v3.tenure_checked_at` column from
migration 017. The task tolerates the column not existing yet (logs
once and sleeps long) so a missing migration doesn't crash the loop.
"""
import asyncio
import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────

# Whether the loop runs at all. Default off — admins flip a flag once
# 98290 is ready for it. Other Snohomish ZIPs should be opt-in too.
ENABLED = os.environ.get("SCOPI_AUTOFILL_ENABLED", "false").lower() == "true"

# How long between active ticks (when there's still work to do).
TICK_INTERVAL = int(os.environ.get("SCOPI_AUTOFILL_TICK_SECONDS", "30"))

# How long between idle polls (when the queue is drained).
IDLE_INTERVAL = int(os.environ.get("SCOPI_AUTOFILL_IDLE_SECONDS", "3600"))

# Parcels per tick. SCOPI is a sturdy old ASP.NET site, but we still
# rate-limit politely. 50 parcels × 0.5s politeness = ~25s scraping
# time per tick, well under the 30s tick interval.
BATCH_SIZE = int(os.environ.get("SCOPI_AUTOFILL_BATCH_SIZE", "50"))

# Sleep between individual parcel requests. 0.5s = ~2 req/sec.
POLITENESS_DELAY = float(os.environ.get("SCOPI_AUTOFILL_POLITENESS", "0.5"))

# First-tick delay so the rest of the app finishes booting.
SCOPI_AUTOFILL_STARTUP_DELAY = int(
    os.environ.get("SCOPI_AUTOFILL_STARTUP_DELAY", "30")
)

# Market this task operates on. Hard-coded for now (Snohomish only).
MARKET_KEY = "WA_SNOHOMISH"


# ── Shared state for /status endpoint ─────────────────────────────────────
_state: dict = {
    "enabled":             ENABLED,
    "started_at":          None,
    "last_tick_at":        None,
    "last_tick_result":    None,
    "consecutive_errors":  0,
    "backoff_until":       None,
    "total_ticks":         0,
    "total_processed":     0,
    "total_with_sales":    0,
    "total_no_sales":      0,
    "total_errors":        0,
    "last_error":          None,
    "last_error_at":       None,
    "parcels_remaining":   None,
    "config": {
        "tick_interval":   TICK_INTERVAL,
        "idle_interval":   IDLE_INTERVAL,
        "batch_size":      BATCH_SIZE,
        "politeness":      POLITENESS_DELAY,
        "market":          MARKET_KEY,
    },
}


def get_state() -> dict:
    return dict(_state)


# ── Helpers ───────────────────────────────────────────────────────────────
def _count_pending(supa) -> Optional[int]:
    """How many parcels are still awaiting a SCOPI tenure check?"""
    try:
        r = (supa.table("parcels_v3")
             .select("pin", count="exact")
             .eq("market_key", MARKET_KEY)
             .is_("last_transfer_date", "null")
             .is_("tenure_checked_at", "null")
             .limit(1)
             .execute())
        return r.count or 0
    except Exception as e:
        # If the column doesn't exist yet (migration 017 not applied),
        # the query errors. Surface as None — caller treats that as
        # "schema not ready, sleep long."
        msg = str(e).lower()
        if "tenure_checked_at" in msg or "column" in msg:
            log.warning("[scopi-autofill] tenure_checked_at column missing — "
                        "apply migration 017 to enable this task")
            return None
        raise


def _fetch_pending_pins(supa, limit: int) -> list[str]:
    """Get the next batch of parcel PINs to scrape."""
    r = (supa.table("parcels_v3")
         .select("pin")
         .eq("market_key", MARKET_KEY)
         .is_("last_transfer_date", "null")
         .is_("tenure_checked_at", "null")
         .order("pin")
         .limit(limit)
         .execute())
    return [row["pin"] for row in (r.data or [])]


def _update_parcel(supa, pin: str, sale_date: Optional[date],
                   sale_price: Optional[int]) -> None:
    """Write the scrape result back to parcels_v3."""
    today = date.today()
    payload: dict = {
        "tenure_checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if sale_date is not None:
        tenure_years = round((today - sale_date).days / 365.25, 1)
        payload["last_transfer_date"]  = sale_date.isoformat()
        payload["tenure_years"]        = tenure_years
        if sale_price is not None and sale_price > 0:
            payload["last_transfer_price"] = sale_price
    # If no sale_date, we leave last_transfer_date NULL but DO stamp
    # tenure_checked_at so the parcel won't be re-scraped.
    (supa.table("parcels_v3")
     .update(payload)
     .eq("pin", pin)
     .execute())


# ── One tick: scrape up to BATCH_SIZE parcels ─────────────────────────────
def _run_tick(supa) -> dict:
    """
    Scrape one batch. Returns a dict summarizing what happened.
    Runs synchronously (httpx.Client is sync); the outer loop awaits
    asyncio.to_thread on this so it doesn't block the event loop.
    """
    from backend.harvesters.snohomish_scopi import (
        fetch_parcel_sales, make_client,
    )

    pins = _fetch_pending_pins(supa, BATCH_SIZE)
    if not pins:
        return {"processed": 0, "with_sales": 0, "no_sales": 0,
                "errors": 0, "elapsed_s": 0.0}

    started = time.time()
    with_sales = no_sales = errors = 0
    client = make_client()
    try:
        for i, pin in enumerate(pins):
            res = fetch_parcel_sales(client, pin)
            if not res.success:
                errors += 1
                # Don't stamp tenure_checked_at on failure — let the
                # parcel be retried on a later tick.
            else:
                _update_parcel(supa, pin, res.most_recent_sale,
                               res.most_recent_price)
                if res.most_recent_sale is not None:
                    with_sales += 1
                else:
                    no_sales += 1
            # Politeness — but skip the sleep on the last item
            if i < len(pins) - 1:
                time.sleep(POLITENESS_DELAY)
    finally:
        client.close()

    return {
        "processed":   len(pins),
        "with_sales":  with_sales,
        "no_sales":    no_sales,
        "errors":      errors,
        "elapsed_s":   round(time.time() - started, 1),
    }


# ── Main loop ─────────────────────────────────────────────────────────────
async def snohomish_tenure_autofill_loop() -> None:
    """
    Background loop. Sweeps Snohomish parcels missing tenure data and
    fills them from SCOPI. Sleep durations are configurable via env.
    """
    if not ENABLED:
        log.info("[scopi-autofill] disabled (set SCOPI_AUTOFILL_ENABLED=true to start)")
        return

    log.info("[scopi-autofill] starting in %ds…", SCOPI_AUTOFILL_STARTUP_DELAY)
    await asyncio.sleep(SCOPI_AUTOFILL_STARTUP_DELAY)

    _state["started_at"] = datetime.now(timezone.utc).isoformat()

    from backend.api.db import get_supabase_client

    while True:
        try:
            supa = get_supabase_client()
            if not supa:
                log.warning("[scopi-autofill] no Supabase client — sleeping idle")
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            pending = _count_pending(supa)
            if pending is None:
                # Schema not ready (migration 017 not applied). Sleep
                # idle and try again — apply the migration whenever.
                _state["parcels_remaining"] = None
                _state["last_error"] = "schema not ready (migration 017?)"
                _state["last_error_at"] = datetime.now(timezone.utc).isoformat()
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            _state["parcels_remaining"] = pending

            if pending == 0:
                # Drained — sleep idle.
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            # Run one tick in a thread (httpx.Client is sync).
            result = await asyncio.to_thread(_run_tick, supa)

            # Update state
            _state["last_tick_at"]      = datetime.now(timezone.utc).isoformat()
            _state["last_tick_result"]  = result
            _state["total_ticks"]      += 1
            _state["total_processed"]  += result["processed"]
            _state["total_with_sales"] += result["with_sales"]
            _state["total_no_sales"]   += result["no_sales"]
            _state["total_errors"]     += result["errors"]

            if result["errors"] > 0 and result["processed"] == result["errors"]:
                # All-errors tick — back off
                _state["consecutive_errors"] += 1
                backoff = min(IDLE_INTERVAL,
                              TICK_INTERVAL * (2 ** _state["consecutive_errors"]))
                _state["backoff_until"] = datetime.now(timezone.utc).isoformat()
                _state["last_error"] = f"all {result['errors']} parcels errored this tick"
                _state["last_error_at"] = _state["last_tick_at"]
                log.warning("[scopi-autofill] all-errors tick, backing off %ds",
                            backoff)
                await asyncio.sleep(backoff)
            else:
                _state["consecutive_errors"] = 0
                await asyncio.sleep(TICK_INTERVAL)

        except asyncio.CancelledError:
            log.info("[scopi-autofill] cancelled, exiting")
            raise
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            _state["last_error_at"] = datetime.now(timezone.utc).isoformat()
            log.exception("[scopi-autofill] tick failed: %s", e)
            await asyncio.sleep(TICK_INTERVAL)
