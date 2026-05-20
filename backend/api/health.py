"""Health + status endpoints."""
import os
from datetime import datetime, timezone
from fastapi import APIRouter

from backend.api.db import supabase_available

router = APIRouter()


@router.get("/health")
async def health():
    """Basic liveness check."""
    return {
        "status": "ok",
        "service": "sellersignal-v3",
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def status():
    """
    Detailed readiness check — lists which dependencies are connected.
    Useful during deploy to verify env vars are set.
    Does NOT return actual values, just yes/no flags.
    """
    return {
        "service": "sellersignal-v3",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": os.environ.get('ENVIRONMENT', 'development'),
        "dependencies": {
            "supabase":  supabase_available(),
            "serpapi":   bool(os.environ.get('SERPAPI_KEY')),
            "anthropic": bool(os.environ.get('ANTHROPIC_API_KEY')),
            "stripe":    bool(os.environ.get('STRIPE_SECRET_KEY')),
            "google_maps": bool(os.environ.get('GOOGLE_MAPS_API_KEY')),
        },
    }


@router.get("/config")
async def frontend_config():
    """
    Public runtime configuration for the SPA frontend.

    Returns the Supabase URL + anon key so the frontend can initialize
    its supabase-js client at runtime instead of relying on build-time
    Vite env-var injection. Previously the frontend baked these values
    into the JS bundle at `vite build` time; any rebuild done in an
    environment without VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY set
    silently produced an auth-broken bundle (the supabase client was
    initialized as null and every auth call hit a "not configured"
    fallback). See May 20, 2026 incident in MANIFESTO build journal.

    Both values returned here are PUBLIC by design:
      - `supabase_url` is a public project URL.
      - `supabase_anon_key` is the anon JWT — meant to be embedded in
        every browser. Row Level Security policies in Postgres enforce
        actual permissions; the anon key is just a routing token.

    Sensitive credentials (service_role key, admin key, third-party
    API keys) are NOT returned — they live only in Railway env vars
    accessible to the backend.

    No auth required. Cache-friendly on the client side (config rarely
    changes; frontend can cache in localStorage and refresh in the
    background).
    """
    return {
        "supabase_url":      os.environ.get('SUPABASE_URL', ''),
        "supabase_anon_key": os.environ.get('SUPABASE_ANON_KEY', ''),
    }
