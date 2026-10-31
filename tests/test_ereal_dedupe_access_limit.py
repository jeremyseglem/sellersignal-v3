"""
Tests for the eReal sweep repairs of 2026-10-30 (Harvester queue #5, #6 and
the portal access-limit finding).

What was observed live (counts, codes and pins only):
  * pin 7229350630 (98006): the detail page lists 7 sales, recording
    number 199203100000 on two of them (excise 1233793 and 1233795 —
    distinct 1992 sales). One upsert carrying both rows fails with
    Postgres 21000 and the parcel's meta fetched_at stays NULL (the
    2026-10-27 stall pin; 4 write errors per process since).
  * From Railway, blue.kingcounty.com answers Detail.aspx with HTTP 200
    and a 47,736-byte page titled "eReal Property - Exceed Access Limit"
    (form id cphContent_FormViewLimit, "we limit each client's access to
    1000 parcels per day"). It has no owner, building or SALES HISTORY
    section, parses as an empty detail page, and was being stamped
    fetched_at with sales_count 0 for 30 days (98027: 200/200 recent
    meta rows). The same pin parses 1+ sales from another client.

No network and no database: fetch_one's HTTP session and the Supabase
client are fakes. Run: python tests/test_ereal_dedupe_access_limit.py
"""
from __future__ import annotations

import asyncio
import sys
sys.path.insert(0, '.')

from datetime import date

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
    """Enough of postgrest-py's builder for run_batch/upsert_parsed. The
    sales_history_v3 upsert enforces the real table's unique key the way
    Postgres does: two rows with the same (pin, recording_number) in ONE
    statement raise 21000."""

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
        items = self.payload if isinstance(self.payload, list) else [self.payload]
        if self.table == 'sales_history_v3':
            keys = [(it['pin'], it['recording_number']) for it in items]
            if len(keys) != len(set(keys)):
                raise RuntimeError("{'code': '21000', 'details': None, 'hint': None, "
                                   "'message': 'ON CONFLICT DO UPDATE command cannot affect "
                                   "row a second time'}")
            key = lambda r: (r.get('pin'), r.get('recording_number'))  # noqa: E731
        else:
            key = lambda r: r.get('pin')  # noqa: E731
        for it in items:
            for r in rows:
                if key(r) == key(it):
                    r.update(dict(it))
                    break
            else:
                rows.append(dict(it))
        return _Res([])


class FakeSupa:
    def __init__(self, zips: dict[str, list[str]]):
        self.db = {
            'parcels_v3': [{'pin': p, 'zip_code': z, 'owner_type': 'individual'}
                           for z, pins in zips.items() for p in pins],
            'parcel_ereal_meta_v3': [],
            'sales_history_v3': [],
        }

    def table(self, name): return _Q(self.db, name)

    def meta(self, pin):
        return next((r for r in self.db['parcel_ereal_meta_v3'] if r['pin'] == pin), None)


# The live 7229350630 sales list, names replaced, otherwise as parsed on
# 2026-10-30 (7 rows, recording 199203100000 twice).
def _sale(rec, excise, d, price, instr, reason):
    return {'excise_number': excise, 'recording_number': rec, 'sale_date': d,
            'sale_price': price, 'seller_name': 'S', 'buyer_name': 'B',
            'instrument': instr, 'sale_reason': reason, 'is_arms_length': None}


DUP_SALES = [
    _sale('20220301000001', '3100001', date(2022, 3, 1), 1_500_000, 'Statutory Warranty Deed', 'None'),
    _sale('20150601000002', '2700002', date(2015, 6, 1), 900_000, 'Statutory Warranty Deed', 'None'),
    _sale('20050801000003', '2100003', date(2005, 8, 1), 500_000, 'Statutory Warranty Deed', 'None'),
    _sale('199803100004', '1600004', date(1998, 3, 10), 350_000, 'Warranty Deed', 'None'),
    _sale('199203100000', '1233793', date(1992, 2, 14), None, 'Quit Claim Deed', 'Other'),
    _sale('199203100000', '1233795', date(1992, 2, 7), 300_000, 'Warranty Deed', 'None'),
    _sale('198501010005', '0900005', date(1985, 1, 1), 120_000, 'Warranty Deed', 'None'),
]

# ---- 1. _dedupe_sales_rows --------------------------------------------------
print("_dedupe_sales_rows")
rows_in = [{'pin': '7229350630', 'recording_number': s['recording_number'],
            'excise_number': s['excise_number'], 'sale_date': s['sale_date'].isoformat(),
            'sale_price': s['sale_price'], 'instrument': s['instrument'],
            'sale_reason': s['sale_reason'], 'seller_name': 'S', 'buyer_name': 'B',
            'is_arms_length': None, 'source_fetched_at': 'x'} for s in DUP_SALES]
out, dropped = E._dedupe_sales_rows(rows_in)
t("7 page rows -> 6 upsert rows", len(out), 6)
t("1 row dropped", dropped, 1)
t("keys unique", len({r['recording_number'] for r in out}), 6)
kept = next(r for r in out if r['recording_number'] == '199203100000')
t("the more complete (priced) row is kept for the shared key", kept['excise_number'], '1233795')
t("page order preserved", [r['excise_number'] for r in out],
  ['3100001', '2700002', '2100003', '1600004', '1233795', '0900005'])
t("no duplicates -> unchanged", E._dedupe_sales_rows(rows_in[:4]), (rows_in[:4], 0))

# ---- 2. upsert_parsed with the duplicate on a key-enforcing fake DB ---------
print("upsert_parsed")
supa = FakeSupa({'98006': ['7229350630']})
parsed = {'pin': '7229350630', 'parcel': {}, 'building': {'sqft': 2000, 'year_built': 1985},
          'sales': DUP_SALES, 'parser_version': E.PARSER_VERSION}
st = E.upsert_parsed(supa, '7229350630', parsed)
t("no write error", st['error'], None)
t("6 sales rows written", st['sales_upserted'], 6)
t("dropped duplicate counted", st['sales_dup_rec'], 1)
t("6 rows in sales_history_v3", len(supa.db['sales_history_v3']), 6)
t("meta fetched_at stamped", bool(supa.meta('7229350630')['fetched_at']), True)
t("meta sales_count is the page count (7)", supa.meta('7229350630')['sales_count'], 7)

# the pre-patch behaviour, for the record: the same payload un-deduped fails
try:
    supa.table('sales_history_v3').upsert(rows_in, on_conflict='pin,recording_number').execute()
    raised = False
except RuntimeError as e:
    raised = "'21000'" in str(e)
t("un-deduped payload raises 21000 on the fake (the prod failure)", raised, True)

# ---- 3. access-limit page detection ----------------------------------------
print("access-limit page")
# Markers copied from the page Railway received 2026-10-30 (title + form id).
LIMIT_PAGE = ("<html><head><title>\r\n\tKing County Department of Assessments: eReal Property"
              " - Exceed Access Limit\r\n</title></head><body>"
              '<table cellspacing="0" id="cphContent_FormViewLimit" style="border-collapse:collapse;">'
              "<tr><td>Due to the large number of clients accessing our server, we limit each"
              ' client’s access to&nbsp;<span id="cphContent_FormViewLimit_LabelLimitNbr">1000'
              "</span>&nbsp; parcels per day.</td></tr></table></body></html>")
DETAIL_PAGE = ("<html><head><title>King County Department of Assessments: eReal Property</title>"
               "</head><body><span>SALES HISTORY</span><table></table>"
               "<span>REVIEW HISTORY</span></body></html>")
t("limit page detected", E.is_access_limit_page(LIMIT_PAGE), True)
t("detail page not flagged", E.is_access_limit_page(DETAIL_PAGE), False)
t("empty body not flagged", E.is_access_limit_page(""), False)


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class FakeSession:
    def __init__(self, pages: dict[str, str]):
        self.pages, self.requested = pages, []

    def get(self, url, timeout=None):
        pin = url.rsplit('=', 1)[1]
        self.requested.append(pin)
        return _Resp(self.pages[pin])


sess = FakeSession({'A': DETAIL_PAGE, 'L': LIMIT_PAGE})
ra = E.fetch_one('A', session=sess)
rl = E.fetch_one('L', session=sess)
t("detail page: ok", ra['ok'], True)
t("limit page: not ok", rl['ok'], False)
t("limit page: rate_limited flag", rl.get('rate_limited'), True)
t("limit page: HTTP status kept (200)", rl['status'], 200)
t("limit page: error names the cause", rl['error'], E.ACCESS_LIMIT_ERROR)
t("limit page: nothing parsed", rl['parsed'], None)

# ---- 4. _fetch_pins stops at the cap page and stamps nothing for it --------
print("_fetch_pins on the cap page")
sess2 = FakeSession({'P1': DETAIL_PAGE, 'P2': LIMIT_PAGE, 'P3': DETAIL_PAGE})
E._build_session = lambda: sess2
supa2 = FakeSupa({'98027': ['P1', 'P2', 'P3']})
agg = E._fetch_pins(supa2, ['P1', 'P2', 'P3'], sleep_between_s=0)
t("requests stop at the cap page", sess2.requested, ['P1', 'P2'])
t("fetched counts the two requests", agg['fetched'], 2)
t("rate_limited reported", agg['rate_limited'], True)
t("one candidate left un-requested", agg['not_attempted'], 1)
t("cap pin in failed_pins", agg['failed_pins'], ['P2'])
t("cap pin counted as an http error", agg['http_errors'], 1)
t("P1 stamped fetched", bool(supa2.meta('P1')['fetched_at']), True)
t("P2 meta has no fetched_at", supa2.meta('P2').get('fetched_at'), None)
t("P2 meta last_error names the cap", supa2.meta('P2')['last_error'], E.ACCESS_LIMIT_ERROR)
t("P3 has no meta row (never requested, stays due)", supa2.meta('P3'), None)
t("cap page is not in fetched_pins (detector input)", agg['fetched_pins'], ['P1'])

# ---- 5. the loop: budget, cap backoff, fresh-ZIP pacing --------------------
print("ereal_autofill_loop pacing + budget")
import backend.api.db as dbmod

PAGES = {f"Z1-{i}": DETAIL_PAGE for i in range(4)}
PAGES.update({f"Z2-{i}": DETAIL_PAGE for i in range(2)})
sess3 = FakeSession(PAGES)
E._build_session = lambda: sess3
E.INTER_REQUEST_SLEEP_S = 0
supa3 = FakeSupa({'98004': sorted(p for p in PAGES if p.startswith('Z1')),
                  '98005': sorted(p for p in PAGES if p.startswith('Z2'))})
dbmod.get_supabase_client = lambda: supa3
T._kc_zips = lambda s: ['98004', '98005']
T.detect_transfers = lambda s, pins, **k: {'pins': len(pins), 'sales_seen': 0, 'signals': 0,
                                            'retired_pins': 0, 'by_type': {}, 'errors': 0}
T.STARTUP_DELAY = 0
T.TICK_INTERVAL = 180
T.IDLE_INTERVAL = 3600
T.FRESH_ZIP_ADVANCE_SECONDS = 15
T.BATCH_PARCELS = 3
T.DAILY_BUDGET = 5          # 6 parcels exist: the 6th must wait for the window
T._request_times.clear()

_real_sleep = asyncio.sleep
sleeps: list[tuple[int, float]] = []   # (total_ticks at the time, seconds asked)


async def fake_sleep(sec):
    sleeps.append((T.state['total_ticks'], sec))
    if len(sleeps) > 400:
        raise asyncio.CancelledError()
    await _real_sleep(0)

T.asyncio.sleep = fake_sleep
try:
    asyncio.run(T.ereal_autofill_loop())
except asyncio.CancelledError:
    pass
T.asyncio.sleep = _real_sleep

by_tick: dict[int, float] = {}
for tick, sec in sleeps:
    by_tick[tick] = by_tick.get(tick, 0) + sec
print("   requested:", sess3.requested)
print("   sleep seconds by tick:", {k: round(v) for k, v in by_tick.items()})
t("budget: exactly 5 parcels requested, the 6th waits", len(sess3.requested), 5)
t("tick 1 fetched 3 (batch) -> tick wait 180 s", round(by_tick.get(1, 0)), 180)
t("tick 2 fetched the last 1 of 98004 -> 180 s", round(by_tick.get(2, 0)), 180)
t("tick 3: 98004 fresh, cursor advanced -> 15 s, not an hour", round(by_tick.get(3, 0)), 15)
t("tick 4: 98005 got the 1 remaining budget parcel", sess3.requested[-1].startswith('Z2'), True)
t("no tick errors", T.state['total_errors'], 0)
t("budget_used_24h reported", T.state['budget_used_24h'], 5)
t("budget wait is a wait, not a request", sess3.requested.count('Z2-1'), 0)

# cap-page tick -> IDLE_INTERVAL; full fresh pass -> IDLE_INTERVAL
print("ereal_autofill_loop after the cap page")
sess4 = FakeSession({'Q1': LIMIT_PAGE, 'Q2': DETAIL_PAGE})
E._build_session = lambda: sess4
supa4 = FakeSupa({'98006': ['Q1', 'Q2']})
dbmod.get_supabase_client = lambda: supa4
T._kc_zips = lambda s: ['98006']
T.DAILY_BUDGET = 950
T._request_times.clear()
T._attempted_this_pass.clear()
T.state.update({'zip_rotation': [], 'zip_cursor': 0, 'total_ticks': 0, 'total_errors': 0,
                'pass_fetched': 0, 'total_rate_limited': 0})
sleeps.clear()
T.asyncio.sleep = fake_sleep
try:
    asyncio.run(T.ereal_autofill_loop())
except asyncio.CancelledError:
    pass
T.asyncio.sleep = _real_sleep
by_tick = {}
for tick, sec in sleeps:
    by_tick[tick] = by_tick.get(tick, 0) + sec
print("   requested:", sess4.requested, "sleep by tick:", {k: round(v) for k, v in by_tick.items()})
t("first request drew the cap page and the batch stopped", sess4.requested[0], 'Q1')
t("cap tick rests IDLE_INTERVAL (3600 s)", round(by_tick.get(1, 0)), 3600)
t("rate-limited tick counted", T.state['total_rate_limited'] >= 1, True)
t("last_tick_result carries rate_limited", T.state['last_tick_result']['rate_limited'], True)
t("the cap pin is retried on the next tick, not skipped for the pass",
  sess4.requested[:2], ['Q1', 'Q1'])
t("status state holds no pin sets", any(isinstance(v, set) for v in T.state.values()), False)

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
