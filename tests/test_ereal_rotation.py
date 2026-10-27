"""
Tests for the eReal sweep's rotation guard (2026-10-27 repair).

The stall being fixed (prod, 2026-10-26T16:54Z -> 10-27T16:16Z): 393 ticks
on rotation cursor 2 (98006), each fetching exactly 1 parcel with
parsed_ok 1 / sales_upserted 0, while /api/admin/coverage-status?zip_code=
98006 read total 17,517 / hydrated 17,516. One parcel stayed TTL-due after
every fetch (fetched_at NULL), so run_batch always found 1 candidate and
the cursor never advanced.

No network and no database: fetch_one and the Supabase client are fakes.
Run: python tests/test_ereal_rotation.py
"""
from __future__ import annotations

import asyncio
import sys
sys.path.insert(0, '.')

from backend.harvesters import ereal_property as E
from backend.tasks import ereal_autofill as T

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


# ---- fakes -----------------------------------------------------------------
class _Res:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []
        self.op, self.payload, self.rng = 'select', None, None

    def select(self, *_a, **_k): return self
    def eq(self, col, val): self.filters.append(('eq', col, val)); return self
    def in_(self, col, vals): self.filters.append(('in', col, set(vals))); return self
    def range(self, a, b): self.rng = (a, b); return self
    def update(self, payload): self.op, self.payload = 'update', payload; return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload = 'upsert', payload
        return self

    def _match(self, row):
        for kind, col, val in self.filters:
            if kind == 'eq' and row.get(col) != val:
                return False
            if kind == 'in' and row.get(col) not in val:
                return False
        return True

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.op == 'select':
            out = [r for r in rows if self._match(r)]
            if self.rng:
                out = out[self.rng[0]:self.rng[1] + 1]
            return _Res(out)
        if self.op == 'update':
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
            return _Res([])
        # upsert
        items = self.payload if isinstance(self.payload, list) else [self.payload]
        for it in items:
            if self.table == 'parcel_ereal_meta_v3' and it['pin'] in self.db['_meta_fail']:
                raise RuntimeError("{'code': 'XX000', 'details': 'Failing row contains (SECRET NAME)', "
                                   "'hint': None, 'message': 'simulated meta write failure'}")
            key = 'pin'
            for r in rows:
                if r.get(key) == it.get(key) and self.table == 'parcel_ereal_meta_v3':
                    r.update({k: v for k, v in it.items()})
                    break
            else:
                rows.append(dict(it))
        return _Res([])


class FakeSupa:
    def __init__(self, zips: dict[str, list[str]], meta_fail: set[str]):
        self.db = {
            'parcels_v3': [{'pin': p, 'zip_code': z, 'owner_type': 'individual'}
                           for z, pins in zips.items() for p in pins],
            'parcel_ereal_meta_v3': [],
            'sales_history_v3': [],
            '_meta_fail': meta_fail,
        }

    def table(self, name): return _Q(self.db, name)


FETCHES: list[str] = []


def fake_fetch_one(pin, session=None):
    FETCHES.append(pin)
    return {'pin': pin, 'ok': True, 'status': 200, 'body_length': 1000,
            'error': None,
            'parsed': {'pin': pin, 'parcel': {}, 'building': {}, 'sales': [],
                       'parser_version': E.PARSER_VERSION}}


E.fetch_one = fake_fetch_one
E._build_session = lambda: None
E.INTER_REQUEST_SLEEP_S = 0

# ---- 1. run_batch / _fetch_pins unit behaviour -----------------------------
print("run_batch + _fetch_pins")
supa = FakeSupa({'98006': ['A1', 'A2', 'BAD']}, meta_fail={'BAD'})
b1 = E.run_batch(supa, '98006', limit=60, ttl_days=30, sleep_between_s=0)
t("first batch fetches all 3 never-fetched pins", sorted(FETCHES), ['A1', 'A2', 'BAD'])
t("meta write failure is reported as a write error", b1['write_errors'], 1)
t("the failing pin is in failed_pins", b1['failed_pins'], ['BAD'])
t("sample error carries the pin", b1['sample_errors'][0]['pin'], 'BAD')
FETCHES.clear()
b2 = E.run_batch(supa, '98006', limit=60, ttl_days=30, sleep_between_s=0)
t("without exclusion the failing pin is re-fetched (the prod stall)", FETCHES, ['BAD'])
FETCHES.clear()
b3 = E.run_batch(supa, '98006', limit=60, ttl_days=30, sleep_between_s=0,
                 exclude_pins={'BAD'})
t("with exclusion nothing is fetched", FETCHES, [])
t("with exclusion candidates_found is 0", b3['candidates_found'], 0)
t("excluded-but-still-due pin is counted", b3['repeat_due'], 1)
t("repeat_due_sample names the pin", b3['repeat_due_sample'], ['BAD'])

# ---- 2. sanitised status errors --------------------------------------------
print("status error sanitising")
se = T._safe_errors(b1['sample_errors'])
t("code + message kept", se[0]['error'], 'XX000: simulated meta write failure')
t("failing-row details dropped", 'SECRET' in str(se), False)

# ---- 3. the real loop: cursor advances past a persistently failing pin -----
print("ereal_autofill_loop rotation")
FETCHES.clear()
supa2 = FakeSupa({'98006': ['B1', 'B2', 'STUCK'], '98007': ['C1', 'C2']},
                 meta_fail={'STUCK'})
import backend.api.db as dbmod
dbmod.get_supabase_client = lambda: supa2
T._kc_zips = lambda s: ['98006', '98007']
T.detect_transfers = lambda s, pins, **k: {'pins': len(pins), 'sales_seen': 0,
                                            'signals': 0, 'retired_pins': 0,
                                            'by_type': {}, 'errors': 0}
T.STARTUP_DELAY = 0
T.TICK_INTERVAL = 1
T.IDLE_INTERVAL = 1
_real_sleep = asyncio.sleep
ticks_seen: list[tuple] = []


async def fake_sleep(sec):
    # called once per tick-wait; record cursor and stop after 8 ticks
    ticks_seen.append((T.state['zip_cursor'], T.state['total_ticks']))
    if T.state['total_ticks'] >= 8:
        raise asyncio.CancelledError()
    await _real_sleep(0)

T.asyncio.sleep = fake_sleep
try:
    asyncio.run(T.ereal_autofill_loop())
except (asyncio.CancelledError, BaseException) as e:
    if not isinstance(e, asyncio.CancelledError):
        raise
T.asyncio.sleep = _real_sleep

print("   fetch order:", FETCHES, "ticks (cursor,total):", ticks_seen)
passes = 1 + sum(1 for (c0, _), (c1, _) in zip(ticks_seen, ticks_seen[1:]) if c1 < c0)
t("STUCK fetched once per rotation pass (not once per tick)", FETCHES.count("STUCK"), passes)
t("after STUCK the sweep moves on to 98007 in the same pass",
  FETCHES[FETCHES.index("STUCK") + 1], "C1")
t("98007 parcels were reached", sorted(p for p in FETCHES if p.startswith('C')), ['C1', 'C2'])
t("no tick errors", T.state['total_errors'], 0)
t("write errors counted in state", T.state['total_write_errors'] >= 1, True)
t("repeat-due skip counted when 98006 closed", T.state['total_repeat_due_skipped'] >= 1, True)
t("status state holds no pin sets", any(isinstance(v, set) for v in T.state.values()), False)

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
