"""
Geometry autofill background task — fills missing parcel lat/lng per ZIP.

Why this exists (2026-06-11): onboarding seeds parcels without lat/lng (the
bulk assessor files don't carry coordinates), so every new ZIP needs a
geometry backfill against its county's ArcGIS layer before map pins render.
The synchronous POST /api/admin/geometry/{zip} endpoint works but a full ZIP
(7-10K parcels) takes many minutes; on Railway's single worker a held call
blocks every other request, and chunk-feeding it by hand is operator toil
(felt acutely onboarding the 3 Dallas ZIPs — ~25K parcels total).

This task does the same work as the endpoint, in-process and incrementally:

  - Ticks every TICK_INTERVAL seconds (default 90s).
  - Each tick: pick the live ZIP with the most missing geometry, backfill a
    small chunk (GEOM_CHUNK pins, default 300) via backfill_geometry_zip_async
    (async — yields to the event loop between ArcGIS batches, so the API
    stays responsive; this is what the held HTTP call could not do).
  - ZIPs whose stuck PINs are flagged geocode_skipped are naturally excluded
    by the underlying query (migration 024).
  - When nothing is missing anywhere, idles at IDLE_INTERVAL (default 1h).
  - On error, exponential backoff up to 30 min.
  - State via /api/harvest/geometry-autofill-status; pause/resume endpoints.

Market-agnostic: market_key is resolved per-ZIP from zip_coverage_v3, same as
the admin endpoint, so any market in geometry_backfill.MARKET_CONFIGS
(WA_KING / WA_SNOHOMISH / AZ_MARICOPA / TX_DALLAS / future) is covered.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Configuration (tunable via env) ───────────────────────────────────────
# INCIDENT 2026-06-11: first deployment of this task saturated the single
# Railway worker (production unreachable for hours — even /api/health timed
# out after TLS connect). Root cause: backfill_geometry_zip_async contains
# SYNC Supabase calls (_fetch_pins_missing_geometry + the lat/lng upserts)
# that run directly on the event loop, and _pick_target_zip counts missing
# geometry across every live ZIP (62 queries) each tick. Under load the event
# loop never freed. The task is now OFF by default; set
# GEOM_AUTOFILL_ENABLED=1 only after the blocking calls are wrapped in
# asyncio.to_thread and the per-tick ZIP scan is cached.
ENABLED_AT_BOOT = os.environ.get("GEOM_AUTOFILL_ENABLED", "0") == "1"
TICK_INTERVAL   = int(os.environ.get("GEOM_AUTOFILL_TICK_SECONDS", "90"))
IDLE_INTERVAL   = int(os.environ.get("GEOM_AUTOFILL_IDLE_SECONDS", "3600"))
GEOM_CHUNK      = int(os.environ.get("GEOM_AUTOFILL_CHUNK", "300"))
STARTUP_DELAY   = int(os.environ.get("GEOM_AUTOFILL_STARTUP_DELAY", "120"))
MAX_BACKOFF     = 1800

# ── Shared state ──────────────────────────────────────────────────────────
state: dict = {
    "enabled":            ENABLED_AT_BOOT,
    "started_at":         None,
    "last_tick_at":       None,
    "last_tick_result":   None,
    "consecutive_errors": 0,
    "backoff_until":      None,
    "total_ticks":        0,
    "total_updated":      0,
    "total_errors":       0,
    "last_error":         None,
    "last_error_at":      None,
    "config": {
        "tick_interval": TICK_INTERVAL,
        "idle_interval": IDLE_INTERVAL,
        "chunk":         GEOM_CHUNK,
    },
}


def _pick_target_zip(supa) -> Optional[tuple]:
    """Return (zip_code, market_key, missing_count) for the live ZIP with the
    most parcels missing geometry, or None if everything is geocoded.

    Counts respect geocode_skipped where the column exists (the count query
    mirrors geometry_backfill._fetch_pins_missing_geometry's filter)."""
    cov = (supa.table("zip_coverage_v3")
           .select("zip_code, market_key, status")
           .eq("status", "live")
           .execute()).data or []
    best = None
    for row in cov:
        z = row.get("zip_code")
        if not z:
            continue
        try:
            q = (supa.table("parcels_v3")
                 .select("pin", count="exact")
                 .eq("zip_code", z)
                 .or_("lat.is.null,lng.is.null"))
            try:
                res = q.eq("geocode_skipped", False).limit(1).execute()
            except Exception:
                res = (supa.table("parcels_v3")
                       .select("pin", count="exact")
                       .eq("zip_code", z)
                       .or_("lat.is.null,lng.is.null")
                       .limit(1).execute())
            missing = res.count or 0
        except Exception as e:
            log.warning(f"geometry_autofill: count failed for {z}: {e}")
            continue
        if missing > 0 and (best is None or missing > best[2]):
            best = (z, row.get("market_key") or "WA_KING", missing)
    return best


async def geometry_autofill_loop() -> None:
    """Main task body. Runs until cancelled."""
    from backend.api.db import get_supabase_client

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(f"geometry_autofill: tick every {TICK_INTERVAL}s, "
             f"chunk={GEOM_CHUNK}, first tick in {STARTUP_DELAY}s")
    await asyncio.sleep(STARTUP_DELAY)

    while True:
        try:
            if not state["enabled"]:
                await asyncio.sleep(30)
                continue

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
                await asyncio.sleep(60)
                continue

            target = await asyncio.to_thread(_pick_target_zip, supa)
            if target is None:
                state["last_tick_result"] = {"idle": True}
                state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
                await asyncio.sleep(IDLE_INTERVAL)
                continue

            zip_code, market_key, missing = target
            # Run the SYNC wrapper on a worker thread. It creates its own
            # event loop there (asyncio.run), so every blocking call inside —
            # the sync Supabase reads/upserts AND the ArcGIS fetches — is
            # confined to that thread. The main event loop stays free to
            # serve API requests. (Calling backfill_geometry_zip_async
            # directly here was the 2026-06-11 outage: its sync Supabase
            # calls ran ON the main loop and starved it.)
            from backend.ingest.geometry_backfill import backfill_geometry_zip
            stats = await asyncio.to_thread(
                backfill_geometry_zip,
                zip_code, market_key=market_key,
                dry_run=False, limit=GEOM_CHUNK, verbose=False,
            )

            state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
            state["last_tick_result"] = {
                "zip": zip_code, "market_key": market_key,
                "missing_before": missing,
                "fetched": stats.get("fetched"),
                "updated": stats.get("updated"),
                "not_found": stats.get("not_found"),
            }
            state["total_ticks"] += 1
            state["total_updated"] += int(stats.get("updated") or 0)
            state["consecutive_errors"] = 0

            await asyncio.sleep(TICK_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            state["consecutive_errors"] += 1
            state["total_errors"] += 1
            state["last_error"] = f"{type(e).__name__}: {e}"
            state["last_error_at"] = datetime.now(timezone.utc).isoformat()
            backoff = min(MAX_BACKOFF, 60 * (2 ** min(state["consecutive_errors"], 5)))
            state["backoff_until"] = (
                datetime.now(timezone.utc) + timedelta(seconds=backoff)
            ).isoformat()
            log.warning(f"geometry_autofill: tick error ({e}); backoff {backoff}s")
