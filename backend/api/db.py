"""
Supabase client singleton.

Uses the service-role key server-side. Never expose the service key to
the browser — the frontend uses the anon key via user sessions.
"""
import os
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def get_supabase_client():
    """Lazy-initialized Supabase client. Returns None if env missing (dev mode)."""
    try:
        from supabase import create_client, Client
    except ImportError:
        print('[warn] supabase-py not installed')
        return None

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')

    if not url or not key:
        print('[warn] SUPABASE_URL or SUPABASE_SERVICE_KEY missing — returning None')
        return None

    return create_client(url, key)


def supabase_available() -> bool:
    return get_supabase_client() is not None
