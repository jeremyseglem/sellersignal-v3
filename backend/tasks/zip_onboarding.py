"""
ZIP onboarding orchestrator — single end-to-end pipeline for adding a ZIP.

Background:
After ZIP #15 we kept hitting different variations of the same problem:
manually orchestrating 8-15 admin endpoints in the right order, with
silent failures, broken pipes, and partial completions that looked
identical to successes. Each new ZIP became 30-60 minutes of debugging.

This module collapses that into one function. The pipeline:

  1. register     — create zip_coverage_v3 row
  2. seed         — load parcels_v3 from data/seeds/wa-king-{zip}-owners.json
                    (writes owner_name, last_transfer_date, tenure_years,
                     value, address, owner_type)
  3. canonicalize — parse owner_name into owner_canonical_v3 via Haiku 4.5
                    (cost ~$0.50 per 1k parcels at current pricing; ~$4-9
                    for a typical 8-18k-parcel KC ZIP. See the canonicalize
                    module docstring for the per-parcel rate;
                    backend/ingest/backfill_owner_canonical.py prints
                    measured cost at end of each run.)
  4. classify     — assign signal_family archetype based on owner_type
                    + tenure_years + value patterns
  5. band         — assign Band 0-4 based on archetype + hard
                    disqualifiers (institutional, brokerage, etc.)
  6. refresh-counts — update zip_coverage_v3.current_call_now_count
                    snapshot for the territory map UI

NOT included (separate concerns):
  - rematch_autofill — global operation, not per-ZIP
  - obit harvest — global, runs on its own 12h cadence
  - tax foreclosure ingest — TBD, separate signal source

Architecture:
  - Runs as an asyncio task started from the admin endpoint
  - Each step is idempotent — re-running picks up where it left off
  - Status tracked in module-level _STATE dict, served by /onboard-status
  - Each step uses the existing cmd_* functions from zip_builder
  - Canonicalize uses cmd_canonicalize directly (synchronous in-process,
    NOT the canonicalize-all endpoint which returns immediately and
    spawns a separate background task that gets killed by deploys)

Failure handling:
  - Transient (Supabase broken pipe, etc.) → retry up to 3x with backoff
  - Hard error → mark step failed, halt pipeline, expose in status

This is intentionally a thin orchestration layer. It does not duplicate
logic that lives elsewhere — every step calls into existing code via
the cmd_* functions. If a cmd_* function has a bug, that's where to
fix it, not here.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Module-level state: maps zip_code -> status dict.
# Cleared on service restart (deploy-resilience would require persisting
# to DB; deferred for MVP since each ZIP onboarding is a few hours and
# we control deploy timing).
_STATE: dict[str, dict] = {}

# Pipeline step names in order
PIPELINE_STEPS = [
    "register",
    "seed",
    "canonicalize",
    "classify",
    "band",
    "refresh_counts",
]


def get_status(zip_code: str) -> dict:
    """Return current onboarding status for a ZIP. Used by the status endpoint."""
    return _STATE.get(zip_code, {
        "zip_code": zip_code,
        "state":    "not_started",
        "steps":    {s: "pending" for s in PIPELINE_STEPS},
    })


def _set_step(zip_code: str, step: str, status: str, detail: Optional[str] = None):
    """Update step status in the state dict."""
    state = _STATE.setdefault(zip_code, {
        "zip_code":   zip_code,
        "state":      "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps":      {s: "pending" for s in PIPELINE_STEPS},
        "logs":       [],
    })
    state["steps"][step] = status
    state["last_step"] = step
    if detail:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        state["logs"].append(f"[{ts}] {step}: {detail}")
        # Cap log length
        state["logs"] = state["logs"][-200:]


def _capture_stdout(fn, *args, **kwargs) -> tuple[int, str]:
    """Run a cmd_* function, capture its stdout. Return (rc, output)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = fn(*args, **kwargs)
        except Exception as e:
            return 1, f"{buf.getvalue()}\nEXCEPTION: {type(e).__name__}: {e}\n{traceback.format_exc()}"
    return rc, buf.getvalue()


async def _retry(coro_fn, *, attempts: int = 3, backoff: float = 5.0, label: str = ""):
    """Retry an async callable on exception, with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return await coro_fn()
        except Exception as e:
            last_exc = e
            log.warning(f"[onboard:{label}] attempt {attempt+1}/{attempts} failed: {e}")
            if attempt < attempts - 1:
                await asyncio.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last_exc}")


# ─── Step implementations ────────────────────────────────────────────────────

async def _step_register(zip_code: str, market_key: str, city: str,
                         state: str, json_path: str):
    from backend.ingest.zip_builder import cmd_register

    def _run():
        return _capture_stdout(
            cmd_register, zip_code, market_key, city, state,
            source_url=None,
        )
    rc, output = await _retry(
        lambda: asyncio.to_thread(_run), label="register",
    )
    _set_step(zip_code, "register", "ok" if rc == 0 else "failed",
              output.strip()[-500:] if output else None)
    if rc != 0:
        raise RuntimeError(f"register failed: {output}")


async def _step_seed(zip_code: str, json_path: str):
    from backend.ingest.zip_builder import cmd_seed

    if not Path(json_path).exists():
        _set_step(zip_code, "seed", "failed", f"JSON not found at {json_path}")
        raise FileNotFoundError(json_path)

    def _run():
        return _capture_stdout(cmd_seed, zip_code, json_path)
    rc, output = await _retry(
        lambda: asyncio.to_thread(_run), label="seed",
    )
    _set_step(zip_code, "seed", "ok" if rc == 0 else "failed",
              output.strip()[-500:] if output else None)
    if rc != 0:
        raise RuntimeError(f"seed failed: {output}")


async def _step_canonicalize(zip_code: str):
    """
    Canonicalize via the programmatic backfill_zip function — same path
    the existing /api/admin/canonicalize/{zip} endpoint uses (verified
    working). Avoids cmd_canonicalize because that monkey-patches
    sys.argv and calls a CLI argparse main(), which is fragile in
    async/threaded context.

    This step keeps the canonicalize work bound to this onboarding task
    instead of spawning a separate background loop that gets killed by
    deploys.
    """
    from backend.ingest.backfill_owner_canonical import backfill_zip

    def _run() -> tuple[int, str]:
        try:
            stats = backfill_zip(
                zip_code=zip_code,
                dry_run=False,
                limit=None,
                force=False,
                sleep_ms=50,
                verbose=False,   # don't spam stdout — orchestrator captures via state
                concurrency=10,
            )
            # Render a one-line summary for the status feed
            summary = (
                f"eligible={stats.get('eligible')} "
                f"already_done={stats.get('already_done')} "
                f"processed={stats.get('processed')} "
                f"low_conf={stats.get('low_conf')} "
                f"errors={len(stats.get('errors') or [])} "
                f"cost_usd={stats.get('cost_usd', 0):.2f} "
                f"wall_time_s={stats.get('wall_time_s', 0):.1f}"
            )
            return 0, summary
        except Exception as e:
            import traceback
            return 1, f"EXCEPTION: {type(e).__name__}: {e}\n{traceback.format_exc()}"

    rc, output = await _retry(
        lambda: asyncio.to_thread(_run),
        attempts=2,            # canonicalize is expensive — fewer retries
        backoff=30.0,
        label="canonicalize",
    )
    _set_step(zip_code, "canonicalize", "ok" if rc == 0 else "failed",
              output[-2000:] if output else None)
    if rc != 0:
        raise RuntimeError(f"canonicalize failed: {output}")


async def _step_classify(zip_code: str):
    from backend.ingest.zip_builder import cmd_classify

    def _run():
        return _capture_stdout(cmd_classify, zip_code)
    rc, output = await _retry(
        lambda: asyncio.to_thread(_run), label="classify",
    )
    _set_step(zip_code, "classify", "ok" if rc == 0 else "failed",
              output.strip()[-800:] if output else None)
    if rc != 0:
        raise RuntimeError(f"classify failed: {output}")


async def _step_band(zip_code: str):
    from backend.ingest.zip_builder import cmd_band

    def _run():
        return _capture_stdout(cmd_band, zip_code)
    rc, output = await _retry(
        lambda: asyncio.to_thread(_run), label="band",
    )
    _set_step(zip_code, "band", "ok" if rc == 0 else "failed",
              output.strip()[-800:] if output else None)
    if rc != 0:
        raise RuntimeError(f"band failed: {output}")


async def _step_refresh_counts(zip_code: str):
    """Sync zip_coverage_v3.current_call_now_count from current briefing data."""
    import httpx
    from backend.api.db import get_supabase_client

    supa = get_supabase_client()
    if not supa:
        _set_step(zip_code, "refresh_counts", "failed", "Supabase not configured")
        raise RuntimeError("supabase missing")

    # Hit the local briefing endpoint over loopback (same pattern as
    # refresh_coverage_counts in backend/api/coverage.py).
    local_port = int(os.environ.get("PORT", "8000"))
    base_url   = f"http://127.0.0.1:{local_port}"
    admin_key  = os.environ.get("ADMIN_KEY", "")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
            resp = await client.get(
                f"/api/briefings/{zip_code}",
                params={"force_rebuild": "true"},
                headers={"X-Admin-Key": admin_key},
            )
            resp.raise_for_status()
            payload = resp.json()

        playbook = (payload or {}).get("playbook") or {}
        cn = len(playbook.get("call_now") or [])
        bn = len(playbook.get("build_now") or [])
        bn_total = (payload.get("stats") or {}).get("build_now_total")

        supa.table("zip_coverage_v3").update({
            "current_call_now_count": cn,
            "updated_at":              datetime.now(timezone.utc).isoformat(),
        }).eq("zip_code", zip_code).execute()

        _set_step(zip_code, "refresh_counts", "ok",
                  f"call_now={cn}, build_now={bn}, build_now_total={bn_total}")
    except Exception as e:
        _set_step(zip_code, "refresh_counts", "failed", f"{type(e).__name__}: {e}")
        raise


# ─── Top-level orchestrator ──────────────────────────────────────────────────

async def run_onboarding(
    zip_code: str,
    json_path: str,
    market_key: str = "WA_KING",
    city: str = "Bellevue",
    state: str = "WA",
):
    """
    Run the full onboarding pipeline for a ZIP. Call as an asyncio task.

    Idempotent: re-running on a partially-onboarded ZIP picks up where
    it left off. Each step's underlying cmd_* function is itself
    idempotent.

    Args:
        zip_code:    5-digit ZIP
        json_path:   absolute path to wa-king-{zip}-owners.json
        market_key:  WA_KING / WA_SNOHOMISH (sets canonicalizer rules)
        city, state: defaults for parcels_v3 rows
    """
    state_dict = _STATE.setdefault(zip_code, {})
    state_dict.update({
        "zip_code":   zip_code,
        "state":      "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps":      {s: "pending" for s in PIPELINE_STEPS},
        "logs":       [],
        "json_path":  json_path,
        "market_key": market_key,
    })

    log.info(f"[onboard {zip_code}] starting pipeline")
    t_start = time.time()

    try:
        # Step 1: register
        log.info(f"[onboard {zip_code}] step 1/6: register")
        await _step_register(zip_code, market_key, city, state, json_path)

        # Step 2: seed
        log.info(f"[onboard {zip_code}] step 2/6: seed")
        await _step_seed(zip_code, json_path)

        # Step 3: canonicalize  (the slow step — wall-clock dominates here;
        # cost ~$0.0005/parcel ≈ $4-9 per typical KC ZIP at Haiku 4.5 pricing)
        log.info(f"[onboard {zip_code}] step 3/6: canonicalize (slow)")
        await _step_canonicalize(zip_code)

        # Step 4: classify archetypes
        log.info(f"[onboard {zip_code}] step 4/6: classify")
        await _step_classify(zip_code)

        # Step 5: band assignment
        log.info(f"[onboard {zip_code}] step 5/6: band")
        await _step_band(zip_code)

        # Step 6: refresh snapshot counts
        log.info(f"[onboard {zip_code}] step 6/6: refresh_counts")
        await _step_refresh_counts(zip_code)

        elapsed = time.time() - t_start
        state_dict["state"] = "completed"
        state_dict["completed_at"] = datetime.now(timezone.utc).isoformat()
        state_dict["elapsed_sec"] = round(elapsed, 1)
        log.info(f"[onboard {zip_code}] ✓ completed in {elapsed:.0f}s")
    except Exception as e:
        elapsed = time.time() - t_start
        state_dict["state"] = "failed"
        state_dict["failed_at"] = datetime.now(timezone.utc).isoformat()
        state_dict["error"] = f"{type(e).__name__}: {e}"
        state_dict["elapsed_sec"] = round(elapsed, 1)
        log.error(f"[onboard {zip_code}] ✗ failed after {elapsed:.0f}s: {e}")
        # Don't re-raise — task ran in background, errors propagate via state
