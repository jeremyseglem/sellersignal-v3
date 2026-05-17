"""
ZIP onboarding orchestrator — single end-to-end pipeline for adding a ZIP.

Background:
After ZIP #15 we kept hitting different variations of the same problem:
manually orchestrating 8-15 admin endpoints in the right order, with
silent failures, broken pipes, and partial completions that looked
identical to successes. Each new ZIP became 30-60 minutes of debugging.

This module collapses that into one function. The pipeline:

  1. register     — create zip_coverage_v3 row (status=in_development)
  2. seed         — load parcels_v3 from data/seeds/wa-king-{zip}-owners.json
                    (writes owner_name, last_transfer_date, tenure_years,
                     value, address, owner_type)
  3. classify     — assign signal_family archetype based on owner_type
                    + tenure_years + value patterns (zero-API,
                    reads parcels_v3 directly)
  4. band         — assign Band 0-4 based on archetype + hard
                    disqualifiers (institutional, brokerage, etc.)
  5. refresh_counts — compute zip_coverage_v3.current_call_now_count
                    snapshot before publication
  6. publish      — flip status from in_development to live; ZIP is
                    now claimable + visible + Build Now leads render
  ─── ZIP IS LIVE FOR BUILD NOW HERE — agents can use it ───
  7. canonicalize — parse owner_name into owner_canonical_v3 via Haiku 4.5
                    (best-effort; ~$0.50 per 1k parcels ≈ $4-9 per ZIP.
                     Used only by the probate-matcher for Call Now leads;
                     Build Now / Tier-2 archetypes do NOT depend on it.)
  ─── Call Now data fills in as canonicalize completes + rematch ticks ───

Pipeline state semantics:
  - "running"                     — actively executing steps 1-7
  - "completed"                   — all 7 steps succeeded; canonicalize done
  - "live_canonicalize_pending"   — steps 1-6 succeeded, canonicalize was
                                    deferred (another ZIP was canonicalizing).
                                    ZIP is live; canonicalize will run when
                                    re-triggered or via background autofill.
  - "live_canonicalize_failed"    — steps 1-6 succeeded, canonicalize itself
                                    failed (rate limit, connection storm,
                                    deploy mid-run). ZIP is live; canonicalize
                                    can be retried out-of-band.
  - "failed"                      — pre-publish step failed; ZIP is NOT live.

The key invariant: anything pre-publish failing means ZIP didn't go live.
Anything post-publish failing means ZIP is live and the failure is recoverable
without affecting agent-visible state.

NOT included (separate concerns):
  - rematch_autofill — global operation, not per-ZIP
  - obit harvest — global, runs on its own 12h cadence
  - tax foreclosure ingest — TBD, separate signal source
  - canonicalize_autofill — TODO: background task to process
    live_canonicalize_pending ZIPs without re-triggering the orchestrator

Architecture:
  - Runs as an asyncio task started from the admin endpoint
  - Each step is idempotent — re-running picks up where it left off
  - Status tracked in module-level _STATE dict, served by /onboard-status
  - Each step uses the existing cmd_* functions from zip_builder
  - Canonicalize uses backfill_zip directly (synchronous in-process,
    NOT the canonicalize-all endpoint which returns immediately and
    spawns a separate background task that gets killed by deploys)
  - Concurrency guard on canonicalize: only one ZIP canonicalizes at a
    time per Railway instance; others defer to live_canonicalize_pending.
    Prevents the Supabase-connection-storm pattern (5 parallel
    canonicalize jobs × concurrency=10 = 50 concurrent connections).

Failure handling:
  - Transient (Supabase broken pipe, etc.) → retry up to 3x with backoff
  - Hard error in steps 1-6 → mark step failed, halt pipeline, state=failed
  - Hard error in step 7 → ZIP is already live, state=live_canonicalize_failed

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

# Process-wide lock around the canonicalize step. Only one ZIP canonicalizes
# at a time per Railway instance — see "Concurrency guard" in the module
# docstring. When held, other ZIPs' canonicalize attempts skip cleanly and
# mark themselves as "deferred" rather than queuing or fighting for the
# Supabase connection pool.
_CANONICALIZE_LOCK = asyncio.Lock()

# Pipeline step names in order
PIPELINE_STEPS = [
    "register",
    "seed",
    "classify",
    "band",
    "refresh_counts",
    "publish",
    "canonicalize",
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

    Concurrency guard: only one ZIP canonicalizes at a time per Railway
    instance. If another ZIP currently holds _CANONICALIZE_LOCK, this
    step marks itself "deferred" and returns cleanly without raising.
    The orchestrator caller is responsible for translating "deferred"
    into the live_canonicalize_pending end-state.

    This step keeps the canonicalize work bound to this onboarding task
    instead of spawning a separate background loop that gets killed by
    deploys.
    """
    from backend.ingest.backfill_owner_canonical import backfill_zip

    # Concurrency guard. asyncio is cooperative single-threaded, so the
    # locked() check and the subsequent acquire run atomically (no await
    # between them = no other coroutine can run between them).
    if _CANONICALIZE_LOCK.locked():
        _set_step(zip_code, "canonicalize", "deferred",
                  "Another ZIP is canonicalizing on this instance; "
                  "deferred to avoid Supabase connection storm. "
                  "Re-trigger this ZIP or wait for canonicalize_autofill.")
        log.info(f"[onboard {zip_code}] canonicalize deferred (lock held by other ZIP)")
        return

    async with _CANONICALIZE_LOCK:
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


async def _step_publish(zip_code: str):
    """
    Flip zip_coverage_v3.status from 'in_development' to 'live'.

    After this step succeeds, the ZIP is visible in /api/coverage,
    claimable by agents, and serves real briefings. Build Now / Tier-2
    leads render immediately because the classifier reads parcels_v3
    directly and has no dependency on canonicalize/owner_canonical_v3.

    Uses force=True because the legacy investigated_count safety check
    in cmd_publish is irrelevant to this product (SerpAPI investigation
    is the old Option-A pipeline; not used in the v3 harvester model).
    This matches the pattern in scripts/onboard_kc_zips.sh which has
    always used --force.

    Idempotent: if already live, cmd_publish returns 0 as a no-op.
    """
    from backend.ingest.zip_builder import cmd_publish

    def _run():
        return _capture_stdout(cmd_publish, zip_code, force=True)

    rc, output = await _retry(
        lambda: asyncio.to_thread(_run), label="publish",
    )
    _set_step(zip_code, "publish", "ok" if rc == 0 else "failed",
              output.strip()[-500:] if output else None)
    if rc != 0:
        raise RuntimeError(f"publish failed: {output}")


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

    # ── Phase 1: pre-publish (steps 1-6). Failure here = ZIP is NOT live. ──
    try:
        # Step 1: register
        log.info(f"[onboard {zip_code}] step 1/7: register")
        await _step_register(zip_code, market_key, city, state, json_path)

        # Step 2: seed parcels_v3 from the bulk JSON
        log.info(f"[onboard {zip_code}] step 2/7: seed")
        await _step_seed(zip_code, json_path)

        # Step 3: classify archetypes (zero-API, reads parcels_v3 directly)
        log.info(f"[onboard {zip_code}] step 3/7: classify")
        await _step_classify(zip_code)

        # Step 4: band assignment (zero-API, deterministic)
        log.info(f"[onboard {zip_code}] step 4/7: band")
        await _step_band(zip_code)

        # Step 5: compute snapshot counts BEFORE publishing so the territory
        # popup shows correct numbers the moment the ZIP goes live
        log.info(f"[onboard {zip_code}] step 5/7: refresh_counts")
        await _step_refresh_counts(zip_code)

        # Step 6: flip status=live. ZIP is now visible, claimable, and
        # rendering Build Now / Tier-2 leads. The moment this returns,
        # agents can use this territory.
        log.info(f"[onboard {zip_code}] step 6/7: publish (ZIP goes live)")
        await _step_publish(zip_code)
    except Exception as e:
        # Pre-publish failure — ZIP is NOT live. No special handling needed
        # beyond marking the orchestration state and returning.
        elapsed = time.time() - t_start
        state_dict["state"] = "failed"
        state_dict["failed_at"] = datetime.now(timezone.utc).isoformat()
        state_dict["error"] = f"{type(e).__name__}: {e}"
        state_dict["elapsed_sec"] = round(elapsed, 1)
        log.error(f"[onboard {zip_code}] ✗ pre-publish failure after {elapsed:.0f}s: {e}")
        return  # don't proceed to canonicalize

    # ── Phase 2: post-publish (step 7). ZIP is already live; canonicalize is
    # best-effort. Failure or deferral here does NOT undo the live state. ──
    log.info(f"[onboard {zip_code}] step 7/7: canonicalize (best-effort, ZIP already live)")
    try:
        await _step_canonicalize(zip_code)
        canon_status = (state_dict.get("steps") or {}).get("canonicalize")
        elapsed = time.time() - t_start
        if canon_status == "ok":
            state_dict["state"] = "completed"
            state_dict["completed_at"] = datetime.now(timezone.utc).isoformat()
            state_dict["elapsed_sec"] = round(elapsed, 1)
            log.info(f"[onboard {zip_code}] ✓ completed in {elapsed:.0f}s")
        elif canon_status == "deferred":
            state_dict["state"] = "live_canonicalize_pending"
            state_dict["live_at"] = state_dict.get("live_at") or \
                datetime.now(timezone.utc).isoformat()
            state_dict["elapsed_sec"] = round(elapsed, 1)
            log.info(f"[onboard {zip_code}] live; canonicalize deferred "
                     f"(another ZIP holds the lock)")
        else:
            # Shouldn't happen — _step_canonicalize either sets ok/deferred
            # or raises. Defensive fallback.
            state_dict["state"] = "live_canonicalize_unknown"
            log.warning(f"[onboard {zip_code}] live; canonicalize state unclear: "
                        f"{canon_status!r}")
    except Exception as canon_exc:
        # Canonicalize itself raised (rate limit, connection storm, deploy
        # mid-run, etc.). ZIP is still live — publish already flipped it.
        elapsed = time.time() - t_start
        state_dict["state"] = "live_canonicalize_failed"
        state_dict["live_at"] = state_dict.get("live_at") or \
            datetime.now(timezone.utc).isoformat()
        state_dict["canonicalize_error"] = f"{type(canon_exc).__name__}: {canon_exc}"
        state_dict["elapsed_sec"] = round(elapsed, 1)
        log.error(f"[onboard {zip_code}] live; canonicalize failed after "
                  f"{elapsed:.0f}s: {canon_exc}")
        # Don't re-raise — task ran in background, errors propagate via state
