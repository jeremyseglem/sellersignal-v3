"""
Supabase client singleton.

Uses the service-role key server-side. Never expose the service key to
the browser — the frontend uses the anon key via user sessions.
"""
import os
from functools import lru_cache
from typing import Optional

import httpx


def _force_http1_pool() -> None:
    """Make PostgREST use HTTP/1.1 with a real connection pool.

    postgrest 0.17.2 hardcodes ``http2=True`` in ``create_session``, so
    EVERY API request handler and ALL background tasks multiplex over a
    SINGLE HTTP/2 connection to Supabase. When that one connection goes
    bad — stream exhaustion under task load, or a server GOAWAY — every
    subsequent request through the shared client fails with
    ``ConnectionTerminated`` or ``Invalid input StreamInputs.SEND_HEADERS
    in state N``. That took every briefing (and the map + dossier, which
    hit the same backend) to HTTP 500 on 2026-07-22, and is the recurring
    "background-task contention" in Active Issues #11.

    HTTP/1.1 gives httpx a pool of independent connections: a broken
    connection fails one request instead of poisoning the process. This
    is a pure transport change — PostgREST behaves identically over 1.1.
    """
    try:
        from postgrest._sync.client import SyncPostgrestClient, SyncClient
    except ImportError:
        return
    if getattr(SyncPostgrestClient, "_ss_http1_patched", False):
        return

    def create_session(self, base_url, headers, timeout, verify=True,
                       proxy=None):
        return SyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            verify=verify,
            proxy=proxy,
            follow_redirects=True,
            http2=False,
            limits=httpx.Limits(max_connections=40,
                                max_keepalive_connections=20,
                                keepalive_expiry=30.0),
        )

    SyncPostgrestClient.create_session = create_session
    SyncPostgrestClient._ss_http1_patched = True
    print('[db] PostgREST transport pinned to HTTP/1.1 (pooled)')


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

    _force_http1_pool()
    return create_client(url, key)


def supabase_available() -> bool:
    return get_supabase_client() is not None
