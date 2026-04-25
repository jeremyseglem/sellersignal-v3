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

PIPELINE_STAGES = ["register", "ingest", "geocode", "classify", "band", "publish"]


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
        cmd_register, cmd_ingest, cmd_geocode,
        cmd_classify, cmd_band, cmd_publish,
    )

    if stage == "register":
        # Idempotent: skips if zip already registered.
        return cmd_register(zip_code, market_key="WA_KING", city=city, state="WA")

    if stage == "ingest":
        return cmd_ingest(zip_code)

    if stage == "geocode":
        return cmd_geocode(zip_code)

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
