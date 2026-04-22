"""
Harvester API endpoints.

Gate: admin-key (same mechanism as the canonicalize/rescore endpoints).
Harvester runs can be expensive and shouldn't be casually triggered.

Endpoints:
  POST /api/harvest/run             Run a harvest + match cycle
  GET  /api/harvest/status/{zip}    Summary of raw_signals + matches for a ZIP
"""

from __future__ import annotations

import os
import time
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.harvesters.orchestrator import run_harvest, HARVESTERS
from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

router = APIRouter()


# ─── Admin-key guard ───────────────────────────────────────────────────

def _require_admin(x_admin_key: Optional[str]):
    server_key = os.environ.get("ADMIN_KEY")
    if not server_key:
        raise HTTPException(503, "ADMIN_KEY not configured server-side")
    if x_admin_key != server_key:
        raise HTTPException(401, "Missing or invalid X-Admin-Key header")


# ─── Request / response models ─────────────────────────────────────────

class HarvestRunRequest(BaseModel):
    source: str = Field(
        "kc_superior_court",
        description="Harvester key. See HARVESTERS registry.",
    )
    case_types: Optional[list[str]] = Field(
        None,
        description=(
            "Harvester-specific subset. For kc_superior_court: "
            "['probate', 'divorce'] (default = both)."
        ),
    )
    since_days_ago: int = Field(
        30,
        ge=1,
        le=730,
        description=(
            "How many days back to harvest from today. Ignored if "
            "since_date is provided."
        ),
    )
    since_date: Optional[str] = Field(
        None,
        description="YYYY-MM-DD. Overrides since_days_ago if set.",
    )
    until_date: Optional[str] = Field(
        None,
        description=(
            "YYYY-MM-DD. Upper bound. Defaults to today. Use with "
            "since_date for arbitrary date windows (e.g. 30-day chunks "
            "to stay under HTTP timeouts on large backfills)."
        ),
    )
    zip_filter: Optional[str] = Field(
        "98004",
        description="Scope matches to this ZIP. None = all covered ZIPs.",
    )
    dry_run: bool = Field(
        False,
        description=(
            "If true, harvester parses but writes NOTHING to Supabase. "
            "Useful for first-run parser validation."
        ),
    )
    match_after: bool = Field(
        True,
        description="Run matcher immediately after harvest.",
    )


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.post("/run")
def harvest_run(
    req: HarvestRunRequest,
    x_admin_key: Optional[str] = Header(None),
):
    """
    Fire a harvest + match cycle.

    For the pilot:
      - source: 'kc_superior_court'
      - case_types: ['probate', 'divorce']
      - since_days_ago: 30-180
      - zip_filter: '98004'

    Response includes harvested count, upsert counts (new vs duplicate),
    and match statistics.
    """
    _require_admin(x_admin_key)

    if req.source not in HARVESTERS:
        raise HTTPException(400, f"Unknown source. Available: {list(HARVESTERS)}")

    # Resolve date window: explicit dates override since_days_ago.
    # Chunking strategy: to avoid Railway's ~5-min HTTP timeout on large
    # backfills, callers can pass 30-day windows (e.g. since_date=2025-11-01,
    # until_date=2025-12-01) and make multiple calls.
    try:
        if req.until_date:
            until = date.fromisoformat(req.until_date)
        else:
            until = date.today()
        if req.since_date:
            since = date.fromisoformat(req.since_date)
        else:
            since = until - timedelta(days=req.since_days_ago)
    except ValueError as e:
        raise HTTPException(400, f"Invalid date format (expected YYYY-MM-DD): {e}")

    if since > until:
        raise HTTPException(400, "since_date must be <= until_date")

    stats = run_harvest(
        source=req.source,
        since=since,
        until=until,
        case_types=req.case_types,
        zip_filter=req.zip_filter,
        dry_run=req.dry_run,
        match_after=req.match_after,
    )
    return stats


@router.post("/match-only")
def harvest_match_only(
    x_admin_key: Optional[str] = Header(None),
    zip_filter: Optional[str] = "98004",
    batch_size: int = 100,
    max_batches: int = 200,
):
    """
    Run JUST the matcher against already-harvested signals. Skips the
    harvest step entirely. Safe to run repeatedly — the matcher only
    processes rows with matched_at IS NULL.

    Use case: a previous harvest wrote signals to raw_signals_v3 but
    the matcher phase never ran (e.g. HTTP timeout killed the request
    handler mid-run). This endpoint picks up where it left off.

    Typical runtime: ~1-3 minutes for a few thousand pending signals.
    Far under the Railway HTTP timeout because matching is just DB
    reads + writes (no external scraping).
    """
    _require_admin(x_admin_key)

    # Import locally to avoid circular-ish load at module import time
    from backend.harvesters import matcher
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    stats = matcher.process_unmatched(
        supa,
        zip_filter=zip_filter,
        batch_size=batch_size,
        max_batches=max_batches,
    )
    return stats


@router.get("/diag/signal-date-range")
def diag_signal_date_range(
    x_admin_key: Optional[str] = Header(None),
    signal_type: str = "probate",
):
    """
    Diagnostic: summary of event_date distribution for a signal type.
    Shows min/max date, how many signals have null event_date, and
    a few sample rows from each extreme.
    """
    _require_admin(x_admin_key)
    supa = get_supabase_client()

    # Count total
    total_res = (supa.table('raw_signals_v3')
                 .select('id', count='exact')
                 .eq('source_type', 'kc_superior_court')
                 .eq('signal_type', signal_type)
                 .limit(1)
                 .execute())
    total = total_res.count or 0

    # Count with null event_date
    null_res = (supa.table('raw_signals_v3')
                .select('id', count='exact')
                .eq('source_type', 'kc_superior_court')
                .eq('signal_type', signal_type)
                .is_('event_date', 'null')
                .limit(1)
                .execute())
    null_count = null_res.count or 0

    # Earliest 5 rows by event_date
    earliest = (supa.table('raw_signals_v3')
                .select('id, document_ref, event_date')
                .eq('source_type', 'kc_superior_court')
                .eq('signal_type', signal_type)
                .not_.is_('event_date', 'null')
                .order('event_date', desc=False)
                .limit(5)
                .execute()).data or []

    # Latest 5 rows by event_date
    latest = (supa.table('raw_signals_v3')
              .select('id, document_ref, event_date')
              .eq('source_type', 'kc_superior_court')
              .eq('signal_type', signal_type)
              .not_.is_('event_date', 'null')
              .order('event_date', desc=True)
              .limit(5)
              .execute()).data or []

    # Also sample 5 of the NULL-event-date signals
    null_samples = (supa.table('raw_signals_v3')
                    .select('id, document_ref, raw_data')
                    .eq('source_type', 'kc_superior_court')
                    .eq('signal_type', signal_type)
                    .is_('event_date', 'null')
                    .limit(5)
                    .execute()).data or []
    null_samples_min = [
        {"id": r['id'], "document_ref": r.get('document_ref')}
        for r in null_samples
    ]

    return {
        "signal_type":       signal_type,
        "total_signals":     total,
        "null_event_date":   null_count,
        "earliest_signals":  earliest,
        "latest_signals":    latest,
        "null_samples":      null_samples_min,
    }


@router.get("/diag/case-key-match")
def diag_case_key_match(
    x_admin_key: Optional[str] = Header(None),
    signal_type: str = "probate",
    since: str = "2025-10-20",
    until: str = "2025-10-26",
):
    """
    Diagnostic: show the FIRST 20 DB document_ref values in this date
    range side-by-side with what the live KC search returns. Pinpoints
    why backfill-internal-ids isn't matching.

    Read-only. No writes.
    """
    _require_admin(x_admin_key)
    from datetime import datetime
    from backend.harvesters.kc_superior_court import (
        KCSuperiorCourtHarvester, CASE_TYPES,
    )

    start_date = datetime.strptime(since, "%Y-%m-%d").date()
    end_date = datetime.strptime(until, "%Y-%m-%d").date()

    supa = get_supabase_client()

    # DB side: event_date filter
    res = (supa.table('raw_signals_v3')
           .select('id, document_ref, event_date, raw_data')
           .eq('source_type', 'kc_superior_court')
           .eq('signal_type', signal_type)
           .gte('event_date', str(start_date))
           .lte('event_date', str(end_date))
           .order('id', desc=False)
           .limit(20)
           .execute())
    db_rows = res.data or []
    db_docs = [
        {
            "id":            r['id'],
            "document_ref":  r.get('document_ref'),
            "event_date":    r.get('event_date'),
            "has_internal":  bool(r.get('raw_data', {}).get('internal_id')),
        }
        for r in db_rows
    ]

    # Live scrape side
    h = KCSuperiorCourtHarvester(case_types=[signal_type])
    session = h.build_session()
    code, sel, _ = CASE_TYPES[signal_type]
    live_rows: list = []
    try:
        ctx = h._open_search_form(session, code)
        html = h._post_search(session, code, sel, ctx, start_date, end_date)
        parsed = h._parse_result_rows(html)
        for row in parsed[:20]:
            live_rows.append({
                "case_number":      row.get('case_number'),
                "case_number_raw":  row.get('case_number_raw'),
                "internal_id":      row.get('internal_id'),
                "filing_date":      row.get('filing_date_raw'),
                "case_name":        row.get('case_name')[:40] if row.get('case_name') else None,
            })
    except Exception as e:
        live_rows = [{"error": str(e)[:300]}]

    return {
        "date_range":   f"{start_date}..{end_date}",
        "db_count":     len(db_rows),
        "db_sample":    db_docs,
        "live_count":   len(live_rows),
        "live_sample":  live_rows,
    }


@router.get("/diag/fetch-participants")
def diag_fetch_participants(
    x_admin_key: Optional[str] = Header(None),
    internal_id: str = "5387893",
    warmup_mode: str = "real_search",
    warmup_since: Optional[str] = None,
    warmup_until: Optional[str] = None,
):
    """
    Diagnostic: fetch the Participants tab for ONE case using a specified
    warm-up strategy and return the raw HTML + parse result so we can see
    why production fetches are returning 'No participants table found'.

    warmup_mode options:
      - 'today'         Warm session with today-to-today search (returns 0 rows).
                        This is what backfill-parties currently does.
      - 'real_search'   Warm with a 1-week date-range search that returns real
                        results (April 21-27 2025, which we know has 171 cases).
      - 'real_plus_detail'  As above, but then also visit the specific case's
                           detail page (?q=node/420/{id}) before the Participants
                           tab, to establish a 'currently viewing' session.
      - 'none'          No warm-up at all.

    Returns:
      warmup_mode, html_length, html_preview (first 500 chars after the
      nav chrome), parse_success, parse_parties (structured party list
      if parse succeeded), and a 'participants_text_snippet' for quick
      visual inspection of the page's actual participant data.
    """
    _require_admin(x_admin_key)
    from backend.harvesters.kc_superior_court import (
        KCSuperiorCourtHarvester, CASE_TYPES, BASE, FORM_BASE_PATH,
    )
    from backend.harvesters.kc_court_participants import (
        _parse_participants_html,
    )
    from datetime import date, timedelta

    h = KCSuperiorCourtHarvester(case_types=['probate'])
    session = h.build_session()
    code = "511110"

    warm_info = {}
    if warmup_mode == "today":
        try:
            ctx = h._open_search_form(session, code)
            today = date.today()
            html = h._post_search(session, code, code, ctx, today, today)
            warm_info['status'] = 'OK'
            warm_info['warm_html_len'] = len(html)
        except Exception as e:
            warm_info['status'] = f'ERROR: {str(e)[:100]}'
    elif warmup_mode == "paginated_warmup":
        # Full pagination through all pages of the given week — mimics
        # what backfill-parties does.
        try:
            from datetime import datetime
            if not (warmup_since and warmup_until):
                return {"error": "paginated_warmup requires warmup_since and warmup_until"}
            w_since = datetime.strptime(warmup_since, "%Y-%m-%d").date()
            w_until = datetime.strptime(warmup_until, "%Y-%m-%d").date()
            ctx = h._open_search_form(session, code)
            html = h._post_search(session, code, code, ctx, w_since, w_until)
            page_idx = 1
            pages_fetched = 1
            all_case_numbers = [r.get('case_number') for r in h._parse_result_rows(html)]
            while h._has_next_page_link(html, page_idx):
                html = h._get_next_page(session, code, page_idx)
                page_idx += 1
                pages_fetched += 1
                all_case_numbers.extend(r.get('case_number') for r in h._parse_result_rows(html))
                if page_idx > 15:
                    break
            warm_info['status'] = 'OK'
            warm_info['warm_range'] = f"{w_since}..{w_until}"
            warm_info['pages_fetched'] = pages_fetched
            warm_info['total_cases_authorized'] = len(all_case_numbers)
            warm_info['first_cases'] = all_case_numbers[:5]
            warm_info['last_cases'] = all_case_numbers[-5:] if len(all_case_numbers) > 5 else []
        except Exception as e:
            warm_info['status'] = f'ERROR: {str(e)[:100]}'

    elif warmup_mode in ("real_search", "real_plus_detail"):
        try:
            ctx = h._open_search_form(session, code)
            # Use custom dates if provided, else default to April 21-27 2025
            if warmup_since and warmup_until:
                from datetime import datetime
                w_since = datetime.strptime(warmup_since, "%Y-%m-%d").date()
                w_until = datetime.strptime(warmup_until, "%Y-%m-%d").date()
            else:
                w_since = date(2025, 4, 21)
                w_until = date(2025, 4, 27)
            html = h._post_search(
                session, code, code, ctx,
                w_since, w_until,
            )
            warm_info['status'] = 'OK'
            warm_info['warm_html_len'] = len(html)
            warm_info['warm_range'] = f"{w_since}..{w_until}"
        except Exception as e:
            warm_info['status'] = f'ERROR: {str(e)[:100]}'

    search_referer = f"{BASE}{FORM_BASE_PATH}?caseType=511110"

    # Optionally bootstrap detail page first
    detail_html_len = None
    if warmup_mode == "real_plus_detail":
        try:
            detail_url = f"{BASE}/?q=node/420/{internal_id}"
            r = session.get(
                detail_url,
                headers={'Referer': search_referer},
                timeout=30,
            )
            detail_html_len = len(r.text)
        except Exception as e:
            detail_html_len = f"ERR: {str(e)[:80]}"

    # Fetch the Participants tab directly
    part_url = (
        f"{BASE}/node/420"
        f"?Id={internal_id}"
        f"&folder=FV-Public-Case-Participants-Portal"
    )
    part_info = {}
    try:
        import requests
        r = session.get(
            part_url,
            headers={'Referer': search_referer},
            timeout=30,
        )
        part_info['status_code'] = r.status_code
        part_info['html_length'] = len(r.text)
        # Try parsing
        parties = _parse_participants_html(r.text)
        part_info['parse_party_count'] = len(parties)
        part_info['parsed_parties'] = [
            {
                'role': p.role,
                'raw_role': p.raw_role,
                'name_raw': p.name_raw,
                'pr_classification': p.pr_classification,
            }
            for p in parties
        ]
        # Find "Participants" text in page and snippet around it
        html_up = r.text
        snippet = None
        # Look for 'table-condensed' class (the parties table)
        if 'table-condensed' in html_up:
            idx = html_up.index('table-condensed')
            snippet = html_up[max(0, idx - 200):idx + 1500]
            part_info['has_table_condensed_class'] = True
        else:
            part_info['has_table_condensed_class'] = False
            # Find 'Participant' occurrence
            if 'Participant' in html_up:
                idx = html_up.index('Participant')
                snippet = html_up[max(0, idx - 200):idx + 1000]
            else:
                part_info['has_participant_text'] = False
        part_info['snippet'] = snippet[:2000] if snippet else None

        # Also check for key errors
        if 'not authorized' in html_up.lower():
            part_info['authorization_error'] = True
        if 'page not found' in html_up.lower():
            part_info['page_not_found_error'] = True

        # Extra indicators to diagnose generic-page state
        indicators: dict = {}
        for marker in [
            'Participants', 'Case Data', 'Documents', 'Events',
            'please refine', 'session expired', 'login',
            'folder=FV-Public-Case-Participants',
            'data-drupal-selector', 'drupal-settings-json',
            'BigPipe', 'big_pipe', 'ECPFormCode',
            'Please try again', 'page unavailable',
        ]:
            indicators[marker] = marker in html_up
        part_info['indicators'] = indicators

        # Middle snippet — body area
        body_start = html_up.find('<body')
        if body_start > 0:
            part_info['body_snippet_middle'] = html_up[body_start:body_start + 2500]
        # End snippet — last 1500 chars before </body>
        body_end = html_up.rfind('</body>')
        if body_end > 0:
            part_info['body_snippet_end'] = html_up[max(0, body_end - 1500):body_end + 10]
    except Exception as e:
        part_info['fetch_error'] = str(e)[:200]

    return {
        'internal_id':      internal_id,
        'warmup_mode':      warmup_mode,
        'warm_info':        warm_info,
        'detail_html_len':  detail_html_len,
        'part_info':        part_info,
    }


@router.post("/backfill-internal-ids")
def harvest_backfill_internal_ids(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
    signal_type: str = "probate",
    since: Optional[str] = None,  # 'YYYY-MM-DD'
    until: Optional[str] = None,  # 'YYYY-MM-DD'
    chunk_weeks: int = 1,
):
    """
    Backfill the portal's internal_id into existing raw_signals_v3.raw_data.

    The primary harvester previously didn't capture the per-case node ID
    used to navigate into the Participants / Documents tabs. This endpoint
    re-runs KC Superior Court searches week-by-week across a date range,
    extracts internal_id from each result row's case-number link, and
    UPDATEs the matching raw_signals_v3 row.

    No signals are created or deleted — only the 'internal_id' key inside
    each signal's raw_data JSONB is added. Safe to re-run.

    Params:
      signal_type  — 'probate' or 'divorce' (each searches a different
                     case-type bucket on the portal)
      since/until  — date range to cover. Defaults to the min/max event_date
                     of un-backfilled signals in that signal_type.
      chunk_weeks  — how many weeks per search call. Default 1 (safest for
                     portal pagination at 20 results/page × 3 pages max).

    Wall-clock: ~5 seconds per weekly search. A full 18-month backfill is
    ~75 weekly searches ≈ 6 minutes. Well within HTTP timeout.
    """
    _require_admin(x_admin_key)
    if not confirm:
        raise HTTPException(
            400,
            "This re-searches the KC portal. Pass ?confirm=true to proceed.",
        )

    from datetime import datetime, date as date_cls, timedelta
    from backend.harvesters.kc_superior_court import (
        KCSuperiorCourtHarvester, CASE_TYPES,
    )

    if signal_type not in CASE_TYPES:
        raise HTTPException(400, f"signal_type must be one of {list(CASE_TYPES.keys())}")

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # Determine date range
    if since:
        start_date = datetime.strptime(since, "%Y-%m-%d").date()
    else:
        # Default: earliest un-backfilled signal of this type
        start_date = date_cls(2025, 1, 1)
    if until:
        end_date = datetime.strptime(until, "%Y-%m-%d").date()
    else:
        end_date = date_cls.today()

    if end_date < start_date:
        raise HTTPException(400, "until must be >= since")

    # Build a {case_number: signal_id} index from DB for fast lookup
    signal_ids_by_case: dict = {}
    OFFSET_STEP = 1000
    sig_offset = 0
    while True:
        res = (supa.table('raw_signals_v3')
               .select('id, document_ref, raw_data')
               .eq('source_type', 'kc_superior_court')
               .eq('signal_type', signal_type)
               .range(sig_offset, sig_offset + OFFSET_STEP - 1)
               .execute())
        batch = res.data or []
        if not batch:
            break
        for r in batch:
            case_num = r.get('document_ref')
            if not case_num:
                continue
            raw_data = r.get('raw_data') or {}
            if raw_data.get('internal_id'):
                continue  # already backfilled
            signal_ids_by_case[case_num] = (r['id'], raw_data)
        if len(batch) < OFFSET_STEP:
            break
        sig_offset += OFFSET_STEP

    if not signal_ids_by_case:
        return {
            "message":          "No signals need internal_id backfill.",
            "signals_updated":  0,
        }

    log.info(f"Need to backfill internal_id for {len(signal_ids_by_case)} {signal_type} signals")

    # Run searches week-by-week
    h = KCSuperiorCourtHarvester(case_types=[signal_type])
    session = h.build_session()
    code, sel, _ = CASE_TYPES[signal_type]

    signals_updated = 0
    searches_run = 0
    errors: list = []
    cur = start_date
    while cur <= end_date:
        win_start = cur
        win_end = min(cur + timedelta(days=7 * chunk_weeks - 1), end_date)
        try:
            ctx = h._open_search_form(session, code)
            html = h._post_search(session, code, sel, ctx, win_start, win_end)
            rows = h._parse_result_rows(html)
            # Handle pagination — pages beyond the first
            page_idx = 1
            while h._has_next_page_link(html, page_idx):
                html = h._get_next_page(session, code, page_idx)
                rows.extend(h._parse_result_rows(html))
                page_idx += 1
                if page_idx > 10:
                    break  # safety

            # Match case_numbers to DB rows and update
            for row in rows:
                case_num = row.get('case_number')
                internal_id = row.get('internal_id')
                if not case_num or not internal_id:
                    continue
                if case_num not in signal_ids_by_case:
                    continue
                sig_id, raw_data = signal_ids_by_case[case_num]
                new_raw = dict(raw_data)
                new_raw['internal_id'] = internal_id
                (supa.table('raw_signals_v3')
                 .update({'raw_data': new_raw})
                 .eq('id', sig_id)
                 .execute())
                signals_updated += 1
                del signal_ids_by_case[case_num]

            searches_run += 1
        except Exception as e:
            errors.append({
                "window":  f"{win_start}..{win_end}",
                "error":   str(e)[:200],
            })
            if len(errors) > 10:
                break

        cur = win_end + timedelta(days=1)

    return {
        "signal_type":          signal_type,
        "date_range":           f"{start_date}..{end_date}",
        "searches_run":         searches_run,
        "signals_updated":      signals_updated,
        "signals_still_needing_backfill": len(signal_ids_by_case),
        "errors":               errors,
    }


@router.post("/clear-sentinel-parties")
def harvest_clear_sentinels(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
):
    """
    Delete '(no participants found)' sentinel rows from case_parties_v3.

    Earlier versions of backfill-parties failed with "not authorized" due
    to wrong session warm-up and wrote sentinels for cases that actually
    have participants. This endpoint clears those sentinels so the cases
    can be re-scraped.

    Only deletes rows where raw_role='(no participants found)'. Real
    party data is never touched.
    """
    _require_admin(x_admin_key)
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to proceed.")

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    res = (supa.table('case_parties_v3')
           .delete()
           .eq('raw_role', '(no participants found)')
           .execute())
    return {
        "deleted_count": len(res.data or []),
        "message":       "Cleared sentinel rows. Cases are unblocked for re-scraping.",
    }


@router.post("/backfill-parties")
def harvest_backfill_parties(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
    limit: int = 50,
    offset: int = 0,
    source_type: str = "kc_superior_court",
    zip_code: Optional[str] = None,
):
    """
    Enrich existing probate/divorce signals with Participants-tab data.

    KC Superior Court portal authorizes case-detail access via search-result
    session state: you can only fetch the Participants tab for cases that
    were returned by a recent search that YOU paginated through. A search
    for April dates won't authorize an August case.

    So: this endpoint groups the `limit` candidate cases by event-date WEEK,
    and for each week (1) performs a search covering that week, (2) paginates
    through all result pages to authorize every case, (3) fetches
    Participants for every case in that week's batch.

    Idempotent: cases already in case_parties_v3 are skipped. Safe to retry.

    Case selection modes:
      1) offset-based (default): scans signals in id order starting at `offset`
      2) zip_code=XXXXX: restricts to signals that matched parcels in that ZIP.
         This is the high-value mode for agents — prioritizes their territory.

    Params:
      limit    — cap on cases to process this call (default 50, max 200).
      offset   — skip this many signal IDs before scanning (for chunked runs).
      zip_code — if set, only process cases that have a match for a parcel
                 in this ZIP (e.g. "98004"). Ignores offset.

    Typical rate: ~0.5s per case + ~2s per week warm-up. For 50 cases
    spread across ~5 weeks: ~40 sec wall-clock per call.
    """
    _require_admin(x_admin_key)
    if not confirm:
        raise HTTPException(
            400,
            "This fetches from the live KC portal. Pass ?confirm=true to proceed.",
        )
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be 1–200")

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    if zip_code:
        # ZIP-driven selection: find raw_signal_ids that matched parcels
        # in this ZIP, then load those signals (not offset-based).
        pins_in_zip: list = []
        PAGE = 1000
        z_off = 0
        while True:
            res = (supa.table('parcels_v3')
                   .select('pin')
                   .eq('zip_code', zip_code)
                   .range(z_off, z_off + PAGE - 1)
                   .execute())
            batch = res.data or []
            pins_in_zip.extend(r['pin'] for r in batch)
            if len(batch) < PAGE:
                break
            z_off += PAGE
            if z_off > 100000:
                break

        if not pins_in_zip:
            return {
                "processed":         0,
                "message":           f"No parcels found in ZIP {zip_code}.",
                "zip_code":          zip_code,
            }

        # Pull signal_ids for matches on these pins (prefer non-weak)
        matched_signal_ids: set = set()
        CHUNK = 200
        for i in range(0, len(pins_in_zip), CHUNK):
            chunk = pins_in_zip[i : i + CHUNK]
            res = (supa.table('raw_signal_matches_v3')
                   .select('raw_signal_id')
                   .in_('pin', chunk)
                   .neq('match_strength', 'weak')
                   .limit(5000)
                   .execute())
            matched_signal_ids.update(
                m['raw_signal_id'] for m in (res.data or [])
            )

        if not matched_signal_ids:
            return {
                "processed":         0,
                "message":           f"No strong matches yet for ZIP {zip_code}.",
                "zip_code":          zip_code,
            }

        # Load those signals
        all_signals = []
        CHUNK_S = 300
        sig_ids_list = list(matched_signal_ids)
        for i in range(0, len(sig_ids_list), CHUNK_S):
            chunk = sig_ids_list[i : i + CHUNK_S]
            res = (supa.table('raw_signals_v3')
                   .select('id, document_ref, raw_data, signal_type, event_date')
                   .in_('id', chunk)
                   .eq('source_type', source_type)
                   .in_('signal_type', ['probate', 'divorce'])
                   .execute())
            all_signals.extend(res.data or [])
    else:
        # Offset-based: scan signals in id order.
        # Scan a wider window than the final limit so we can filter out
        # already-scraped + missing-internal-id cases before picking `limit`.
        signals_res = (supa.table('raw_signals_v3')
                       .select('id, document_ref, raw_data, signal_type, event_date')
                       .eq('source_type', source_type)
                       .in_('signal_type', ['probate', 'divorce'])
                       .order('id', desc=False)
                       .range(offset, offset + 500 - 1)
                       .execute())
        all_signals = signals_res.data or []

    # Find which case_numbers already have parties scraped
    case_numbers_to_check = [
        s['document_ref'] for s in all_signals if s.get('document_ref')
    ]
    already_scraped: set = set()
    if case_numbers_to_check:
        CHK = 300
        for i in range(0, len(case_numbers_to_check), CHK):
            chunk = case_numbers_to_check[i : i + CHK]
            res = (supa.table('case_parties_v3')
                   .select('case_number')
                   .in_('case_number', chunk)
                   .eq('source_type', source_type)
                   .execute())
            already_scraped.update(r['case_number'] for r in (res.data or []))

    # Filter to signals needing scrape + with internal_id + with event_date
    needs_scrape = [
        s for s in all_signals
        if s.get('document_ref')
        and s.get('raw_data', {}).get('internal_id')
        and s.get('event_date')  # need date to group by week
        and s['document_ref'] not in already_scraped
    ][:limit]

    if not needs_scrape:
        return {
            "processed":         0,
            "skipped_no_id":     sum(
                1 for s in all_signals
                if not s.get('raw_data', {}).get('internal_id')
            ),
            "skipped_no_date":   sum(
                1 for s in all_signals
                if s.get('raw_data', {}).get('internal_id')
                and not s.get('event_date')
            ),
            "already_scraped":   len(already_scraped),
            "message":           "Nothing to process in this window.",
            "offset_scanned":    offset,
            "offset_scanned_to": offset + len(all_signals),
        }

    # Group signals by ISO week (Monday-based). Each week-group will get
    # one warm-up search covering that full week.
    from datetime import datetime, date as date_cls, timedelta
    from backend.harvesters.kc_superior_court import (
        KCSuperiorCourtHarvester, CASE_TYPES, BASE, FORM_BASE_PATH,
    )
    from backend.harvesters.kc_court_participants import fetch_case_participants

    def _week_start(event_date_str: str) -> date_cls:
        """Return Monday of the week containing the event date."""
        d = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        return d - timedelta(days=d.weekday())

    groups: dict = {}   # week_start -> [signals]
    for s in needs_scrape:
        wk = _week_start(s['event_date'])
        groups.setdefault(wk, []).append(s)

    h = KCSuperiorCourtHarvester(case_types=['probate'])
    session = h.build_session()
    code = "511110"
    search_referer = f"{BASE}{FORM_BASE_PATH}?caseType=511110"

    processed = 0
    inserted_parties = 0
    no_parties_count = 0
    errors: list = []
    weeks_processed = 0

    for week_start, week_signals in sorted(groups.items()):
        week_end = week_start + timedelta(days=6)
        # Index this week's target cases by internal_id for O(1) lookup
        # during page processing.
        targets_by_internal_id = {
            s['raw_data']['internal_id']: s for s in week_signals
        }
        # Also index by case_number so we can match against search rows
        # which give us case_number but signals are keyed by internal_id.
        # (internal_id is the authoritative key; case_number is the DB ref.)
        week_done = False
        try:
            # 1) Fresh warm-up: search form + post search for THIS week only
            ctx = h._open_search_form(session, code)
            html = h._post_search(
                session, code, code, ctx, week_start, week_end,
            )
            weeks_processed += 1
        except Exception as e:
            errors.append({
                'week':  f"{week_start}..{week_end}",
                'error': f"warmup failed: {str(e)[:150]}",
            })
            if len(errors) > 10:
                break
            continue

        # 2) CRITICAL: the portal authorizes case-detail access ONLY for the
        # page of results currently being viewed. Paginating to page 2
        # REVOKES authorization for page 1's cases. So we must fetch
        # Participants for each target case BEFORE moving to the next page.
        #
        # ADDITIONAL CONSTRAINT discovered empirically: the portal also
        # depletes authorization after ~3-4 Participants fetches within
        # a single page view. Solution: rebuild the entire session (fresh
        # cookies) between EACH case. Yes, it's heavy-handed (~2 extra
        # HTTP calls per case, total ~28k extra calls for full backfill)
        # but it's the only approach that reliably works for >10 cases
        # on a single page.
        #
        # Drupal pagination: POST returns display-page-1 (Drupal page 0,
        # no ?page= param). Clicking "2" goes to ?page=1 = display-page-2.
        # `drupal_page` tracks the URL param (0 = no param / POST result).
        drupal_page = 0
        # Diagnostic trace for this week
        case_trace: list = []

        def _rebuild_and_warm() -> str:
            """Build a fresh session, warm it with a search POST for this
            week, and (if not on page 0) paginate to the current page.
            Returns the HTML of the current page."""
            nonlocal session
            session = h.build_session()
            ctx2 = h._open_search_form(session, code)
            new_html = h._post_search(
                session, code, code, ctx2, week_start, week_end,
            )
            # If we're past page 0, paginate up to our current page
            for p in range(1, drupal_page + 1):
                new_html = h._get_next_page(session, code, p)
            return new_html

        while not week_done:
            # Parse this page's case rows (fresh from the current `html`)
            page_rows = h._parse_result_rows(html)
            cases_processed_on_this_page = 0
            for row in page_rows:
                iid = row.get('internal_id')
                if not iid or iid not in targets_by_internal_id:
                    continue  # this case isn't in my backfill batch
                signal = targets_by_internal_id.pop(iid)
                case_num = signal['document_ref']

                # Rebuild session between cases to get fresh auth.
                # Skip for the very first case (session is already fresh
                # from the week-warmup at the top of this loop).
                if cases_processed_on_this_page > 0:
                    try:
                        html = _rebuild_and_warm()
                        time.sleep(0.3)
                    except Exception as e:
                        errors.append({
                            'case_number': case_num,
                            'error': f"session rebuild (drupal_page={drupal_page}) failed: {str(e)[:120]}",
                        })
                        case_trace.append({
                            'case': case_num, 'drupal_page': drupal_page,
                            'step': 'rebuild_failed',
                        })
                        continue
                cases_processed_on_this_page += 1

                try:
                    parties = fetch_case_participants(
                        session, iid, search_referer, polite_delay=0.3,
                    )
                    processed += 1
                    case_trace.append({
                        'case': case_num, 'drupal_page': drupal_page,
                        'parties': len(parties),
                    })

                    if not parties:
                        (supa.table('case_parties_v3')
                         .upsert({
                            'case_number':    case_num,
                            'source_type':    source_type,
                            'role':           'other',
                            'raw_role':       '(no participants found)',
                            'name_raw':       '(empty)',
                         }, on_conflict='case_number,source_type,role,name_raw')
                         .execute())
                        no_parties_count += 1
                        continue

                    rows_ins = [
                        {
                            'case_number':       case_num,
                            'source_type':       source_type,
                            'role':              p.role,
                            'raw_role':          p.raw_role,
                            'name_raw':          p.name_raw,
                            'name_last':         p.name_last,
                            'name_first':        p.name_first,
                            'name_middle':       p.name_middle,
                            'represented_by':    p.represented_by,
                            'pr_classification': p.pr_classification,
                        }
                        for p in parties
                    ]
                    (supa.table('case_parties_v3')
                     .upsert(rows_ins,
                             on_conflict='case_number,source_type,role,name_raw')
                     .execute())
                    inserted_parties += len(rows_ins)
                except Exception as e:
                    errors.append({
                        'case_number': case_num,
                        'error':       str(e)[:200],
                    })
                    if len(errors) > 20:
                        week_done = True
                        break

            # Done with this page's targets. Are there any week targets left?
            if not targets_by_internal_id:
                week_done = True
                break
            # Check if there's a next page in the CURRENT html.
            if not h._has_next_page_link(html, drupal_page + 1):
                # No more pages; any remaining targets just aren't findable
                # via this week's search (e.g. disposed/sealed cases that
                # don't appear in KC search results). Skip them.
                week_done = True
                break
            if drupal_page >= 14:
                # Safety cap — some pathological weeks might exceed this
                week_done = True
                break
            # Advance to next page. This also rebuilds session for fresh auth.
            try:
                session = h.build_session()
                ctx2 = h._open_search_form(session, code)
                html = h._post_search(
                    session, code, code, ctx2, week_start, week_end,
                )
                next_drupal = drupal_page + 1
                for p in range(1, next_drupal + 1):
                    html = h._get_next_page(session, code, p)
                drupal_page = next_drupal
            except Exception as e:
                errors.append({
                    'week':  f"{week_start}..{week_end}",
                    'error': f"advance to ?page={drupal_page + 1} failed: {str(e)[:100]}",
                })
                week_done = True
                break

        # Attach trace to errors for diagnostic visibility
        if case_trace:
            # Keep trace small to avoid blowing up response size
            if len(case_trace) <= 60:
                errors.append({'week_trace': case_trace})

    return {
        "processed":            processed,
        "inserted_parties":     inserted_parties,
        "no_parties_found":     no_parties_count,
        "weeks_processed":      weeks_processed,
        "total_weeks_in_batch": len(groups),
        "errors":               errors,
        "offset_start":         offset,
        "offset_end":           offset + len(all_signals),
        "next_offset":          offset + len(all_signals),
    }


@router.get("/diag/portal-health")
def diag_portal_health(
    x_admin_key: Optional[str] = Header(None),
):
    """
    Quick check whether the KC Superior Court portal is responsive.
    Tests the search form endpoint and a known-good case's participants.

    Returns status dict. Used to gate backfill-parties runs — if portal
    is degraded, don't burn time trying.
    """
    _require_admin(x_admin_key)
    from backend.harvesters.kc_superior_court import (
        KCSuperiorCourtHarvester, BASE, FORM_BASE_PATH,
    )
    from backend.harvesters.kc_court_participants import _parse_participants_html
    from datetime import date

    h = KCSuperiorCourtHarvester(case_types=['probate'])
    session = h.build_session()
    code = "511110"

    health = {"portal_healthy": False, "checks": {}}

    # Check 1: Search form loads
    try:
        ctx = h._open_search_form(session, code)
        health['checks']['search_form'] = 'OK'
    except Exception as e:
        health['checks']['search_form'] = f"FAIL: {str(e)[:120]}"
        return health

    # Check 2: POST search returns real results
    try:
        html = h._post_search(session, code, code, ctx, date(2025, 4, 21), date(2025, 4, 27))
        health['checks']['search_post_len'] = len(html)
        rows = h._parse_result_rows(html)
        health['checks']['search_rows_page1'] = len(rows)
        if len(rows) < 5:
            health['checks']['search_verdict'] = 'FAIL: too few rows'
            return health
    except Exception as e:
        health['checks']['search_post'] = f"FAIL: {str(e)[:120]}"
        return health

    # Check 3: Known-good case 5387893 (YURDIN, LAWRENCE S)
    try:
        search_referer = f"{BASE}{FORM_BASE_PATH}?caseType=511110"
        import requests
        part_url = f"{BASE}/node/420?Id=5387893&folder=FV-Public-Case-Participants-Portal"
        session.get(f"{BASE}/?q=node/420/5387893",
                    headers={'Referer': search_referer}, timeout=15)
        r = session.get(part_url, headers={'Referer': search_referer}, timeout=15)
        health['checks']['participants_http'] = r.status_code
        health['checks']['participants_len'] = len(r.text)
        if 'table-condensed' in r.text:
            parties = _parse_participants_html(r.text)
            health['checks']['participants_parsed'] = len(parties)
            health['portal_healthy'] = True
        else:
            health['checks']['participants_verdict'] = 'FAIL: no table-condensed'
    except Exception as e:
        health['checks']['participants'] = f"FAIL: {str(e)[:120]}"

    return health


@router.get("/diag/parties-count")
def diag_parties_count(
    x_admin_key: Optional[str] = Header(None),
):
    """
    Return counts of parties in case_parties_v3 by role and pr_classification.
    Also counts how many DISTINCT case_numbers have parties scraped (vs total
    signals) so we can track coverage.
    """
    _require_admin(x_admin_key)
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    result: dict = {}

    # Total parties rows
    total = (supa.table('case_parties_v3')
             .select('id', count='exact')
             .limit(1)
             .execute())
    result['total_party_rows'] = total.count or 0

    # Sentinel rows (no participants found)
    sentinels = (supa.table('case_parties_v3')
                 .select('id', count='exact')
                 .eq('raw_role', '(no participants found)')
                 .limit(1)
                 .execute())
    result['sentinel_rows'] = sentinels.count or 0

    # Real party rows
    result['real_party_rows'] = result['total_party_rows'] - result['sentinel_rows']

    # By role
    role_counts: dict = {}
    for role in ['deceased', 'personal_representative', 'petitioner',
                 'attorney', 'respondent', 'other']:
        c = (supa.table('case_parties_v3')
             .select('id', count='exact')
             .eq('role', role)
             .limit(1)
             .execute())
        role_counts[role] = c.count or 0
    result['by_role'] = role_counts

    # By pr_classification (for personal_representative role)
    pr_counts: dict = {}
    for cls in ['family', 'corporate', 'attorney', 'unknown']:
        c = (supa.table('case_parties_v3')
             .select('id', count='exact')
             .eq('role', 'personal_representative')
             .eq('pr_classification', cls)
             .limit(1)
             .execute())
        pr_counts[cls] = c.count or 0
    result['pr_classification'] = pr_counts

    # Distinct case_numbers scraped
    # Supabase doesn't have a clean DISTINCT COUNT via REST, so approximate
    # via sentinel + real and note it's an upper bound
    result['note'] = ("Case coverage: a case_number may have multiple rows "
                      "(decedent + PR + attorney + etc), so total_party_rows "
                      "> distinct case_numbers scraped. Real coverage requires "
                      "a SELECT DISTINCT or use per-case query.")

    return result


@router.post("/rematch")
def harvest_rematch(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
    zip_filter: Optional[str] = "98004",
):
    """
    Delete ALL existing raw_signal_matches_v3 rows, then reset
    raw_signals_v3 matched_at to NULL, then re-run the matcher against
    the existing signal data.

    Use case: matcher rules changed (e.g. expanded noise list,
    rarity filter) and we want to re-score everything in DB under
    the new rules. No re-scrape needed — everything recomputes from
    the raw_signals already present.

    Pass ?confirm=true to actually execute.
    """
    _require_admin(x_admin_key)

    if not confirm:
        raise HTTPException(
            400,
            "This deletes all matches and resets signal processing state. "
            "Pass ?confirm=true to proceed.",
        )

    from backend.harvesters import matcher
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # 1. Delete all existing matches
    del_res = (supa.table('raw_signal_matches_v3')
               .delete()
               .neq('id', -1)
               .execute())
    deleted_matches = len(del_res.data or [])

    # 2. Reset matched_at to NULL on all raw_signals so matcher will
    #    re-process them. Paginate to avoid row-limit issues.
    page = 1000
    offset = 0
    reset_count = 0
    while True:
        rows = (supa.table('raw_signals_v3')
                .select('id')
                .not_.is_('matched_at', 'null')
                .range(offset, offset + page - 1)
                .execute()).data or []
        if not rows:
            break
        ids = [r['id'] for r in rows]
        (supa.table('raw_signals_v3')
         .update({'matched_at': None})
         .in_('id', ids)
         .execute())
        reset_count += len(ids)
        if len(rows) < page:
            break
        # do NOT advance offset — updating rows to NULL may change the
        # result set; keep querying from 0 until empty

    # 3. Re-run matcher
    stats = matcher.process_unmatched(
        supa,
        zip_filter=zip_filter,
        batch_size=100,
        max_batches=500,
    )

    return {
        "deleted_matches": deleted_matches,
        "signals_reset": reset_count,
        "match_stats": stats,
    }


@router.post("/reset")
def harvest_reset(
    x_admin_key: Optional[str] = Header(None),
    confirm: bool = False,
):
    """
    Delete ALL rows from raw_signals_v3 and raw_signal_matches_v3.

    For pilot iteration only — gives us a clean slate to re-run
    harvesters after filter changes. Pass ?confirm=true to actually
    perform the delete.
    """
    _require_admin(x_admin_key)

    if not confirm:
        raise HTTPException(
            400,
            "This deletes all harvester data. Pass ?confirm=true to proceed.",
        )

    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # Cascade: delete raw_signals deletes raw_signal_matches via FK
    # But be explicit about both for safety + count reporting
    matches_res = (supa.table('raw_signal_matches_v3')
                   .delete()
                   .neq('id', -1)      # match all rows (id > 0)
                   .execute())
    signals_res = (supa.table('raw_signals_v3')
                   .delete()
                   .neq('id', -1)
                   .execute())

    return {
        "deleted_matches": len(matches_res.data or []),
        "deleted_signals": len(signals_res.data or []),
    }



@router.get("/status/{zip_code}")
def harvest_status(zip_code: str):
    """
    Summary of harvested signals and matches for a ZIP.

    Counts:
      - raw_signals_v3 rows total + by (source_type, signal_type)
      - raw_signals_v3 processed vs unmatched
      - raw_signal_matches_v3 rows scoped to this ZIP's parcels
      - Distinct matched parcels in this ZIP
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    # All raw signals — paginate because Supabase REST caps at 1000/req
    all_raw: list[dict] = []
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('raw_signals_v3')
               .select('source_type, signal_type, matched_at')
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        all_raw.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 500000:  # safety bound
            break

    by_source_type: dict = {}
    processed = 0
    for row in all_raw:
        key = f"{row['source_type']}::{row['signal_type']}"
        by_source_type[key] = by_source_type.get(key, 0) + 1
        if row.get('matched_at'):
            processed += 1

    # Pins in this ZIP — paginate because Supabase REST caps at 1000/req
    pins: list[str] = []
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin')
               .eq('zip_code', zip_code)
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        pins.extend(r['pin'] for r in batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 100000:
            break

    # Matches for parcels in this ZIP + distinct match pins
    matched_count = 0
    matched_pins: set = set()
    if pins:
        CHUNK = 200
        for i in range(0, len(pins), CHUNK):
            chunk = pins[i : i + CHUNK]
            res = (supa.table('raw_signal_matches_v3')
                   .select('pin', count='exact')
                   .in_('pin', chunk)
                   .limit(5000)
                   .execute())
            matched_count += res.count or 0
            for r in (res.data or []):
                matched_pins.add(r['pin'])

    return {
        "zip_code":              zip_code,
        "parcels_in_zip":        len(pins),
        "raw_signals_total":     len(all_raw),
        "raw_signals_processed": processed,
        "raw_signals_pending":   len(all_raw) - processed,
        "raw_signals_by_type":   by_source_type,
        "total_matches":         matched_count,
        "distinct_matched_pins": len(matched_pins),
    }


@router.get("/matches/{zip_code}")
def harvest_matches(
    zip_code: str,
    limit: int = 100,
    include_weak: bool = False,
):
    """
    The actual prospect list: matched parcels in this ZIP with their
    triggering signals.

    Returns one row per (parcel, signal) match, joined to parcel info
    and signal detail. Sorted by most recent event_date first.

    By default, weak-strength matches (surname-only, permissive name
    collisions) are filtered out. Weak matches are overwhelmingly false
    positives in practice — e.g. "John K Anderson" parcel matched to a
    "Mark John Anderson" divorce party because both share the surname.
    Use ?include_weak=true to see everything for debugging.
    """
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Supabase not configured")

    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be 1–1000")

    # Pins in this ZIP — paginate because Supabase REST caps at 1000/req
    parcels_by_pin: dict = {}
    PAGE = 1000
    offset = 0
    while True:
        res = (supa.table('parcels_v3')
               .select('pin, owner_name, address, city, total_value, owner_type')
               .eq('zip_code', zip_code)
               .range(offset, offset + PAGE - 1)
               .execute())
        batch = res.data or []
        for r in batch:
            parcels_by_pin[r['pin']] = r
        if len(batch) < PAGE:
            break
        offset += PAGE
        if offset > 100000:
            break
    pins = list(parcels_by_pin.keys())
    if not pins:
        return {"zip_code": zip_code, "matches": []}

    # Fetch matches for these pins
    all_matches: list[dict] = []
    CHUNK = 200
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i : i + CHUNK]
        q = (supa.table('raw_signal_matches_v3')
             .select('raw_signal_id, pin, match_strength, match_method, matched_at')
             .in_('pin', chunk)
             .limit(5000))
        if not include_weak:
            q = q.neq('match_strength', 'weak')
        res = q.execute()
        all_matches.extend(res.data or [])

    if not all_matches:
        return {"zip_code": zip_code, "matches": []}

    # Fetch the signal details for all matched raw_signal_ids
    signal_ids = list({m['raw_signal_id'] for m in all_matches})
    signals_by_id: dict = {}
    CHUNK_S = 300
    for i in range(0, len(signal_ids), CHUNK_S):
        chunk = signal_ids[i : i + CHUNK_S]
        res = (supa.table('raw_signals_v3')
               .select('id, source_type, signal_type, trust_level, party_names, '
                       'event_date, jurisdiction, document_ref, raw_data')
               .in_('id', chunk)
               .execute())
        for r in (res.data or []):
            signals_by_id[r['id']] = r

    # Enrich with case_parties (Personal Rep data). We fetch all parties
    # for the case_numbers we have signals for, then index by case_number.
    case_numbers = [
        s.get('document_ref') for s in signals_by_id.values()
        if s.get('document_ref') and s.get('source_type') == 'kc_superior_court'
    ]
    parties_by_case: dict = {}
    if case_numbers:
        CHUNK_C = 200
        for i in range(0, len(case_numbers), CHUNK_C):
            chunk = case_numbers[i : i + CHUNK_C]
            res = (supa.table('case_parties_v3')
                   .select('case_number, role, raw_role, name_raw, '
                           'name_last, name_first, name_middle, '
                           'represented_by, pr_classification')
                   .in_('case_number', chunk)
                   .execute())
            for p in (res.data or []):
                parties_by_case.setdefault(p['case_number'], []).append(p)

    # Assemble the response: one row per (parcel, signal)
    matches_out: list[dict] = []
    for m in all_matches:
        signal = signals_by_id.get(m['raw_signal_id'])
        parcel = parcels_by_pin.get(m['pin'])
        if not signal or not parcel:
            continue

        # Extract first party name for quick display
        parties = signal.get('party_names') or []
        first_party = parties[0].get('raw') if parties else None

        # Find Personal Rep (if any) from case_parties
        # Priority: 1) formal 'personal_representative' role,
        #          2) 'petitioner' role (usually the family member seeking
        #             to be appointed PR — workable lead even before formal
        #             appointment), 3) fallback: no PR.
        # Both roles are surfaced under personal_representative to keep
        # agent UX simple. pr_role field distinguishes.
        case_num = signal.get('document_ref')
        case_parties = parties_by_case.get(case_num, []) if case_num else []
        personal_rep = None
        pr_role_type = None
        for p in case_parties:
            if p['role'] == 'personal_representative':
                personal_rep = {
                    'name':           p['name_raw'],
                    'name_last':      p['name_last'],
                    'name_first':     p['name_first'],
                    'name_middle':    p['name_middle'],
                    'classification': p['pr_classification'],
                    'role_source':    'personal_representative',
                }
                pr_role_type = 'appointed_pr'
                break
        if not personal_rep:
            # Fallback: petitioner (most are family members seeking PR role)
            for p in case_parties:
                if p['role'] == 'petitioner':
                    personal_rep = {
                        'name':           p['name_raw'],
                        'name_last':      p['name_last'],
                        'name_first':     p['name_first'],
                        'name_middle':    p['name_middle'],
                        'classification': p.get('pr_classification') or 'family',
                        'role_source':    'petitioner',
                    }
                    pr_role_type = 'petitioner'
                    break

        # Compute actionability flag — the single bit of routing guidance
        # we surface at briefing level. Don't force agents to interpret
        # pr_classification strings.
        if personal_rep:
            if personal_rep['classification'] == 'family':
                contact_status = 'family_pr_identified'
            elif personal_rep['classification'] in ('corporate', 'attorney'):
                contact_status = 'unworkable_pr'
            else:
                contact_status = 'pr_unknown_classification'
        elif case_num and case_parties:
            contact_status = 'no_pr_yet'
        elif case_num:
            contact_status = 'parties_not_scraped'
        else:
            contact_status = 'not_applicable'

        matches_out.append({
            "pin":              m['pin'],
            "owner_name":       parcel.get('owner_name'),
            "owner_type":       parcel.get('owner_type'),
            "address":          parcel.get('address'),
            "city":             parcel.get('city'),
            "total_value":      parcel.get('total_value'),
            "signal_type":      signal['signal_type'],
            "signal_source":    signal['source_type'],
            "trust_level":      signal['trust_level'],
            "event_date":       signal.get('event_date'),
            "matched_party":    first_party,
            "all_parties":      parties,
            "document_ref":     signal.get('document_ref'),
            "case_detail":      signal.get('raw_data', {}),
            "match_strength":   m['match_strength'],
            "matched_at":       m['matched_at'],
            # NEW — contact routing data from Phase 1.5
            "personal_representative": personal_rep,
            "contact_status":          contact_status,
            "all_case_parties":        case_parties,
        })

    # Sort by event_date desc (most recent first), null dates at bottom
    matches_out.sort(
        key=lambda r: r.get('event_date') or '',
        reverse=True,
    )

    return {
        "zip_code":       zip_code,
        "total_matches":  len(matches_out),
        "returned":       min(limit, len(matches_out)),
        "matches":        matches_out[:limit],
    }
