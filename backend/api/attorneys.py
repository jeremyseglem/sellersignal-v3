"""
Attorney map — the repeat-filing counsel a territory's agent should know.

Step 2 of the conversion thesis (strategy doc, 2026-10-22): estate and
divorce sellers pick agents who read as process-safe, and the attorneys
are the gatekeepers. Every harvested filing already carries party data;
this rolls it up into a ranked roster per state/market.

Coverage honesty (from live data inspection, 2026-10-22):
  - WA_SNOHOMISH divorce filings: explicit {'role': 'attorney'} parties.
  - MT_* and Maricopa probate: an 'attorney' field on petitioner/PR rows.
  - WA_KING probate: parties live in case_parties_v3, not party_names —
    KC attorneys are a FOLLOW-UP (the endpoint reports its own gaps).

Aggregation is state-level: jurisdictions map to states, not ZIPs, and
sample honesty beats false precision (per the market-genome rule).
Cached in-process for 6h per state.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from backend.api.auth import user_from_authorization
from backend.api.db import get_supabase_client
from backend.api.territory import require_zip_access

router = APIRouter()

_cache: dict[str, tuple[float, dict]] = {}
_TTL = 6 * 3600
_MAX_ROWS = 25000


def _jurisdiction_filters(state: str) -> list:
    """supabase-py filters for a state's jurisdiction spellings."""
    fs = [('like', f'{state}_%')]
    if state == 'AZ':
        fs.append(('eq', 'Maricopa County'))
    return fs


def _harvest_attorneys(supa, state: str) -> dict:
    rows = []
    for op, val in _jurisdiction_filters(state):
        off = 0
        while off < _MAX_ROWS:
            q = (supa.table('raw_signals_v3')
                 .select('signal_type, jurisdiction, party_names, event_date'))
            q = q.like('jurisdiction', val) if op == 'like' else q.eq('jurisdiction', val)
            res = q.range(off, off + 999).execute()
            batch = res.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            off += 1000

    agg: dict[str, dict] = defaultdict(
        lambda: {'filings': 0, 'case_types': set(), 'jurisdictions': set(),
                 'first_seen': None, 'last_seen': None})
    attorney_rows = 0
    for r in rows:
        names = []
        for p in (r.get('party_names') or []):
            if not isinstance(p, dict):
                continue
            if p.get('role') == 'attorney' and p.get('raw'):
                names.append(p['raw'])
            att = p.get('attorney')
            if att and isinstance(att, str):
                names.append(att)
        if not names:
            continue
        attorney_rows += 1
        ev = r.get('event_date')
        for n in set(x.strip() for x in names if x and x.strip()):
            a = agg[n.title() if n.isupper() else n]
            a['filings'] += 1
            a['case_types'].add(r.get('signal_type') or 'unknown')
            a['jurisdictions'].add(r.get('jurisdiction') or '')
            if ev:
                a['first_seen'] = min(a['first_seen'] or ev, ev)
                a['last_seen'] = max(a['last_seen'] or ev, ev)

    roster = sorted(
        ({'name': k, 'filings': v['filings'],
          'case_types': sorted(v['case_types']),
          'jurisdictions': sorted(j for j in v['jurisdictions'] if j),
          'first_seen': v['first_seen'], 'last_seen': v['last_seen']}
         for k, v in agg.items()),
        key=lambda x: -x['filings'])
    gaps = []
    if state == 'WA':
        gaps.append('King County probate attorneys are not yet extracted '
                    '(KC parties live in case_parties_v3) — Snohomish and '
                    'divorce counsel are covered.')
    return {
        'state': state,
        'signals_scanned': len(rows),
        'signals_with_attorneys': attorney_rows,
        'attorneys': roster[:100],
        'coverage_gaps': gaps,
    }


@router.get("/attorney-map/{zip_code}")
async def attorney_map(
    zip_code: str,
    authorization: Optional[str] = Header(None),
):
    """Ranked repeat-filing counsel for the requesting agent's state.
    Access mirrors briefings: agents for their own ZIP, operators all."""
    user = user_from_authorization(authorization)
    require_zip_access(user, zip_code)
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")
    cov = (supa.table('zip_coverage_v3')
           .select('state, market_key, city')
           .eq('zip_code', zip_code).maybe_single().execute())
    if not cov or not cov.data:
        raise HTTPException(404, f'ZIP {zip_code} not in coverage')
    state = cov.data.get('state')
    if not state:
        raise HTTPException(422, f'ZIP {zip_code} has no state on coverage')
    hit = _cache.get(state)
    if hit and time.time() - hit[0] < _TTL:
        data = hit[1]
    else:
        data = _harvest_attorneys(supa, state)
        _cache[state] = (time.time(), data)
    return {'zip_code': zip_code, 'market_key': cov.data.get('market_key'),
            'city': cov.data.get('city'), **data}
