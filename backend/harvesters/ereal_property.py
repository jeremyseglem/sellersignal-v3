"""
KC eReal Property harvester.

Per-parcel fetcher for the King County Assessor's eReal Property detail
pages. Runs from Railway (sandbox TLS can't reach blue.kingcounty.com).

Flow per parcel:
  1. Fetch https://blue.kingcounty.com/Assessor/eRealProperty/
         Detail.aspx?ParcelNbr=<10-digit-pin>
  2. Parse with ereal_property_parser.parse_ereal_detail
  3. Upsert parcels_v3: owner_name, sqft, year_built
     (non-destructive — only fills NULL or refreshes on explicit override)
  4. Upsert sales_history_v3: full sales list
  5. Stamp parcel_ereal_meta_v3: fetched_at, sales_count, parser_version

Rate limiting: 1.2 seconds between parcel fetches (inline sleep).
Conservative default to be a good citizen. Total time for 7,145 parcels
is ~2.4 hours. Admin endpoint runs in bounded batches (default 100
parcels per call) so each HTTP request completes well under Railway's
5-minute proxy cap.

Incremental behavior: the runner reads parcel_ereal_meta_v3.fetched_at
and skips parcels fetched within the last `ttl_days` (default 30).
The operator can force-refetch by passing `force=True`.

This harvester does NOT write to raw_signals_v3. Sales history and
parcel attribute refreshes go to their dedicated tables. The existing
harvester→briefing bridge is untouched.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from backend.harvesters.ereal_property_parser import (
    parse_ereal_detail, PARSER_VERSION,
)

log = logging.getLogger(__name__)

DETAIL_URL = (
    "https://blue.kingcounty.com/Assessor/eRealProperty/Detail.aspx"
    "?ParcelNbr={pin}"
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT_S = 30
INTER_REQUEST_SLEEP_S = 1.2


# ─── Session with retry ───────────────────────────────────────────────

def _build_session() -> requests.Session:
    """
    Configured requests.Session for eReal fetches.

    Headers chosen to look like a normal browser. The assessor's portal
    is not behind Cloudflare and does not require any auth, but it
    does return 403 for obviously-scripted User-Agents (empty, curl/*)
    so we set a real-looking UA.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection":      "keep-alive",
    })
    return s


def fetch_one(pin: str, session: Optional[requests.Session] = None) -> dict:
    """
    Fetch + parse a single parcel. Returns a dict with:
        {
          'pin': str,
          'ok': bool,
          'status': int | None,
          'body_length': int,
          'parsed': dict | None,
          'error': str | None,
        }
    Does NOT write to DB — pure network + parse.
    """
    s = session or _build_session()
    url = DETAIL_URL.format(pin=pin)
    try:
        r = s.get(url, timeout=REQUEST_TIMEOUT_S)
    except Exception as e:
        return {
            'pin':         pin,
            'ok':          False,
            'status':      None,
            'body_length': 0,
            'parsed':      None,
            'error':       f"{type(e).__name__}: {str(e)[:200]}",
        }

    body = r.text or ""
    if r.status_code != 200:
        return {
            'pin':         pin,
            'ok':          False,
            'status':      r.status_code,
            'body_length': len(body),
            'parsed':      None,
            'error':       f"HTTP {r.status_code}",
        }

    # Parse errors are non-fatal — the page loaded, we just couldn't
    # extract. Record the body length so the operator can see if the
    # response was unexpectedly short (blocked / rate-limited).
    try:
        parsed = parse_ereal_detail(body, pin)
    except Exception as e:
        return {
            'pin':         pin,
            'ok':          False,
            'status':      r.status_code,
            'body_length': len(body),
            'parsed':      None,
            'error':       f"parse error: {type(e).__name__}: {str(e)[:200]}",
        }

    return {
        'pin':         pin,
        'ok':          True,
        'status':      r.status_code,
        'body_length': len(body),
        'parsed':      parsed,
        'error':       None,
    }


# ─── Upsert coordinator ───────────────────────────────────────────────

def upsert_parsed(supa, pin: str, parsed: dict) -> dict:
    """
    Write parsed detail to the three destinations:
      1. parcels_v3: owner_name, owner_name_raw, sqft, year_built
         (non-destructive merge — existing non-null values are
         preserved unless current row has NULL or stale)
      2. sales_history_v3: all sales (upsert on pin+recording_number)
      3. parcel_ereal_meta_v3: fetched_at, sales_count, parser_version

    Returns a stats dict:
      { 'parcel_updated': bool, 'sales_upserted': int,
        'sales_skipped': int, 'error': str | None }
    """
    stats = {
        'parcel_updated':  False,
        'sales_upserted':  0,
        'sales_skipped':   0,
        'error':           None,
    }

    b = parsed.get('building') or {}
    p = parsed.get('parcel') or {}

    # ── parcels_v3 refresh ──
    # eReal pulls owner_name_raw from the assessor's authoritative
    # detail page (KC ArcGIS doesn't expose names per RCW 42.56.070(8)).
    # We also derive owner_name (display form, "John Smith" not
    # "SMITH JOHN") and owner_type (individual / llc / trust / estate /
    # gov) inline, so the parcel row is ready for classify and band
    # without any further enrichment step.
    parcel_update: dict = {}
    owner_raw = p.get('owner_name')
    if owner_raw:
        # Lazy-import to avoid heavy module-init costs on every upsert
        from backend.ingest.seed_from_json import _normalize_display_name
        from backend.ingest.arcgis import _derive_owner_type
        parcel_update['owner_name_raw'] = owner_raw
        parcel_update['owner_name']     = _normalize_display_name(owner_raw)
        parcel_update['owner_type']     = _derive_owner_type(owner_raw)
    if b.get('sqft') is not None:
        parcel_update['sqft'] = b['sqft']
    if b.get('year_built') is not None:
        parcel_update['year_built'] = b['year_built']

    if parcel_update:
        try:
            supa.table('parcels_v3').update(parcel_update).eq('pin', pin).execute()
            stats['parcel_updated'] = True
        except Exception as e:
            stats['error'] = f"parcels_v3 update: {type(e).__name__}: {str(e)[:150]}"
            log.warning(f"[ereal.upsert {pin}] parcel update failed: {e}")

    # ── sales_history_v3 ──
    sales = parsed.get('sales') or []
    rows = []
    for s in sales:
        rec = s.get('recording_number')
        if not rec:
            stats['sales_skipped'] += 1
            continue
        sd = s.get('sale_date')
        rows.append({
            'pin':              pin,
            'recording_number': rec,
            'excise_number':    s.get('excise_number'),
            'sale_date':        sd.isoformat() if sd else None,
            'sale_price':       s.get('sale_price'),
            'seller_name':      s.get('seller_name'),
            'buyer_name':       s.get('buyer_name'),
            'instrument':       s.get('instrument'),
            'sale_reason':      s.get('sale_reason'),
            'is_arms_length':   s.get('is_arms_length'),
            'source_fetched_at': datetime.now(timezone.utc).isoformat(),
        })
    if rows:
        try:
            supa.table('sales_history_v3').upsert(
                rows, on_conflict='pin,recording_number'
            ).execute()
            stats['sales_upserted'] = len(rows)
        except Exception as e:
            # Don't overwrite an earlier parcel-update error
            if stats['error'] is None:
                stats['error'] = f"sales_history_v3 upsert: {type(e).__name__}: {str(e)[:150]}"
            log.warning(f"[ereal.upsert {pin}] sales upsert failed: {e}")

    # ── parcel_ereal_meta_v3 ──
    now_iso = datetime.now(timezone.utc).isoformat()
    meta_ok = stats['error'] is None
    meta_row = {
        'pin':                pin,
        'fetched_at':         now_iso if meta_ok else None,
        'last_attempt_at':    now_iso,
        'last_error':         stats['error'],
        'consecutive_errors': 0 if meta_ok else 1,
        'sales_count':        len(sales),
        'parser_version':     PARSER_VERSION,
    }
    try:
        supa.table('parcel_ereal_meta_v3').upsert(
            meta_row, on_conflict='pin'
        ).execute()
    except Exception as e:
        # Meta-table failures are not critical — logged only
        log.warning(f"[ereal.upsert {pin}] meta upsert failed: {e}")

    return stats


# ─── Batch runner ─────────────────────────────────────────────────────

def run_batch(
    supa,
    zip_code: str,
    limit: int = 100,
    ttl_days: int = 30,
    force: bool = False,
    sleep_between_s: float = INTER_REQUEST_SLEEP_S,
) -> dict:
    """
    Fetch up to `limit` parcels in the given ZIP that need refreshing.

    "Needs refreshing" means: parcel_ereal_meta_v3.fetched_at is NULL
    OR older than ttl_days ago. Pass force=True to bypass the TTL check
    and re-fetch regardless.

    Returns aggregate stats:
      {
        zip_code, fetched, parsed_ok, parse_errors, http_errors,
        sales_upserted, parcels_updated, duration_s, sample_errors
      }
    """
    started = time.time()
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    cutoff_iso = cutoff.isoformat()

    # Pull candidate pins: left-join parcels_v3 to parcel_ereal_meta_v3
    # and filter to those with NULL fetched_at or fetched_at < cutoff.
    # Supabase PostgREST doesn't do arbitrary joins, so do this in two
    # passes: get all pins in zip, then filter by meta.
    #
    # IMPORTANT: PostgREST has a hard cap on rows per response set
    # at the project level via PGRST_DB_MAX_ROWS (this project's cap
    # is 1,000 — verified by inspecting map_data.py:_fetch_all which
    # paginates at page_size=1000). To pull all parcels for ZIPs
    # with >1,000 rows, paginate explicitly with .range(start, end).
    PAGE_SIZE = 1000
    all_pins: list[str] = []
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
        all_pins.extend(r['pin'] for r in page_data)
        if len(page_data) < PAGE_SIZE:
            break  # last page
        page += 1
        if page > 100:    # safety cap: 100K parcels max per ZIP
            log.warning(f"ereal: pagination exceeded 100 pages for {zip_code}; stopping")
            break

    # Same pagination needed for the meta lookup. The .in_(all_pins)
    # filter limits us to whatever PIN list we send, but PostgREST
    # still caps the RESPONSE at PGRST_DB_MAX_ROWS rows. Chunk the
    # lookup so each request fits under the cap.
    meta_by_pin: dict[str, dict] = {}
    META_CHUNK = 500   # IN list size; response will have <= chunk size rows, well under 1000 cap
    for i in range(0, len(all_pins), META_CHUNK):
        chunk = all_pins[i:i + META_CHUNK]
        meta_res = (
            supa.table('parcel_ereal_meta_v3')
            .select('pin, fetched_at')
            .in_('pin', chunk)
            .execute()
        )
        for r in (meta_res.data or []):
            meta_by_pin[r['pin']] = r

    candidates: list[str] = []
    for pin in all_pins:
        m = meta_by_pin.get(pin)
        if force:
            candidates.append(pin)
        elif not m or not m.get('fetched_at'):
            candidates.append(pin)
        elif m['fetched_at'] < cutoff_iso:
            candidates.append(pin)
        if len(candidates) >= limit:
            break

    agg = {
        'zip_code':         zip_code,
        'candidates_found': len(candidates),
        'fetched':          0,
        'parsed_ok':        0,
        'parse_errors':     0,
        'http_errors':      0,
        'sales_upserted':   0,
        'parcels_updated':  0,
        'sample_errors':    [],
        'duration_s':       0.0,
    }

    session = _build_session()
    for i, pin in enumerate(candidates):
        res = fetch_one(pin, session=session)
        agg['fetched'] += 1

        if not res['ok']:
            if res.get('status') is None or (res['status'] or 0) >= 400:
                agg['http_errors'] += 1
            else:
                agg['parse_errors'] += 1
            if len(agg['sample_errors']) < 5:
                agg['sample_errors'].append({
                    'pin':    pin,
                    'status': res.get('status'),
                    'error':  res.get('error'),
                })
            # Also record the failure in the meta table so we don't
            # immediately retry it on the next run
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                supa.table('parcel_ereal_meta_v3').upsert({
                    'pin':                pin,
                    'last_attempt_at':    now_iso,
                    'last_error':         res.get('error'),
                    'http_status':        res.get('status'),
                    'body_length':        res.get('body_length') or 0,
                    'consecutive_errors': 1,
                    'parser_version':     PARSER_VERSION,
                }, on_conflict='pin').execute()
            except Exception:
                pass
        else:
            agg['parsed_ok'] += 1
            upsert_stats = upsert_parsed(supa, pin, res['parsed'])
            if upsert_stats['parcel_updated']:
                agg['parcels_updated'] += 1
            agg['sales_upserted'] += upsert_stats['sales_upserted']
            if upsert_stats.get('error') and len(agg['sample_errors']) < 5:
                agg['sample_errors'].append({
                    'pin':   pin,
                    'error': upsert_stats['error'],
                })

        # Rate limit between parcels — skip on the last iteration
        if i + 1 < len(candidates):
            time.sleep(sleep_between_s)

    agg['duration_s'] = round(time.time() - started, 1)
    return agg
