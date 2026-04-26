"""
Onboarding endpoint — kicks off the full ZIP build pipeline for a
batch of King County ZIPs.

Replaces the standalone scripts/onboard_kc_zips.sh runbook with a
backend endpoint so onboarding can be triggered with one curl
against the live Railway deploy. The container has Python, the
Supabase service key, and clean network egress to KC ArcGIS — all
the ingredients the script needs.

Endpoints:
  POST /api/admin/onboard-zips           — kick off the pipeline
  GET  /api/admin/onboard-zips/status    — read current job status

Both gated by the X-Admin-Key header (existing pattern, see
admin.py: require_admin).

Design notes:
- Pipeline stages run sequentially per ZIP: register, ingest,
  geocode, classify, band, publish (--force). Skips SerpAPI
  investigate — confirmed via audit that no agent-visible field
  in the dossier depends on SerpAPI data.
- Job state lives in a module-level dict, not the database. One
  job can run at a time; second POST while one is in-flight gets
  a 409. State is lost on container restart, but that's fine —
  the underlying work is idempotent (rerun is safe) and the GET
  endpoint exists for live polling, not historical record.
- Each stage is wrapped in a try/except so a failure on one ZIP
  doesn't kill the whole batch. The job state tracks per-ZIP
  per-stage outcomes.
- Runs in a FastAPI BackgroundTask so the POST returns
  immediately. Estimated total runtime: 25-40 minutes for 10 ZIPs
  depending on parcel counts.
"""
import asyncio
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from backend.api.admin import require_admin

router = APIRouter()


# ── Job roster ──────────────────────────────────────────────────
# 10 King County ZIPs to onboard. Tier-organized for prioritization
# if the job is split or partially restarted: Tier 1 finishes first
# so even a partial completion gives the highest-value coverage.
DEFAULT_ZIP_ROSTER: List[Dict[str, str]] = [
    # Tier 1 — Eastside luxury
    {"zip": "98039", "city": "Medina"},
    {"zip": "98040", "city": "Mercer Island"},
    {"zip": "98033", "city": "Kirkland"},
    {"zip": "98006", "city": "Bellevue"},
    # Tier 2 — Eastside extension
    {"zip": "98052", "city": "Redmond"},
    {"zip": "98005", "city": "Bellevue"},
    {"zip": "98007", "city": "Bellevue"},
    # Tier 3 — Seattle SFH pockets
    {"zip": "98112", "city": "Seattle"},
    {"zip": "98199", "city": "Seattle"},
    {"zip": "98105", "city": "Seattle"},
]

PIPELINE_STAGES = ["register", "ingest", "classify", "band", "publish"]
# Skipped: geocode. KC ArcGIS parcels already arrive with LAT/LON
# attributes (see arcgis.py:_parse_feature). cmd_geocode is a stub
# that returns 2 unconditionally (NOT YET IMPLEMENTED), so including
# it would fail every ZIP. When a non-KC market is added that needs
# real geocoding, implement cmd_geocode and add 'geocode' back here
# (or make it conditional on market_key).


# ── Job state (module-level, single job at a time) ──────────────
# Locked because BackgroundTask + GET status can race.
_job_lock = threading.Lock()
_current_job: Optional[Dict[str, Any]] = None


def _new_job(roster: List[Dict[str, str]]) -> Dict[str, Any]:
    """Initialize a fresh job-state dict for the given roster."""
    return {
        "started_at":    datetime.now(timezone.utc).isoformat(),
        "completed_at":  None,
        "status":        "running",   # running | complete | failed
        "roster":        [r["zip"] for r in roster],
        "current_zip":   None,
        "current_stage": None,
        # zips: { "98039": { "register": "ok", "ingest": "ok", ... } }
        "zips":          {r["zip"]: {} for r in roster},
        "errors":        [],          # list of {"zip": ..., "stage": ..., "error": ...}
    }


def _get_job_snapshot() -> Optional[Dict[str, Any]]:
    """Thread-safe copy of current job state (or None if no job)."""
    with _job_lock:
        if _current_job is None:
            return None
        # Shallow copy is enough — caller doesn't mutate.
        return dict(_current_job, zips=dict(_current_job["zips"]),
                    errors=list(_current_job["errors"]))


def _update_job(updates: Dict[str, Any]) -> None:
    with _job_lock:
        if _current_job is not None:
            _current_job.update(updates)


def _record_stage(zip_code: str, stage: str, outcome: str, error: Optional[str] = None) -> None:
    """Mark a stage outcome on the job state. outcome ∈ {ok, failed, skipped}."""
    with _job_lock:
        if _current_job is None:
            return
        _current_job["zips"].setdefault(zip_code, {})[stage] = outcome
        _current_job["current_zip"]   = zip_code
        _current_job["current_stage"] = stage
        if outcome == "failed" and error:
            _current_job["errors"].append({
                "zip":   zip_code,
                "stage": stage,
                "error": error,
            })


# ── Pipeline execution ─────────────────────────────────────────
# Each stage maps to a cmd_* function in backend.ingest.zip_builder.
# We import inside the function so the import cost (and any optional
# dependencies the zip_builder module pulls in) only hits when an
# onboarding actually runs — not on every container boot.

def _run_stage(stage: str, zip_code: str, city: str) -> int:
    """Run one stage for one ZIP. Returns 0 on success, non-zero on failure."""
    from backend.ingest.zip_builder import (
        cmd_register, cmd_ingest,
        cmd_classify, cmd_band, cmd_publish,
    )

    if stage == "register":
        # Idempotent: skips if zip already registered.
        return cmd_register(zip_code, market_key="WA_KING", city=city, state="WA")

    if stage == "ingest":
        return cmd_ingest(zip_code)

    if stage == "classify":
        return cmd_classify(zip_code)

    if stage == "band":
        return cmd_band(zip_code)

    if stage == "publish":
        # --force bypasses the first_investigation_at gate. We're
        # intentionally skipping the SerpAPI investigate step
        # because it adds no agent-visible value (verified).
        return cmd_publish(zip_code, force=True)

    raise ValueError(f"Unknown stage: {stage}")


def _run_onboarding(roster: List[Dict[str, str]]) -> None:
    """Sequential build pipeline. Mutates _current_job as it runs.
    Designed to be called inside a BackgroundTask.
    """
    try:
        for entry in roster:
            zip_code = entry["zip"]
            city     = entry["city"]

            for stage in PIPELINE_STAGES:
                try:
                    rc = _run_stage(stage, zip_code, city)
                    if rc == 0:
                        _record_stage(zip_code, stage, "ok")
                    else:
                        _record_stage(zip_code, stage, "failed",
                                      f"cmd returned {rc}")
                        # Stop further stages for this ZIP — but
                        # continue with the next ZIP. Partial
                        # progress is fine; we'd rather get 9/10
                        # ZIPs onboarded than block on one bad one.
                        break
                except Exception as e:
                    err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                    _record_stage(zip_code, stage, "failed", err)
                    break

        _update_job({
            "status":       "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_zip":   None,
            "current_stage": None,
        })
    except Exception as e:
        # Catastrophic failure (something outside per-ZIP try/except).
        # Record so the GET endpoint can surface it.
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _update_job({
            "status":       "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "errors":       (_get_job_snapshot() or {}).get("errors", []) + [
                {"zip": "*", "stage": "outer", "error": err},
            ],
        })


# ── Endpoints ──────────────────────────────────────────────────

class OnboardRequest(BaseModel):
    """Optional override for the ZIP roster. When omitted, uses the
    DEFAULT_ZIP_ROSTER above. Lets us re-run for individual ZIPs
    after a failure without redeploying."""
    zips: Optional[List[Dict[str, str]]] = None


@router.post("/onboard-zips", dependencies=[Depends(require_admin)])
async def onboard_zips(
    body: Optional[OnboardRequest] = None,
    background_tasks: BackgroundTasks = None,
):
    """Kick off the build pipeline for the configured ZIP roster.

    Returns immediately with the initial job state. Poll
    GET /api/admin/onboard-zips/status to track progress.

    Returns 409 if a job is already running.
    """
    global _current_job

    roster = (body.zips if body and body.zips else DEFAULT_ZIP_ROSTER)
    # Validate: each entry needs zip + city
    for r in roster:
        if not r.get("zip") or not r.get("city"):
            raise HTTPException(400,
                f"Each roster entry needs both 'zip' and 'city'. Got: {r}")

    with _job_lock:
        if _current_job is not None and _current_job.get("status") == "running":
            raise HTTPException(409,
                "An onboarding job is already running. Poll "
                "/api/admin/onboard-zips/status for progress.")
        _current_job = _new_job(roster)

    # Schedule the actual work as a background task. FastAPI runs
    # this after the response is sent.
    background_tasks.add_task(_run_onboarding, roster)

    snap = _get_job_snapshot()
    return {
        "ok":          True,
        "message":     f"Onboarding started for {len(roster)} ZIPs.",
        "estimated_runtime_minutes": len(roster) * 3,
        "poll_url":    "/api/admin/onboard-zips/status",
        "job":         snap,
    }


@router.get("/onboard-zips/status", dependencies=[Depends(require_admin)])
async def onboard_zips_status():
    """Snapshot of current onboarding job state. Returns 404 when no
    job has been started since the container last booted."""
    snap = _get_job_snapshot()
    if snap is None:
        raise HTTPException(404, "No onboarding job has been started yet.")
    return snap


# ── Hydrate-owners (eReal Property + reclassify + reband) ───────
# Onboarding's `ingest` stage pulls parcels from KC ArcGIS, but
# ArcGIS doesn't expose owner_name (KC filters it under RCW 42.56.
# 070(8)). The KC eRealProperty harvester scrapes the assessor's
# detail pages for the missing owner data — that's what populates
# parcels_v3.owner_name, which classify+band depend on to produce
# meaningful archetypes and scores.
#
# This endpoint runs that backfill across an entire ZIP roster,
# looping run_batch until the ZIP is fully covered, then re-runs
# classify+band on each ZIP so the now-populated owners drive
# real archetypes. Total wall time is hours (not minutes) because
# eRealProperty rate-limits at 1.2s/parcel — that's a deliberate
# good-citizen rate against KC's servers.
#
# Idempotent: TTL-based skipping in run_batch means re-running
# this endpoint won't re-scrape parcels already covered.

# Separate job state for hydrate so it can run in parallel with /
# alongside an onboarding job without colliding.
_hydrate_lock = threading.Lock()
_current_hydrate: Optional[Dict[str, Any]] = None


# Default hydrate roster includes the 10 onboarding ZIPs PLUS the
# already-live 98004, since 98004's owner coverage may also have
# gaps from earlier ingest runs.
DEFAULT_HYDRATE_ROSTER: List[str] = [
    "98004",  # Bellevue (already live, may need backfill)
    "98039", "98040", "98033", "98006",            # Tier 1
    "98052", "98005", "98007",                     # Tier 2
    "98112", "98199", "98105",                     # Tier 3
]

# How many parcels per run_batch call. Keep under Railway's 5-min
# proxy cap; 100 parcels at 1.2s each = ~2 minutes per batch with
# parse + DB write overhead.
BATCH_LIMIT = 100

# Hard cap on batches per ZIP so a runaway loop doesn't burn forever.
# Math: largest KC ZIP we touch is 98052 Redmond at ~15,500 parcels.
# 100 parcels per batch = 155 batches needed. Cap at 250 to give
# headroom for retries on transient failures without allowing
# unbounded loops.
MAX_BATCHES_PER_ZIP = 250


def _new_hydrate_job(roster: List[str]) -> Dict[str, Any]:
    return {
        "started_at":    datetime.now(timezone.utc).isoformat(),
        "completed_at":  None,
        "status":        "running",
        "roster":        list(roster),
        "current_zip":   None,
        "current_phase": None,        # 'ereal' | 'classify' | 'band'
        # zips: { '98039': { 'ereal_batches': 4, 'parcels_fetched': 412,
        #                     'classify': 'ok', 'band': 'ok' } }
        "zips":          {z: {"ereal_batches": 0, "parcels_fetched": 0} for z in roster},
        "errors":        [],
    }


def _hydrate_snapshot() -> Optional[Dict[str, Any]]:
    with _hydrate_lock:
        if _current_hydrate is None:
            return None
        return dict(
            _current_hydrate,
            zips=dict(_current_hydrate["zips"]),
            errors=list(_current_hydrate["errors"]),
        )


def _hydrate_update(updates: Dict[str, Any]) -> None:
    with _hydrate_lock:
        if _current_hydrate is not None:
            _current_hydrate.update(updates)


def _hydrate_record(zip_code: str, key: str, value: Any) -> None:
    with _hydrate_lock:
        if _current_hydrate is None:
            return
        _current_hydrate["zips"].setdefault(zip_code, {})[key] = value


def _hydrate_error(zip_code: str, phase: str, error: str) -> None:
    with _hydrate_lock:
        if _current_hydrate is None:
            return
        _current_hydrate["errors"].append({
            "zip": zip_code, "phase": phase, "error": error,
        })


def _run_hydrate(roster: List[str]) -> None:
    """For each ZIP: loop run_batch until done, then reclassify + reband."""
    try:
        from backend.api.db import get_supabase_client
        from backend.harvesters.ereal_property import run_batch
        from backend.ingest.zip_builder import cmd_classify, cmd_band

        supa = get_supabase_client()
        if supa is None:
            _hydrate_update({
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            _hydrate_error("*", "init", "Supabase client not configured")
            return

        for zip_code in roster:
            _hydrate_update({"current_zip": zip_code, "current_phase": "ereal"})

            # Phase 1: loop run_batch until the ZIP returns 0 candidates.
            # run_batch returns {fetched: N, ...}. When fetched < limit
            # we're at the tail; we'll call once more to confirm 0.
            batch_count = 0
            total_fetched = 0
            consecutive_zero = 0
            while batch_count < MAX_BATCHES_PER_ZIP:
                try:
                    result = run_batch(
                        supa=supa,
                        zip_code=zip_code,
                        limit=BATCH_LIMIT,
                        ttl_days=30,
                        force=False,
                    )
                    fetched = int(result.get("fetched") or 0)
                    batch_count += 1
                    total_fetched += fetched
                    _hydrate_record(zip_code, "ereal_batches", batch_count)
                    _hydrate_record(zip_code, "parcels_fetched", total_fetched)

                    if fetched == 0:
                        consecutive_zero += 1
                        if consecutive_zero >= 2:
                            # Two empty batches in a row — we're done with
                            # this ZIP. (One can be a transient skip-window;
                            # two confirms exhaustion.)
                            break
                    else:
                        consecutive_zero = 0
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                    _hydrate_error(zip_code, "ereal", err)
                    # Don't break — eReal failures are usually transient
                    # (KC rate-limit, parser edge case). Try the next batch.
                    batch_count += 1
                    if batch_count >= 5 and total_fetched == 0:
                        # If first 5 batches all error and nothing fetched,
                        # something is structurally broken — give up on this ZIP.
                        _hydrate_record(zip_code, "ereal_status", "failed")
                        break

            _hydrate_record(zip_code, "ereal_status", "complete")

            # Phase 2: reclassify with the now-populated owner data.
            _hydrate_update({"current_phase": "classify"})
            try:
                rc = cmd_classify(zip_code)
                _hydrate_record(zip_code, "classify",
                                "ok" if rc == 0 else f"failed (rc={rc})")
                if rc != 0:
                    _hydrate_error(zip_code, "classify", f"cmd returned {rc}")
            except Exception as e:
                _hydrate_record(zip_code, "classify", "failed")
                _hydrate_error(zip_code, "classify",
                               f"{type(e).__name__}: {e}")

            # Phase 3: reband.
            _hydrate_update({"current_phase": "band"})
            try:
                rc = cmd_band(zip_code)
                _hydrate_record(zip_code, "band",
                                "ok" if rc == 0 else f"failed (rc={rc})")
                if rc != 0:
                    _hydrate_error(zip_code, "band", f"cmd returned {rc}")
            except Exception as e:
                _hydrate_record(zip_code, "band", "failed")
                _hydrate_error(zip_code, "band",
                               f"{type(e).__name__}: {e}")

        _hydrate_update({
            "status":        "complete",
            "completed_at":  datetime.now(timezone.utc).isoformat(),
            "current_zip":   None,
            "current_phase": None,
        })

    except Exception as e:
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _hydrate_update({
            "status":       "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        _hydrate_error("*", "outer", err)


class HydrateRequest(BaseModel):
    zips: Optional[List[str]] = None


@router.post("/hydrate-owners", dependencies=[Depends(require_admin)])
async def hydrate_owners(
    body: Optional[HydrateRequest] = None,
    background_tasks: BackgroundTasks = None,
):
    """Run eRealProperty owner backfill across the ZIP roster, then
    reclassify + reband each ZIP. Long-running (hours) — returns
    immediately with job state. Poll /hydrate-owners/status.
    """
    global _current_hydrate
    roster = (body.zips if body and body.zips else DEFAULT_HYDRATE_ROSTER)

    with _hydrate_lock:
        if _current_hydrate is not None and _current_hydrate.get("status") == "running":
            raise HTTPException(409,
                "A hydrate job is already running. Poll "
                "/api/admin/hydrate-owners/status for progress.")
        _current_hydrate = _new_hydrate_job(roster)

    background_tasks.add_task(_run_hydrate, roster)

    snap = _hydrate_snapshot()
    return {
        "ok": True,
        "message": f"Owner hydration started for {len(roster)} ZIPs.",
        "estimated_hours": round(len(roster) * 2.5, 1),  # rough — depends on ZIP size
        "poll_url": "/api/admin/hydrate-owners/status",
        "job": snap,
    }


@router.get("/hydrate-owners/status", dependencies=[Depends(require_admin)])
async def hydrate_owners_status():
    """In-memory job state if a job is running. Falls back to a
    DB-derived snapshot when no in-memory job exists (e.g., after
    a container restart wiped the job state but the underlying
    work is still complete or in progress)."""
    snap = _hydrate_snapshot()
    if snap is not None:
        return snap
    # No in-memory job. Compute coverage from the database — this
    # is the ground truth for what eRealProperty has actually
    # populated. Returns same general shape so consumers don't
    # have to special-case the fallback.
    return _db_coverage_snapshot()


# ── DB-backed coverage status ──────────────────────────────────
# These endpoints don't care about job state at all. They read
# directly from parcels_v3 + parcel_ereal_meta_v3 to answer:
# "how many parcels in ZIP X have been hydrated by eReal?"
# Survives container restarts. Always accurate. The right way
# to ask "where is my hydration?" once you stop trusting in-
# memory job state.

def _zip_coverage(supa, zip_code: str) -> Dict[str, Any]:
    """Return per-ZIP coverage stats from the DB.

    Two counts:
      total      — parcels in parcels_v3 with this zip_code
      hydrated   — parcels with a parcel_ereal_meta_v3 row whose
                   fetched_at is non-null

    Coverage % = hydrated / total. >95% is effectively complete
    (some parcels persistently fail to fetch — KC server quirks,
    parser edge cases — and that's tracked separately on the meta
    table's last_error column).
    """
    # Total parcels in the ZIP.
    total_res = (
        supa.table('parcels_v3')
        .select('pin', count='exact', head=True)
        .eq('zip_code', zip_code)
        .execute()
    )
    total = total_res.count or 0

    # Hydrated parcels: parcel_ereal_meta_v3 rows joined to
    # parcels_v3 by pin, scoped to the ZIP. PostgREST doesn't do
    # arbitrary joins, but we can query the meta table for
    # fetched_at IS NOT NULL and intersect by paginating the pins.
    # Simpler approach: paginate the parcels_v3 pins for this ZIP,
    # then for each chunk count how many have meta rows with
    # fetched_at set.
    hydrated = 0
    PAGE_SIZE = 5000
    page = 0
    while True:
        start = page * PAGE_SIZE
        end   = start + PAGE_SIZE - 1
        page_res = (
            supa.table('parcels_v3')
            .select('pin')
            .eq('zip_code', zip_code)
            .range(start, end)
            .execute()
        )
        page_data = page_res.data or []
        if not page_data:
            break
        page_pins = [r['pin'] for r in page_data]

        # Count meta rows for this chunk where fetched_at is set.
        meta_res = (
            supa.table('parcel_ereal_meta_v3')
            .select('pin', count='exact', head=True)
            .in_('pin', page_pins)
            .not_.is_('fetched_at', 'null')
            .execute()
        )
        hydrated += (meta_res.count or 0)

        if len(page_data) < PAGE_SIZE:
            break
        page += 1
        if page > 20:
            break

    pct = round(100.0 * hydrated / total, 1) if total else 0.0
    return {
        "total":     total,
        "hydrated":  hydrated,
        "coverage_pct": pct,
    }


def _db_coverage_snapshot() -> Dict[str, Any]:
    """DB-derived snapshot in roughly the shape the in-memory hydrate
    job emits. Useful when the in-memory job is gone but the work
    is still relevant."""
    from backend.api.db import get_supabase_client

    supa = get_supabase_client()
    if supa is None:
        return {
            "source": "db",
            "status": "unknown",
            "error":  "Supabase client unavailable",
        }

    out = {}
    for zip_code in DEFAULT_HYDRATE_ROSTER:
        try:
            out[zip_code] = _zip_coverage(supa, zip_code)
        except Exception as e:
            out[zip_code] = {"error": f"{type(e).__name__}: {e}"}

    # Aggregate
    total_p = sum((v.get("total") or 0) for v in out.values() if isinstance(v, dict))
    total_h = sum((v.get("hydrated") or 0) for v in out.values() if isinstance(v, dict))
    overall_pct = round(100.0 * total_h / total_p, 1) if total_p else 0.0

    return {
        "source":           "db",
        "as_of":            datetime.now(timezone.utc).isoformat(),
        "roster":           list(DEFAULT_HYDRATE_ROSTER),
        "overall_total":    total_p,
        "overall_hydrated": total_h,
        "overall_pct":      overall_pct,
        "zips":             out,
    }


@router.get("/coverage-status", dependencies=[Depends(require_admin)])
async def coverage_status(zip_code: Optional[str] = None):
    """DB-backed coverage stats, independent of any in-memory job.

    With no query param: returns coverage for all 11 default-roster
    ZIPs. With ?zip_code=98033: returns just that ZIP.

    Reads from parcels_v3 + parcel_ereal_meta_v3 directly. Always
    accurate; survives container restarts; doesn't depend on
    whether a hydrate job is running."""
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase client unavailable")

    if zip_code:
        return {
            "zip_code": zip_code,
            "as_of":    datetime.now(timezone.utc).isoformat(),
            **_zip_coverage(supa, zip_code),
        }
    return _db_coverage_snapshot()
