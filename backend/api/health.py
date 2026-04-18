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
