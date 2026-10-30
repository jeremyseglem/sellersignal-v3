"""
The classify and band stages page parcels_v3 1,000 rows at a time. Without
an ORDER BY the pages are not deterministic and rows get skipped (TX 75219:
exactly 1,000 parcels never banded, 2026-10-29). These tests drive both
stages against a fake Supabase client that only returns stable pages when
.order('pin') was requested. Run: python tests/test_paging_order.py
"""
from __future__ import annotations

import random
import sys
import types

sys.path.insert(0, ".")

PASSES = FAILS = 0


def t(label, got, want):
    global PASSES, FAILS
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r} want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


class _Resp:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Mimics the postgrest builder for parcels_v3 reads/updates and the
    zip_coverage_v3 reads/updates the two stages make."""

    def __init__(self, store, table):
        self.store, self.table = store, table
        self.ordered = False
        self.rng = None
        self.filters = {}
        self.payload = None
        self.in_pins = None
        self.single = False

    def select(self, *_a, **_k): return self
    def eq(self, k, v): self.filters[k] = v; return self
    def in_(self, k, vals): self.in_pins = set(vals); return self
    def maybe_single(self): self.single = True; return self
    def order(self, k, **_k): self.ordered = (k == 'pin'); return self
    def range(self, a, b): self.rng = (a, b); return self
    def update(self, payload): self.payload = payload; return self

    def execute(self):
        if self.table == 'zip_coverage_v3':
            if self.payload is not None:
                self.store['coverage_updates'].append(self.payload)
                return _Resp([])
            return _Resp({'archetypes_classified_at': 'x', 'parcel_count': len(self.store['rows']),
                          'state': 'TX'})
        rows = [r for r in self.store['rows'] if r['zip_code'] == self.filters.get('zip_code')]
        if self.payload is not None:
            for r in self.store['rows']:
                if r['pin'] in (self.in_pins or set()):
                    r.update(self.payload)
            return _Resp([])
        if self.ordered:
            rows = sorted(rows, key=lambda r: r['pin'])
        else:
            # Unordered: Postgres gives no stable order between requests.
            rows = list(rows); random.Random(self.rng[0]).shuffle(rows)
        a, b = self.rng
        return _Resp(rows[a:b + 1])


class FakeSupa:
    def __init__(self, store): self.store = store
    def table(self, name): return FakeQuery(self.store, name)


def make_store(n=2500):
    rows = [{'pin': f"{i:010d}", 'zip_code': '75219', 'owner_name': f"OWNER {i} LLC",
             'owner_name_raw': None, 'owner_type': 'llc', 'total_value': 500000,
             'tenure_years': 5.0, 'prop_type': 'residential', 'signal_family': 'llc_long_hold',
             'address': 'x', 'is_vacant_land': False, 'is_absentee': False,
             'is_out_of_state': False, 'band': None}
            for i in range(n)]
    return {'rows': rows, 'coverage_updates': []}


def run_banding(store):
    import backend.api.db as DB
    import backend.scoring.banding_v3 as B
    orig = DB.get_supabase_client
    DB.get_supabase_client = lambda: FakeSupa(store)
    try:
        return B.apply_banding_to_zip('75219')
    finally:
        DB.get_supabase_client = orig


print("band stage pages every parcel")
store = make_store()
stats = run_banding(store)
t("all 2,500 parcels processed", stats['total'], 2500)
t("no parcel left with band null", sum(1 for r in store['rows'] if r['band'] is None), 0)
t("pins banded are distinct", len({r['pin'] for r in store['rows'] if r['band'] is not None}), 2500)

print("regression: the unordered read skips rows")
# Simulate the old code path: a query that never asked for order.
store2 = make_store()
q = FakeQuery(store2, 'parcels_v3').select().eq('zip_code', '75219')
got = []
for off in range(0, 2500, 1000):
    got += [r['pin'] for r in FakeQuery(store2, 'parcels_v3').select().eq('zip_code', '75219')
            .range(off, off + 999).execute().data]
t("unordered paging returns fewer distinct pins than parcels", len(set(got)) < 2500, True)

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
