"""
Marketplace demand side — buyer needs + matching engine. DARK LAUNCH.

Access model (strict, by design):
  - Every route requires EITHER a valid X-Admin-Key header OR an
    authenticated Supabase user whose email appears in the
    MARKETPLACE_ALLOWLIST env var (comma-separated, case-insensitive).
  - When neither passes, routes raise plain 404 — the feature is
    invisible, not forbidden. No 401/403 hints that it exists.
  - The router is mounted with include_in_schema=False so nothing
    appears in /openapi.json.
  - MARKETPLACE_ALLOWLIST unset/empty means: admin key only.

Design contracts (from the marketplace dossier, 2026-07-23):
  - Buyer side never searches supply. A need is a declared spec; the
    engine searches; the requester sees reports, never a browsable
    inventory. (During the dark phase the report is deliberately full —
    the visibility firewall between buyer-side and territory-side views
    is enforced at unlock, not here.)
  - Tier 1 criteria (universal in parcels_v3): zips, streets, price
    band, prop type. Hard-matched.
  - Tier 2 criteria (partial coverage — WA only today): year_built,
    sqft, acres. Hard-matched where the field is populated; recorded as
    "unknown" where it is not (rank-don't-reject). beds/baths are
    captured on the need but always unknown until the enrichment pass
    lands columns for them.
  - Tier 3 (soft_notes): stored, surfaced, never machine-matched.

Seller-likelihood tiers on each match:
  A — parcel has a court-verified signal match (raw_signal_matches_v3)
  B — structural archetype: trust 10y+, LLC 7y+, absentee, tenure 15y+
  C — everything else that survives the hard filters
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.api.db import get_supabase_client
from backend.api.auth import user_from_authorization

log = logging.getLogger(__name__)
router = APIRouter()

_MAX_ZIPS_PER_NEED = 12
_MAX_STORED_MATCHES = 500
_PAGE = 1000

_PARCEL_COLS = (
    'pin, zip_code, market_key, address, city, owner_name, owner_type, '
    'prop_type, total_value, sqft, year_built, acres, tenure_years, '
    'bedrooms, bathrooms, stories, year_renovated, waterfront, features, '
    'waterfront_footage, view_rating, '
    'is_absentee, is_vacant_land, band, signal_family, lat, lng'
)


# ---------------------------------------------------------------- gate

def _ledger(supa, actor: str, role: str, event: str, *,
            need_id: Optional[str] = None, zip_code: Optional[str] = None,
            counterparty: Optional[str] = None, payload: Optional[dict] = None):
    """Contract 3: append-only, recorded from the first interaction.
    Best-effort — a ledger hiccup never blocks the product path — but
    absence of the table is logged loudly because unrecorded history
    cannot be backfilled."""
    try:
        supa.table('network_ledger_v3').insert({
            'actor': actor, 'actor_role': role, 'event_type': event,
            'need_id': need_id, 'zip_code': zip_code,
            'counterparty': counterparty, 'payload': payload,
        }).execute()
    except Exception as exc:
        if _table_missing(exc):
            log.error('LEDGER TABLE MISSING (schema 038) — %s by %s NOT recorded',
                      event, actor)
        else:
            log.exception('ledger write failed: %s', event)


def _hidden() -> HTTPException:
    # Indistinguishable from a route that doesn't exist.
    return HTTPException(status_code=404, detail='Not Found')


def _gate(authorization: Optional[str], x_admin_key: Optional[str]) -> str:
    """Return the caller identity (email or 'admin') or raise a plain 404."""
    server_key = os.environ.get('ADMIN_KEY')
    if server_key and x_admin_key and x_admin_key == server_key:
        return 'admin'
    allowlist = {
        e.strip().lower()
        for e in os.environ.get('MARKETPLACE_ALLOWLIST', '').split(',')
        if e.strip()
    }
    if allowlist and authorization:
        try:
            user = user_from_authorization(authorization)
            email = (getattr(user, 'email', None) or '').lower()
            if email and email in allowlist:
                return email
        except HTTPException:
            pass
        except Exception:
            log.exception('marketplace gate: unexpected auth error')
    raise _hidden()


def _table_missing(exc: Exception) -> bool:
    s = str(exc)
    return 'PGRST205' in s or ('relation' in s and 'does not exist' in s) \
        or 'Could not find the table' in s


# ---------------------------------------------------------------- models

class NeedIn(BaseModel):
    zips: list[str] = Field(..., min_length=1, max_length=_MAX_ZIPS_PER_NEED)
    client_ref: Optional[str] = None
    streets: Optional[list[str]] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    prop_types: Optional[list[str]] = None
    beds_min: Optional[int] = None
    baths_min: Optional[float] = None
    year_built_min: Optional[int] = None
    year_built_max: Optional[int] = None
    sqft_min: Optional[int] = None
    acres_min: Optional[float] = None
    acres_max: Optional[float] = None
    waterfront: Optional[bool] = None
    view_min: Optional[int] = None
    stories_min: Optional[float] = None
    year_renovated_min: Optional[int] = None
    feature_filters: Optional[dict] = None
    soft_notes: Optional[str] = None
    attestation: bool = False
    expires_at: Optional[str] = None


class NeedPatch(BaseModel):
    status: Optional[str] = None
    client_ref: Optional[str] = None
    zips: Optional[list[str]] = Field(None, max_length=_MAX_ZIPS_PER_NEED)
    streets: Optional[list[str]] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    prop_types: Optional[list[str]] = None
    beds_min: Optional[int] = None
    baths_min: Optional[float] = None
    year_built_min: Optional[int] = None
    year_built_max: Optional[int] = None
    sqft_min: Optional[int] = None
    acres_min: Optional[float] = None
    acres_max: Optional[float] = None
    waterfront: Optional[bool] = None
    view_min: Optional[int] = None
    stories_min: Optional[float] = None
    year_renovated_min: Optional[int] = None
    feature_filters: Optional[dict] = None
    soft_notes: Optional[str] = None
    attestation: Optional[bool] = None
    expires_at: Optional[str] = None


# ---------------------------------------------------------------- helpers

def _fetch_all(supa, table: str, select_cols: str, zip_code: str) -> list[dict]:
    """Paginate past PostgREST's 1000-row cap (same pattern as briefings)."""
    out: list[dict] = []
    offset = 0
    while True:
        page = (supa.table(table).select(select_cols)
                .eq('zip_code', zip_code)
                .range(offset, offset + _PAGE - 1)
                .execute()).data or []
        out.extend(page)
        if len(page) < _PAGE:
            return out
        offset += _PAGE


def _zip_context(supa, zips: list[str]) -> dict:
    """live/unknown status per requested zip — unclaimed/unknown zips bank demand."""
    ctx = {z: {'coverage': 'unknown'} for z in zips}
    try:
        rows = (supa.table('zip_coverage_v3')
                .select('zip_code, status, market_key, city, state')
                .in_('zip_code', zips).execute()).data or []
        for r in rows:
            ctx[r['zip_code']] = {
                'coverage': r.get('status') or 'unknown',
                'market_key': r.get('market_key'),
                'city': r.get('city'),
                'state': r.get('state'),
            }
    except Exception:
        log.exception('marketplace: zip context lookup failed')
    return ctx


def _signal_band(n: int) -> Optional[str]:
    """Contract 1 banding: the buyer seat never sees a precise signal
    count. Floor: under 5, signal presence is not shown at all — this
    kills micro-varied-need triangulation while keeping the tease."""
    if n < 5:
        return None
    for lo, hi in ((5, 15), (15, 30), (30, 60), (60, 120)):
        if n < hi:
            return f"{lo}\u2013{hi}"
    return "120+"


def _claimed_zips(supa, zips: list[str]) -> set:
    try:
        rows = (supa.table('agent_profiles_v3').select('assigned_zip')
                .in_('assigned_zip', zips).execute()).data or []
        return {r['assigned_zip'] for r in rows if r.get('assigned_zip')}
    except Exception:
        log.exception('marketplace: claimed lookup failed')
        return set()


def _seller_tier(parcel: dict, signal_types: Optional[list[str]]) -> str:
    if signal_types:
        return 'A'
    tenure = parcel.get('tenure_years') or 0
    otype = (parcel.get('owner_type') or '').lower()
    if (otype == 'trust' and tenure >= 10) \
            or (otype == 'llc' and tenure >= 7) \
            or parcel.get('is_absentee') \
            or tenure >= 15:
        return 'B'
    return 'C'


def _evaluate(parcel: dict, need: dict, signal_types: Optional[list[str]]):
    """
    Returns (keep: bool, score: float, matched_on: [], unknown_on: [], tier)

    Hard-filter semantics:
      criterion set + field populated + fails  -> reject
      criterion set + field populated + passes -> matched_on
      criterion set + field null               -> unknown_on (kept, ranked down)
    """
    matched, unknown = [], []
    specified = 0

    def check(name, value, passes):
        nonlocal specified
        specified += 1
        if value is None:
            unknown.append(name)
            return True
        if passes(value):
            matched.append(name)
            return True
        return False

    # Price band — total_value is universal, so this is a true hard filter.
    pmin, pmax = need.get('price_min'), need.get('price_max')
    if pmin is not None or pmax is not None:
        tv = parcel.get('total_value')
        ok = check('price', tv, lambda v: (pmin is None or v >= pmin)
                                          and (pmax is None or v <= pmax))
        if not ok:
            return False, 0, [], [], 'C'

    # Streets — address is universal; hard filter when provided.
    streets = [s.strip().upper() for s in (need.get('streets') or []) if s.strip()]
    if streets:
        addr = (parcel.get('address') or '').upper()
        ok = check('street', addr or None,
                   lambda a: any(s in a for s in streets))
        if not ok:
            return False, 0, [], [], 'C'

    # Prop type — populated in WA only; unknown elsewhere.
    ptypes = [p.strip().upper() for p in (need.get('prop_types') or []) if p.strip()]
    if ptypes:
        pt = (parcel.get('prop_type') or '').strip().upper() or None
        if not check('prop_type', pt, lambda v: v in ptypes):
            return False, 0, [], [], 'C'

    # Tier-2 structure criteria — hard where populated, unknown where null.
    ranges = [
        ('year_built', parcel.get('year_built'),
         need.get('year_built_min'), need.get('year_built_max')),
        ('acres', parcel.get('acres'),
         need.get('acres_min'), need.get('acres_max')),
        ('sqft', parcel.get('sqft'), need.get('sqft_min'), None),
        ('beds', parcel.get('bedrooms'), need.get('beds_min'), None),
        ('baths', parcel.get('bathrooms'), need.get('baths_min'), None),
        ('stories', parcel.get('stories'), need.get('stories_min'), None),
        ('year_renovated', parcel.get('year_renovated'),
         need.get('year_renovated_min'), None),
        ('view', parcel.get('view_rating'), need.get('view_min'), None),
    ]
    for name, val, lo, hi in ranges:
        if lo is None and hi is None:
            continue
        if val == 0:
            val = None  # 0 means "not recorded" in every source we ingest
        if not check(name, val, lambda v, lo=lo, hi=hi:
                     (lo is None or v >= lo) and (hi is None or v <= hi)):
            return False, 0, [], [], 'C'

    # Waterfront — tri-state: criterion True/False, field bool-or-null.
    if need.get('waterfront') is not None:
        wf = parcel.get('waterfront')
        want = bool(need.get('waterfront'))
        # NULL means "no waterfront record" — for want=False that's a
        # pass (county flags waterfront affirmatively); for want=True
        # it's a reject, not an unknown, for the same reason.
        actual = bool(wf) if wf is not None else False
        specified += 1
        if actual == want:
            matched.append('waterfront')
        else:
            return False, 0, [], [], 'C'

    # Open-vocabulary feature filters. Key conventions:
    #   "<key>": true          -> parcel features[key] truthy; absent = unknown
    #   "<key>": false         -> require absent/false; absent = PASS
    #                             (counties flag these affirmatively)
    #   "<key>_min": N         -> features[key] >= N; absent = unknown
    #   "<key>_max": N         -> features[key] <= N; absent = PASS
    #   "<key>": "value"       -> equality (e.g. sewer: "public")
    #   "style_any": [...]     -> substring match on features.style
    #   "view_any": [...]      -> any listed category in features.views
    #                             with rating >= feature_filters.view_cat_min
    #                             (default 1); absent views = unknown
    ff = need.get('feature_filters') or {}
    fts = parcel.get('features') or {}
    for k, crit in ff.items():
        if k == 'view_cat_min':
            continue
        specified += 1
        name = f'ft:{k}'
        if k == 'view_any':
            vmin = ff.get('view_cat_min') or 1
            views = fts.get('views') or {}
            if not views:
                unknown.append(name)
            elif any((views.get(c) or 0) >= vmin for c in (crit or [])):
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        elif k == 'style_any':
            style = str(fts.get('style') or '')
            if not style:
                unknown.append(name)
            elif any(str(c).lower() in style for c in (crit or [])):
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        elif k.endswith('_min'):
            v = fts.get(k[:-4])
            if v is None:
                unknown.append(name)
            elif v >= crit:
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        elif k.endswith('_max'):
            v = fts.get(k[:-4])
            if v is None or v <= crit:
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        elif crit is False:
            if not fts.get(k):
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        elif crit is True:
            v = fts.get(k)
            if v is None:
                unknown.append(name)
            elif v:
                matched.append(name)
            else:
                return False, 0, [], [], 'C'
        else:  # equality
            v = fts.get(k)
            if v is None:
                unknown.append(name)
            elif str(v).lower() == str(crit).lower():
                matched.append(name)
            else:
                return False, 0, [], [], 'C'

    score = round(len(matched) / specified, 3) if specified else 1.0
    tier = _seller_tier(parcel, signal_types)
    return True, score, matched, unknown, tier


def _run_match(supa, need: dict) -> dict:
    zips = need.get('zips') or []
    tier_order = {'A': 0, 'B': 1, 'C': 2}
    all_matches: list[dict] = []
    per_zip: dict = {}
    candidates = 0
    field_cov = {'sqft': [0, 0], 'year_built': [0, 0], 'acres': [0, 0],
                 'prop_type': [0, 0], 'bedrooms': [0, 0], 'bathrooms': [0, 0],
                 'waterfront': [0, 0], 'view_rating': [0, 0]}  # populated, total

    for z in zips:
        parcels = _fetch_all(supa, 'parcels_v3', _PARCEL_COLS, z)
        candidates += len(parcels)

        # Court-signal pins for tier A. raw_signal_matches_v3 has no
        # zip_code column — query by pin chunks (same pattern as
        # harvest_matches). Strict-strength only: weak matches are
        # overwhelmingly false positives and tier A must stay accurate.
        signal_pins: dict[str, list[str]] = {}
        try:
            pins = [str(p.get('pin')) for p in parcels]
            match_rows: list[dict] = []
            for i in range(0, len(pins), 200):
                chunk = pins[i:i + 200]
                match_rows.extend(
                    (supa.table('raw_signal_matches_v3')
                     .select('pin, raw_signal_id, match_strength')
                     .in_('pin', chunk)
                     .eq('match_strength', 'strict')
                     .execute()).data or [])
            sig_ids = list({r['raw_signal_id'] for r in match_rows
                            if r.get('raw_signal_id') is not None})
            sig_types: dict = {}
            for i in range(0, len(sig_ids), 200):
                chunk = sig_ids[i:i + 200]
                for s in ((supa.table('raw_signals_v3')
                           .select('id, signal_type')
                           .in_('id', chunk).execute()).data or []):
                    sig_types[s['id']] = s.get('signal_type') or 'signal'
            for r in match_rows:
                signal_pins.setdefault(str(r.get('pin')), []).append(
                    sig_types.get(r.get('raw_signal_id'), 'signal'))
        except Exception:
            log.exception('marketplace: signal fetch failed for %s', z)

        zstats = {'candidates': len(parcels), 'matched': 0,
                  'tiers': {'A': 0, 'B': 0, 'C': 0}}
        for p in parcels:
            for f in field_cov:
                field_cov[f][1] += 1
                if p.get(f) not in (None, 0, ''):
                    field_cov[f][0] += 1
            sigs = signal_pins.get(str(p.get('pin')))
            keep, score, matched_on, unknown_on, tier = _evaluate(p, need, sigs)
            if not keep:
                continue
            zstats['matched'] += 1
            zstats['tiers'][tier] += 1
            all_matches.append({
                'pin': p.get('pin'),
                'zip_code': z,
                'score': score,
                'tier': tier,
                'matched_on': matched_on,
                'unknown_on': unknown_on,
                'detail': {
                    'address': p.get('address'),
                    'city': p.get('city'),
                    'owner_type': p.get('owner_type'),
                    'total_value': p.get('total_value'),
                    'sqft': p.get('sqft'),
                    'year_built': p.get('year_built'),
                    'bedrooms': p.get('bedrooms'),
                    'bathrooms': p.get('bathrooms'),
                    'stories': p.get('stories'),
                    'year_renovated': p.get('year_renovated'),
                    'waterfront': p.get('waterfront'),
                    'waterfront_footage': p.get('waterfront_footage'),
                    'view_rating': p.get('view_rating'),
                    'features': p.get('features'),
                    'acres': p.get('acres'),
                    'tenure_years': p.get('tenure_years'),
                    'is_absentee': p.get('is_absentee'),
                    'band': p.get('band'),
                    'signal_family': p.get('signal_family'),
                    'signal_types': sigs or [],
                    'lat': p.get('lat'),
                    'lng': p.get('lng'),
                },
            })
        per_zip[z] = zstats

    # Rank: seller tier first, then criteria fit, then price-band centering.
    pmin = need.get('price_min')
    pmax = need.get('price_max')
    mid = None
    if pmin is not None and pmax is not None:
        mid = (pmin + pmax) / 2

    def sort_key(m):
        dist = 0
        if mid:
            tv = m['detail'].get('total_value') or mid
            dist = abs(tv - mid) / mid
        return (tier_order[m['tier']], -m['score'], dist)

    all_matches.sort(key=sort_key)

    report = {
        'per_zip': per_zip,
        'tiers': {
            t: sum(s['tiers'][t] for s in per_zip.values())
            for t in ('A', 'B', 'C')
        },
        'field_coverage_pct': {
            f: round(100 * v[0] / v[1], 1) if v[1] else 0
            for f, v in field_cov.items()
        },
        'criteria': {k: need.get(k) for k in (
            'zips', 'streets', 'price_min', 'price_max', 'prop_types',
            'beds_min', 'baths_min', 'year_built_min', 'year_built_max',
            'sqft_min', 'acres_min', 'acres_max', 'waterfront', 'view_min',
            'stories_min', 'year_renovated_min', 'feature_filters')
            if need.get(k) is not None},
    }
    return {'candidates': candidates, 'matches': all_matches, 'report': report}


# ---------------------------------------------------------------- routes

@router.get('/status')
async def marketplace_status(authorization: Optional[str] = Header(None),
                             x_admin_key: Optional[str] = Header(None)):
    who = _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    schema_ok = True
    try:
        supa.table('buyer_needs_v3').select('id').limit(1).execute()
    except Exception as exc:
        schema_ok = not _table_missing(exc)
    allowlist_set = bool(os.environ.get('MARKETPLACE_ALLOWLIST', '').strip())
    return {'ok': True, 'caller': who, 'schema_applied': schema_ok,
            'allowlist_active': allowlist_set}


@router.get('/filters')
async def filter_availability(zips: str,
                              authorization: Optional[str] = Header(None),
                              x_admin_key: Optional[str] = Header(None)):
    """
    Per-ZIP filter availability: which core columns and feature keys are
    populated, and on how many parcels. This is what makes the need form
    data-driven — a ZIP only offers filters the county actually grades
    there (lake views on Mercer Island, golf adjacency in Scottsdale,
    style in MA). Also the enrichment-gap readout per territory.
    """
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    zlist = [z.strip() for z in zips.split(',') if z.strip()][:12]
    out = {}
    CORE = ('total_value', 'sqft', 'year_built', 'bedrooms', 'bathrooms',
            'stories', 'acres', 'year_renovated', 'waterfront',
            'view_rating', 'prop_type')
    for z in zlist:
        rows = _fetch_all(supa, 'parcels_v3',
                          ', '.join(CORE) + ', features', z)
        core_counts = {c: 0 for c in CORE}
        feat_counts: dict = {}
        view_counts: dict = {}
        for r in rows:
            for c in CORE:
                if r.get(c) not in (None, 0, ''):
                    core_counts[c] += 1
            for k, v in (r.get('features') or {}).items():
                if k == 'views':
                    for cat in (v or {}):
                        view_counts[cat] = view_counts.get(cat, 0) + 1
                elif v not in (None, 0, '', False):
                    feat_counts[k] = feat_counts.get(k, 0) + 1
        out[z] = {'parcels': len(rows), 'core': core_counts,
                  'features': dict(sorted(feat_counts.items(),
                                          key=lambda x: -x[1])),
                  'views': view_counts}
    return {'filters': out}


@router.get('/ledger')
async def ledger_peek(limit: int = 30,
                      actor: Optional[str] = None,
                      need_id: Optional[str] = None,
                      authorization: Optional[str] = Header(None),
                      x_admin_key: Optional[str] = Header(None)):
    """Dark-phase observation window into the credibility ledger."""
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    q = (supa.table('network_ledger_v3').select('*')
         .order('created_at', desc=True).limit(min(limit, 200)))
    if actor:
        q = q.eq('actor', actor)
    if need_id:
        q = q.eq('need_id', need_id)
    rows = q.execute().data or []
    return {'events': rows, 'count': len(rows)}


@router.post('/needs')
async def create_need(body: NeedIn,
                      authorization: Optional[str] = Header(None),
                      x_admin_key: Optional[str] = Header(None)):
    who = _gate(authorization, x_admin_key)
    supa = get_supabase_client()

    # Attestation is the accountability moment (dossier §3) — not optional.
    if not body.attestation:
        raise HTTPException(422, 'attestation required: you must confirm this '
                                 'search represents a specific, real client')

    # Two confirmed no-real-buyer flags terminate the seat (Contract 3).
    try:
        flags = (supa.table('network_ledger_v3').select('id')
                 .eq('event_type', 'flag_confirmed').eq('counterparty', who)
                 .limit(2).execute()).data or []
        if len(flags) >= 2:
            raise _hidden()
    except HTTPException:
        raise
    except Exception:
        pass

    # Cap: 5 active needs per seat — scarcity keeps specs honest.
    try:
        active = (supa.table('buyer_needs_v3').select('id')
                  .eq('created_by', who).eq('status', 'active')
                  .limit(6).execute()).data or []
        if len(active) >= 5:
            raise HTTPException(422, 'active search limit reached (5) — '
                                     'close or withdraw one first')
    except HTTPException:
        raise
    except Exception:
        pass

    row = body.model_dump(exclude_none=True)
    row['created_by'] = who
    if not row.get('expires_at'):
        from datetime import timedelta
        row['expires_at'] = (datetime.now(timezone.utc)
                             + timedelta(days=60)).isoformat()
    try:
        res = supa.table('buyer_needs_v3').insert(row).execute()
    except Exception as exc:
        if _table_missing(exc):
            raise HTTPException(503, 'schema 034 not applied')
        raise
    need = (res.data or [{}])[0]
    criteria_keys = [k for k in row if k not in
                     ('created_by', 'client_ref', 'attestation', 'zips',
                      'soft_notes', 'expires_at')]
    _ledger(supa, who, 'buyer_seat', 'need_posted', need_id=need.get('id'),
            payload={'zips': body.zips, 'specificity': len(criteria_keys),
                     'criteria_keys': criteria_keys,
                     'attestation': body.attestation})
    return {'need': need, 'zip_context': _zip_context(supa, body.zips)}


@router.get('/needs')
async def list_needs(status: Optional[str] = None,
                     authorization: Optional[str] = Header(None),
                     x_admin_key: Optional[str] = Header(None)):
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    q = supa.table('buyer_needs_v3').select('*').order('created_at', desc=True)
    if status:
        q = q.eq('status', status)
    try:
        rows = q.limit(200).execute().data or []
    except Exception as exc:
        if _table_missing(exc):
            raise HTTPException(503, 'schema 034 not applied')
        raise

    # Lazy expiry: 60 days, then the need dies quietly (dossier §3).
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        if r.get('status') == 'active' and r.get('expires_at') \
                and r['expires_at'] < now:
            try:
                supa.table('buyer_needs_v3').update(
                    {'status': 'expired'}).eq('id', r['id']).execute()
                r['status'] = 'expired'
                _ledger(supa, 'system', 'system', 'need_expired',
                        need_id=r['id'])
            except Exception:
                pass

    # Status ladder from the ledger: pursuits + open connections per need.
    try:
        ids = [r['id'] for r in rows]
        if ids:
            ev = (supa.table('network_ledger_v3')
                  .select('need_id, event_type, actor, zip_code, created_at')
                  .in_('need_id', ids)
                  .in_('event_type', ['ping_pursued', 'connection_opened'])
                  .order('created_at', desc=True).limit(500).execute()
                  ).data or []
            by_need: dict = {}
            for e in ev:
                d = by_need.setdefault(e['need_id'],
                                       {'pursuing': set(), 'connections': []})
                if e['event_type'] == 'ping_pursued':
                    d['pursuing'].add(e['actor'])
                else:
                    d['connections'].append({'agent': e['actor'],
                                             'zip': e.get('zip_code'),
                                             'opened_at': e.get('created_at')})
            for r in rows:
                d = by_need.get(r['id'])
                r['pursuit_count'] = len(d['pursuing']) if d else 0
                r['connections'] = d['connections'] if d else []
    except Exception:
        log.exception('needs status-ladder enrichment failed')

    return {'needs': rows, 'count': len(rows)}


@router.get('/demand/{zip_code}')
async def demand_for_zip(zip_code: str,
                         authorization: Optional[str] = Header(None),
                         x_admin_key: Optional[str] = Header(None)):
    """
    SUPPLY-SIDE view: active briefs touching this ZIP, each with the
    latest run's matches IN THIS ZIP at full detail (addresses, pins) —
    the territory owner's attack list. Buyer identity and client_ref are
    withheld; the demand spec travels, the buyer stays blind too.
    """
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    needs = (supa.table('buyer_needs_v3').select('*')
             .contains('zips', [zip_code])
             .eq('status', 'active')
             .order('created_at', desc=True).limit(50).execute()).data or []
    out = []
    for n in needs:
        runs = (supa.table('need_match_runs_v3')
                .select('id, run_at, matched')
                .eq('need_id', n['id']).order('run_at', desc=True)
                .limit(1).execute()).data or []
        matches = []
        tiers = {'A': 0, 'B': 0, 'C': 0}
        if runs:
            rows = (supa.table('need_matches_v3').select('*')
                    .eq('run_id', runs[0]['id']).eq('zip_code', zip_code)
                    .order('tier').order('score', desc=True)
                    .limit(100).execute()).data or []
            for m in rows:
                tiers[m.get('tier') or 'C'] = tiers.get(m.get('tier') or 'C', 0) + 1
            matches = rows
        criteria = {k: n.get(k) for k in (
            'zips', 'streets', 'price_min', 'price_max', 'prop_types',
            'beds_min', 'baths_min', 'year_built_min', 'year_built_max',
            'sqft_min', 'acres_min', 'acres_max', 'feature_filters',
            'soft_notes') if n.get(k) is not None}
        out.append({
            'need_id': n['id'],
            'posted_by': n.get('created_by'),
            'posted_at': n.get('created_at'),
            'criteria': criteria,
            'last_run_at': runs[0]['run_at'] if runs else None,
            'tiers_in_zip': tiers,
            'matches_in_zip': matches,
        })
    who = _gate(authorization, x_admin_key)
    if out:
        _ledger(supa, who, 'territory_owner', 'demand_viewed',
                zip_code=zip_code,
                payload={'need_ids': [b['need_id'] for b in out]})
    return {'zip_code': zip_code, 'briefs': out, 'count': len(out)}


@router.post('/demand/{zip_code}/{need_id}/respond')
async def respond_to_demand(zip_code: str, need_id: str, action: str,
                            authorization: Optional[str] = Header(None),
                            x_admin_key: Optional[str] = Header(None)):
    """
    Territory owner -> platform: pursue / ignore / decline (dossier §4).
    Feeds the ledger on both sides. 'pursue' is the pre-connection
    commitment; the connection-open handshake is a later phase.
    """
    who = _gate(authorization, x_admin_key)
    if action not in ('pursue', 'ignore', 'decline'):
        raise HTTPException(422, "action must be pursue | ignore | decline")
    supa = get_supabase_client()
    rows = (supa.table('buyer_needs_v3').select('id, created_by')
            .eq('id', need_id).limit(1).execute()).data or []
    if not rows:
        raise _hidden()
    _ledger(supa, who, 'territory_owner', f'ping_{action}d'
            if action != 'pursue' else 'ping_pursued',
            need_id=need_id, zip_code=zip_code,
            counterparty=rows[0].get('created_by'))
    return {'ok': True, 'action': action}


@router.post('/demand/{zip_code}/{need_id}/connect')
async def open_connection(zip_code: str, need_id: str,
                          authorization: Optional[str] = Header(None),
                          x_admin_key: Optional[str] = Header(None)):
    """
    Territory owner opens the connection: their identity crosses to the
    buyer seat (the contact handoff — Phase 2's payoff of Pursue). The
    buyer sees who and which territory; everything before this stayed
    blind.
    """
    who = _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    rows = (supa.table('buyer_needs_v3').select('id, created_by')
            .eq('id', need_id).limit(1).execute()).data or []
    if not rows:
        raise _hidden()
    _ledger(supa, who, 'territory_owner', 'connection_opened',
            need_id=need_id, zip_code=zip_code,
            counterparty=rows[0].get('created_by'))
    return {'ok': True, 'connection': {'agent': who, 'zip': zip_code}}


@router.post('/demand/{zip_code}/{need_id}/rate')
async def rate_connection(zip_code: str, need_id: str,
                          rating: int, client_was_real: bool = True,
                          authorization: Optional[str] = Header(None),
                          x_admin_key: Optional[str] = Header(None)):
    """
    Post-connection peer rating (Contract 3). A not-real-client report
    also raises an integrity flag; two CONFIRMED flags terminate the
    seat. Ratings feed standing; they never gate.
    """
    who = _gate(authorization, x_admin_key)
    if not 1 <= rating <= 5:
        raise HTTPException(422, 'rating must be 1-5')
    supa = get_supabase_client()
    rows = (supa.table('buyer_needs_v3').select('id, created_by')
            .eq('id', need_id).limit(1).execute()).data or []
    if not rows:
        raise _hidden()
    poster = rows[0].get('created_by')
    _ledger(supa, who, 'territory_owner', 'connection_rated',
            need_id=need_id, zip_code=zip_code, counterparty=poster,
            payload={'rating': rating, 'client_was_real': client_was_real})
    if not client_was_real:
        _ledger(supa, who, 'territory_owner', 'flag_raised',
                need_id=need_id, zip_code=zip_code, counterparty=poster,
                payload={'reason': 'no_real_buyer'})
    return {'ok': True}


@router.get('/needs/{need_id}')
async def get_need(need_id: str,
                   authorization: Optional[str] = Header(None),
                   x_admin_key: Optional[str] = Header(None)):
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    rows = (supa.table('buyer_needs_v3').select('*')
            .eq('id', need_id).limit(1).execute()).data or []
    if not rows:
        raise _hidden()
    runs = (supa.table('need_match_runs_v3')
            .select('id, run_at, candidates, matched, report')
            .eq('need_id', need_id).order('run_at', desc=True)
            .limit(5).execute()).data or []
    return {'need': rows[0], 'runs': runs,
            'zip_context': _zip_context(supa, rows[0].get('zips') or [])}


@router.patch('/needs/{need_id}')
async def patch_need(need_id: str, body: NeedPatch,
                     authorization: Optional[str] = Header(None),
                     x_admin_key: Optional[str] = Header(None)):
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(422, 'no fields to update')
    updates['updated_at'] = datetime.now(timezone.utc).isoformat()
    res = (supa.table('buyer_needs_v3').update(updates)
           .eq('id', need_id).execute())
    if not res.data:
        raise _hidden()
    who2 = _gate(authorization, x_admin_key)
    event = 'need_withdrawn' if updates.get('status') in ('fulfilled', 'paused') \
        else 'need_updated'
    _ledger(supa, who2, 'buyer_seat', event, need_id=need_id,
            payload={'fields': sorted(k for k in updates if k != 'updated_at')})
    return {'need': res.data[0]}


@router.post('/needs/{need_id}/match')
async def run_match(need_id: str,
                    authorization: Optional[str] = Header(None),
                    x_admin_key: Optional[str] = Header(None)):
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    rows = (supa.table('buyer_needs_v3').select('*')
            .eq('id', need_id).limit(1).execute()).data or []
    if not rows:
        raise _hidden()
    need = rows[0]

    result = _run_match(supa, need)
    matches = result['matches']

    run = (supa.table('need_match_runs_v3').insert({
        'need_id': need_id,
        'candidates': result['candidates'],
        'matched': len(matches),
        'report': result['report'],
    }).execute()).data[0]

    to_store = matches[:_MAX_STORED_MATCHES]
    if to_store:
        payload = [{
            'run_id': run['id'], 'need_id': need_id,
            'pin': m['pin'], 'zip_code': m['zip_code'],
            'score': m['score'], 'tier': m['tier'],
            'matched_on': m['matched_on'], 'unknown_on': m['unknown_on'],
            'detail': m['detail'],
        } for m in to_store]
        for i in range(0, len(payload), 500):
            supa.table('need_matches_v3').insert(payload[i:i + 500]).execute()

    tiers = result['report'].get('tiers', {})
    signals = (tiers.get('A', 0) or 0) + (tiers.get('B', 0) or 0)
    claimed = _claimed_zips(supa, need.get('zips') or [])
    buyer_view = {
        'matched': len(matches),
        'signal_band': _signal_band(signals),
        'zips': {
            z: {
                'matched': st.get('matched', 0),
                'territory': 'claimed' if z in claimed else 'open',
            }
            for z, st in result['report'].get('per_zip', {}).items()
        },
    }
    _ledger(supa, 'system', 'system', 'match_run', need_id=need_id,
            payload={'matched': len(matches), 'tiers': tiers,
                     'zips': list((result['report'].get('per_zip') or {}).keys()),
                     'claimed_zips_pinged': sorted(claimed)})

    return {
        'run_id': run['id'],
        'candidates': result['candidates'],
        'matched': len(matches),
        'stored': len(to_store),
        'buyer_view': buyer_view,
        'report': result['report'],
    }


@router.get('/needs/{need_id}/report')
async def match_report(need_id: str,
                       limit: int = 50,
                       tier: Optional[str] = None,
                       authorization: Optional[str] = Header(None),
                       x_admin_key: Optional[str] = Header(None)):
    _gate(authorization, x_admin_key)
    supa = get_supabase_client()
    runs = (supa.table('need_match_runs_v3')
            .select('id, run_at, candidates, matched, report')
            .eq('need_id', need_id).order('run_at', desc=True)
            .limit(1).execute()).data or []
    if not runs:
        raise HTTPException(404, 'no match runs for this need')
    run = runs[0]
    q = (supa.table('need_matches_v3').select('*')
         .eq('run_id', run['id'])
         .order('tier').order('score', desc=True))
    if tier:
        q = q.eq('tier', tier.upper())
    matches = q.limit(min(limit, _MAX_STORED_MATCHES)).execute().data or []
    return {'run': run, 'matches': matches, 'count': len(matches)}
