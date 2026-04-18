"""
ZIP gate — FastAPI dependency that enforces coverage on every ZIP-scoped endpoint.

Usage:
    from backend.api.zip_gate import require_live_zip

    @router.get("/{zip_code}", dependencies=[Depends(require_live_zip)])
    async def get_something(zip_code: str):
        ...

If the ZIP is not in zip_coverage_v3 with status='live', returns 404 with
a clear message. No ZIP can be queried without being explicitly added to
coverage — this prevents the class of bugs where partial data leaks
through for a ZIP that was never intentionally built out.

Cache: ZIP coverage is cached in-memory for 60 seconds to avoid hitting
Supabase on every request. Invalidation happens automatically on TTL.
"""
from __future__ import annotations
import time
from typing import Optional
from fastapi import HTTPException, Path
from backend.api.db import get_supabase_client


# ── Cache ──────────────────────────────────────────────────────────────
# Simple in-memory cache keyed by zip_code. Maps to a (status, expires_at)
# tuple. 60-second TTL is short enough that status changes propagate
# quickly but long enough to avoid DB pressure under normal load.
_zip_status_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 60


def _cached_status(zip_code: str) -> Optional[str]:
    """Check the cache. Returns None if missing or expired."""
    entry = _zip_status_cache.get(zip_code)
    if entry is None:
        return None
    status, expires_at = entry
    if time.time() > expires_at:
        _zip_status_cache.pop(zip_code, None)
        return None
    return status


def _cache_status(zip_code: str, status: str) -> None:
    _zip_status_cache[zip_code] = (status, time.time() + _CACHE_TTL_SECONDS)


def invalidate_zip_cache(zip_code: Optional[str] = None) -> None:
    """
    Manually invalidate cache. Useful after coverage status changes
    (e.g., after a ZIP flips from in_development to live).
    """
    if zip_code:
        _zip_status_cache.pop(zip_code, None)
    else:
        _zip_status_cache.clear()


# ── Core lookup ────────────────────────────────────────────────────────

def get_zip_status(zip_code: str) -> Optional[str]:
    """
    Returns coverage status string or None if ZIP doesn't exist in coverage.

    Possible values: 'in_development' | 'live' | 'paused' | 'archived' | None
    """
    cached = _cached_status(zip_code)
    if cached is not None:
        return cached

    supa = get_supabase_client()
    if supa is None:
        # Dev mode fail-open: if Supabase isn't available, allow requests
        # through rather than crashing. Logged for visibility.
        print(f'[zip_gate] Supabase unavailable — allowing {zip_code} through')
        return 'live'

    try:
        result = (supa.table('zip_coverage_v3')
                  .select('status')
                  .eq('zip_code', zip_code)
                  .maybe_single()
                  .execute())
        row = result.data if result else None
        status = row['status'] if row else None

        if status:
            _cache_status(zip_code, status)
        return status
    except Exception as e:
        print(f'[zip_gate] lookup error for {zip_code}: {e}')
        return None


# ── FastAPI dependencies ───────────────────────────────────────────────

async def require_live_zip(zip_code: str = Path(..., regex=r'^\d{5}$')) -> str:
    """
    Dependency: allow only ZIPs with status='live'.
    Use on public-facing endpoints (briefings, map, parcels).
    """
    status = get_zip_status(zip_code)

    if status is None:
        raise HTTPException(
            404,
            detail={
                'error': 'zip_not_covered',
                'zip': zip_code,
                'message': (
                    f"ZIP {zip_code} is not currently covered by SellerSignal. "
                    f"Covered ZIPs are listed at /api/coverage."
                ),
            },
        )

    if status != 'live':
        raise HTTPException(
            404,
            detail={
                'error': 'zip_not_live',
                'zip': zip_code,
                'current_status': status,
                'message': (
                    f"ZIP {zip_code} exists in coverage but is not live "
                    f"(current status: {status}). Contact support if you "
                    f"believe this is an error."
                ),
            },
        )

    return zip_code


async def require_any_coverage(zip_code: str = Path(..., regex=r'^\d{5}$')) -> str:
    """
    Dependency: allow any ZIP that exists in coverage, regardless of status.
    Use on admin/internal endpoints that need to access in-development ZIPs.
    """
    status = get_zip_status(zip_code)
    if status is None:
        raise HTTPException(
            404,
            detail={'error': 'zip_not_covered', 'zip': zip_code},
        )
    return zip_code
