"""
Tests for repair #7 (2026-10-28): /rematch-reset-scoped must never delete
retired match rows, and the matcher's re-insert must never clear a
retirement.

The incident: 2026-10-26 a scoped reset of kc_superior_court (probate
13,283 + divorce 8,240 signals) deleted every raw_signal_matches_v3 row for
those signals, retired rows included, and the rematch re-created them as
live matches (match_review_status NULL). 669 parcels / 932 matches were
re-retired by hand on 10-27.

No network and no database: the Supabase client is a fake that implements
the PostgREST filters the endpoint uses (eq, in, is/not.is, or=(... is.null,
... not.like.x*)) and PostgREST's upsert semantics with an explicit
`columns=` list (merge-duplicates updates only the payload's columns —
postgrest-py 0.17.2 always sends columns=<payload keys>). The same two
statements were also run as SQL against a local Postgres 16 (PR evidence).

Run: python tests/test_rematch_reset_keep_retired.py
"""
from __future__ import annotations

import fnmatch
import sys
sys.path.insert(0, '.')

from backend.api import harvest as H
from backend.harvesters import matcher as M

FAILS = 0
PASSES = 0


def t(label, got, want):
    global FAILS, PASSES
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r}\n         want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


# ---- fake Supabase ---------------------------------------------------------
class _Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = len(data) if count is None else count


def _or_term(row, term):
    """One PostgREST or= term: col.is.null | col.not.like.pat | col.like.pat"""
    col, rest = term.split('.', 1)
    val = row.get(col)
    if rest == 'is.null':
        return val is None
    neg = rest.startswith('not.')
    if neg:
        rest = rest[4:]
    op, pat = rest.split('.', 1)
    assert op == 'like', f"fake supports like only, got {op}"
    if val is None:            # SQL: NULL LIKE x and NULL NOT LIKE x are NULL
        return False
    hit = fnmatch.fnmatchcase(val, pat)
    return (not hit) if neg else hit


class _Not:
    def __init__(self, q): self.q = q
    def is_(self, col, _null):
        self.q.filters.append(('notnull', col, None)); return self.q


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []
        self.op, self.payload, self.rng, self.on_conflict = 'select', None, None, None

    def select(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def eq(self, col, val): self.filters.append(('eq', col, val)); return self
    def in_(self, col, vals): self.filters.append(('in', col, set(vals))); return self
    def is_(self, col, _null): self.filters.append(('isnull', col, None)); return self
    def or_(self, expr): self.filters.append(('or', expr, None)); return self
    def range(self, a, b): self.rng = (a, b); return self
    @property
    def not_(self): return _Not(self)
    def update(self, payload): self.op, self.payload = 'update', payload; return self
    def delete(self): self.op = 'delete'; return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload, self.on_conflict = 'upsert', payload, on_conflict
        return self

    def _match(self, row):
        for kind, col, val in self.filters:
            if kind == 'eq' and row.get(col) != val:
                return False
            if kind == 'in' and row.get(col) not in val:
                return False
            if kind == 'isnull' and row.get(col) is not None:
                return False
            if kind == 'notnull' and row.get(col) is None:
                return False
            if kind == 'or' and not any(_or_term(row, x) for x in col.split(',')):
                return False
        return True

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.op == 'select':
            out = [r for r in rows if self._match(r)]
            n = len(out)
            if self.rng:
                out = out[self.rng[0]:self.rng[1] + 1]
            return _Res(out, n)
        if self.op == 'update':
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
            return _Res([])
        if self.op == 'delete':
            gone = [r for r in rows if self._match(r)]
            self.db[self.table] = [r for r in rows if not self._match(r)]
            self.db.setdefault('_deleted', []).extend(gone)
            return _Res(gone)
        # upsert: ON CONFLICT (keys) DO UPDATE SET <payload columns only>
        keys = self.on_conflict.split(',')
        payload = self.payload if isinstance(self.payload, list) else [self.payload]
        for p in payload:
            hit = next((r for r in rows
                        if all(r.get(k) == p.get(k) for k in keys)), None)
            if hit is not None:
                hit.update(p)
            else:
                new = {'id': max([r['id'] for r in rows] or [0]) + 1,
                       'match_review_status': None, 'matched_at': 'now'}
                new.update(p)
                rows.append(new)
        return _Res(payload)


class _Supa:
    def __init__(self, db): self.db = db
    def table(self, name): return _Q(self.db, name)


def _db():
    return {
        'raw_signals_v3': [
            {'id': 1, 'source_type': 'kc_superior_court', 'signal_type': 'probate',
             'matched_at': '2026-10-23T00:00:00Z', 'match_count': 3},
            {'id': 2, 'source_type': 'kc_superior_court', 'signal_type': 'probate',
             'matched_at': '2026-10-23T00:00:00Z', 'match_count': 1},
            {'id': 3, 'source_type': 'kc_superior_court', 'signal_type': 'divorce',
             'matched_at': '2026-10-23T00:00:00Z', 'match_count': 1},
        ],
        'raw_signal_matches_v3': [
            {'id': 10, 'raw_signal_id': 1, 'pin': '0000000001', 'match_strength': 'strict',
             'match_method': 'legacy::probate', 'match_review_status': 'retired_sold_assessor'},
            {'id': 11, 'raw_signal_id': 1, 'pin': '0000000002', 'match_strength': 'strict',
             'match_method': 'legacy::probate', 'match_review_status': None},
            {'id': 12, 'raw_signal_id': 1, 'pin': '0000000003', 'match_strength': 'weak',
             'match_method': 'legacy::probate', 'match_review_status': 'likely_false_positive'},
            {'id': 13, 'raw_signal_id': 2, 'pin': '0000000004', 'match_strength': 'strict',
             'match_method': 'legacy::probate', 'match_review_status': 'retired_ownership_change'},
            {'id': 14, 'raw_signal_id': 2, 'pin': '0000000005', 'match_strength': 'strict',
             'match_method': 'legacy::probate', 'match_review_status': 'retired_sold'},
            # out of scope (divorce) — must be untouched by a probate reset
            {'id': 15, 'raw_signal_id': 3, 'pin': '0000000006', 'match_strength': 'strict',
             'match_method': 'legacy::divorce', 'match_review_status': None},
        ],
    }


def _status(db):
    return {r['pin']: r['match_review_status'] for r in db['raw_signal_matches_v3']}


# ---- tests ------------------------------------------------------------------
def test_filter_wire_format():
    print("filter: the or= clause postgrest-py sends")
    from postgrest import SyncPostgrestClient
    b = (SyncPostgrestClient("http://x/rest/v1")
         .from_('raw_signal_matches_v3').delete()
         .in_('raw_signal_id', [1, 2]).or_(H._NOT_RETIRED_FILTER))
    t("method DELETE", b.http_method, 'DELETE')
    t("or clause", dict(b.params).get('or'),
      '(match_review_status.is.null,match_review_status.not.like.retired*)')
    t("raw_signal_id clause", dict(b.params).get('raw_signal_id'), 'in.(1,2)')


def test_or_term_semantics():
    print("filter: per-status verdict (True = deletable)")
    def deletable(s):
        return any(_or_term({'match_review_status': s}, x)
                   for x in H._NOT_RETIRED_FILTER.split(','))
    for s, want in [(None, True), ('likely_valid', True), ('needs_review', True),
                    ('likely_false_positive', True),
                    ('retired_sold_assessor', False), ('retired_ownership_change', False),
                    ('retired_foreclosure', False), ('retired_sold', False)]:
        t(f"{s!r} deletable={want}", deletable(s), want)


def test_scoped_reset_keeps_retired():
    print("endpoint: /rematch-reset-scoped kc_superior_court x probate")
    db = _db()
    H.get_supabase_client = lambda: _Supa(db)
    H._require_admin = lambda _k: None
    out = H.harvest_rematch_reset_scoped(
        source_type='kc_superior_court', signal_type='probate',
        x_admin_key='x', confirm=True)
    t("signals_reset 2", out['signals_reset'], 2)
    t("signals_unmatched_in_scope 2", out['signals_unmatched_in_scope'], 2)
    st = _status(db)
    t("retired_sold_assessor kept", st.get('0000000001'), 'retired_sold_assessor')
    t("retired_ownership_change kept", st.get('0000000004'), 'retired_ownership_change')
    t("retired_sold kept", st.get('0000000005'), 'retired_sold')
    t("un-reviewed live row deleted (stale-match cleanup still works)",
      '0000000002' in st, False)
    t("likely_false_positive row deleted", '0000000003' in st, False)
    t("out-of-scope divorce row untouched", st.get('0000000006', 'GONE'), None)
    sig = {r['id']: r for r in db['raw_signals_v3']}
    t("probate signals matched_at reset", (sig[1]['matched_at'], sig[2]['matched_at']),
      (None, None))
    t("divorce signal untouched", sig[3]['matched_at'], '2026-10-23T00:00:00Z')
    return db


def test_reset_then_rematch_stays_retired():
    print("reset + matcher re-insert: retired rows stay retired")
    db = test_scoped_reset_keeps_retired()
    owners = {p: {'market_key': 'WA_KING', 'owner_name': 'X'} for p in
              ('0000000001', '0000000002', '0000000004', '0000000005')}
    by_sig = {1: ['0000000001', '0000000002'], 2: ['0000000004', '0000000005']}

    def fake_dispatch(row, owners_db, use_codes):
        return [{'parcel_id': p,
                 'trigger_hint': {'match_method': 'county_resolved::test',
                                  'match_strength': 'strict'}}
                for p in by_sig[row['id']]]

    saved = M._DISPATCH.get('probate')
    M._DISPATCH['probate'] = fake_dispatch
    try:
        supa = _Supa(db)
        for sid in (1, 2):
            row = dict(next(r for r in db['raw_signals_v3'] if r['id'] == sid))
            row['party_names'] = []
            n = M._process_one(supa, row, owners, {}, None)
            t(f"signal {sid}: matcher wrote 2 rows", n, 2)
    finally:
        M._DISPATCH['probate'] = saved
    st = _status(db)
    t("pin 1 still retired_sold_assessor", st.get('0000000001'), 'retired_sold_assessor')
    t("pin 4 still retired_ownership_change", st.get('0000000004'), 'retired_ownership_change')
    t("pin 5 still retired_sold", st.get('0000000005'), 'retired_sold')
    t("pin 2 re-created live (status NULL)", st.get('0000000002', 'GONE'), None)
    rows = [r for r in db['raw_signal_matches_v3'] if r['pin'] == '0000000001']
    t("no duplicate row for pin 1", len(rows), 1)
    sig = {r['id']: r for r in db['raw_signals_v3']}
    t("signals re-stamped matched", all(sig[i]['matched_at'] for i in (1, 2)), True)


def test_old_behaviour_would_unretire():
    print("control: the pre-fix delete (no or= filter) un-retires")
    db = _db()
    supa = _Supa(db)
    (supa.table('raw_signal_matches_v3').delete().in_('raw_signal_id', [1, 2]).execute())
    t("all 5 in-scope rows gone under the old delete",
      sorted(r['pin'] for r in db['_deleted']),
      ['0000000001', '0000000002', '0000000003', '0000000004', '0000000005'])


if __name__ == '__main__':
    test_filter_wire_format()
    test_or_term_semantics()
    test_reset_then_rematch_stays_retired()
    test_old_behaviour_would_unretire()
    print(f"\n{PASSES} passed, {FAILS} failed")
    sys.exit(1 if FAILS else 0)
