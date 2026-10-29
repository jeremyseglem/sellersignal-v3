"""
Tests for Harvester queue #10 (2026-10-29): KC public sales file ->
sales_history_v3 (backend/harvesters/kc_sales_file.py + POST
/api/harvest/ingest-sales-history).

Fixture rows use the real file's layout, codes, pins, recording and
excise numbers (EXTR_RPSale.csv / EXTR_LookUp.csv dated 2026-10-23),
with party names replaced by placeholders (no owner names in the repo).
The expected values for pins 3211900015 and 8964800590 are what
production's eReal rows hold for the same recordings
(/api/admin/ereal-sales/{pin}, read 2026-10-29).

No network, no database. Run: python tests/test_kc_sales_history.py
"""
from __future__ import annotations

import csv
import io
import os
import sys
sys.path.insert(0, '.')

from backend.harvesters import kc_sales_file as K
from backend.tasks.ereal_autofill import _classify_transfer

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


LOOKUP = '''"LUType","LUItem","LUDescription"
"1  ","1  ","LAND ONLY                                         "
"5  ","1  ","None                                              "
"5  ","8  ","Estate Settlement                                 "
"5  ","11 ","Divorce Settlement                                "
"5  ","18 ","Other                                             "
"6  ","3  ","Statutory Warranty Deed                           "
"6  ","15 ","Quit Claim Deed                                   "
"6  ","18 ","Trustees' Deed                                    "
'''

HDR = ('"ExciseTaxNbr","Major","Minor","DocumentDate","SalePrice","RecordingNbr",'
       '"Volume","Page","PlatNbr","PlatType","PlatLot","PlatBlock","SellerName",'
       '"BuyerName","PropertyType","PrincipalUse","SaleInstrument","AFForestLand",'
       '"AFCurrentUseLand","AFNonProfitUse","AFHistoricProperty","SaleReason",'
       '"PropertyClass","SaleWarning"\n')


def line(excise, major, minor, dd, price, rec, seller, buyer, instr, reason):
    return (f'"{excise}","{major}","{minor}","{dd}","{price}","{rec}","   ","   ",'
            f'"      "," ","              ","       ","{seller:<50}","{buyer:<50}",'
            f'"11","6","{instr}","N","N","N","N","{reason}","8"," "\n')


SALES = HDR + "".join([
    # pin 3211900015 — eReal holds: 20260427000596 / 3375477 / 2026-04-16 /
    # price None / Quit Claim Deed / Other / is_arms_length False
    line("3375477", "321190", "0015", "04/16/2026", "0", "20260427000596",
         "SELLER A", "BUYER A", "15", "18"),
    # eReal holds: 20111229002253 / 615000 / Statutory Warranty Deed / None / True
    line("2524689", "321190", "0015", "12/22/2011", "615000", "20111229002253",
         "SELLER B", "BUYER B", "3", "1"),
    # pin 8964800590 — eReal: 20000314001055 / 455000 / SWD / Estate Settlement / False
    line("1740963", "896480", "0590", "03/09/2000", "455000", "20000314001055",
         "ESTATE OF X", "BUYER C", "3", "8"),
    # pin 7229350630 — the queue #5 parcel: one recording number twice
    line("1233793", "722935", "0630", "02/14/1992", "0", "199203100000  ",
         "SELLER D", "BUYER D", "0", "18"),
    line("1233795", "722935", "0630", "02/07/1992", "300000", "199203100000  ",
         "SELLER E", "BUYER E", "0", "1"),
    line("3316299", "722935", "0630", "02/05/2025", "0", "20250206000059",
         "SELLER F", "BUYER F", "15", "18"),
    # blank recording number (the file has these) -> skipped
    line("2934731", "722935", "0590", "06/04/2018", "235000", "              ",
         "SELLER G", "BUYER G", "3", "1"),
    # divorce settlement + an unknown instrument code
    line("9999901", "100000", "0010", "03/01/2026", "0", "20260305000111",
         "SPOUSE A+SPOUSE B", "SPOUSE A", "99", "11"),
])


def _rows(**kw):
    lk = K.load_lookups(LOOKUP)
    unknown = {}
    out = list(K.iter_sales(io.StringIO(SALES), lk, unknown=unknown, **kw))
    return out, unknown


def test_lookups():
    print("lookups")
    lk = K.load_lookups(LOOKUP)
    t("instrument 3", lk["instrument"].get("3"), "Statutory Warranty Deed")
    t("instrument 18", lk["instrument"].get("18"), "Trustees' Deed")
    t("reason 8", lk["reason"].get("8"), "Estate Settlement")
    t("other LUTypes ignored", "LAND ONLY" in lk["instrument"].values()
      or "LAND ONLY" in lk["reason"].values(), False)


def test_parse_matches_ereal():
    print("parse == production eReal rows")
    rows, unknown = _rows()
    by = {(r["pin"], r["recording_number"]): r for r in rows}
    a = by[("3211900015", "20260427000596")]
    t("qcd excise", a["excise_number"], "3375477")
    t("qcd date", a["sale_date"], "2026-04-16")
    t("qcd price 0 -> None", a["sale_price"], None)
    t("qcd instrument", a["instrument"], "Quit Claim Deed")
    t("qcd reason", a["sale_reason"], "Other")
    t("qcd arms", a["is_arms_length"], False)
    t("names stripped", a["seller_name"], "SELLER A")
    b = by[("3211900015", "20111229002253")]
    t("swd price", b["sale_price"], 615000)
    t("swd arms True", b["is_arms_length"], True)
    c = by[("8964800590", "20000314001055")]
    t("estate reason", c["sale_reason"], "Estate Settlement")
    t("estate arms False", c["is_arms_length"], False)
    t("estate -> estate_transfer", _classify_transfer(c), "estate_transfer")
    d = by[("1000000010", "20260305000111")]
    t("unknown instrument stored None", d["instrument"], None)
    t("divorce -> divorce_transfer", _classify_transfer(d), "divorce_transfer")
    t("unknown counted", unknown, {"instrument:99": 1, "instrument:0": 2})
    t("blank recording skipped",
      any(r["pin"] == "7229350590" for r in rows), False)
    t("recording stripped", ("7229350630", "199203100000") in by, True)


def test_dedupe():
    print("dedupe (queue #5 parcel 7229350630)")
    rows, _ = _rows()
    t("raw rows incl. duplicate key", len(rows), 7)
    dd, dropped = K.dedupe_rows(rows)
    t("dropped", dropped, 1)
    keep = [r for r in dd if r["recording_number"] == "199203100000"]
    t("one row kept", len(keep), 1)
    t("kept the priced row", keep[0]["excise_number"], "1233795")
    keys = [(r["pin"], r["recording_number"]) for r in dd]
    t("keys unique", len(keys), len(set(keys)))


def test_filters():
    print("filters")
    from datetime import date
    rows, _ = _rows(pins={"3211900015"})
    t("pin filter", sorted(r["recording_number"] for r in rows),
      ["20111229002253", "20260427000596"])
    rows, _ = _rows(since=date(2015, 1, 1))
    t("since filter", sorted(r["recording_number"] for r in rows),
      ["20250206000059", "20260305000111", "20260427000596"])
    t("pin_of pads", K.pin_of("20", "1"), "0000200001")
    t("pin_of junk", K.pin_of("", "0001"), "")


# ---- endpoint, fake Supabase ------------------------------------------------
class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.kw, self.flt = db, table, 'select', {}, None
        db.touched.add(table)

    def select(self, *_a, **_k): return self
    def in_(self, col, vals):
        self.flt = (col, set(vals)); return self
    def upsert(self, rows, **kw):
        self.op, self.rows, self.kw = 'upsert', rows, kw; return self

    def execute(self):
        data = self.db.tables.setdefault(self.table, [])
        if self.op == 'select':
            col, vals = self.flt
            return _Res([dict(r) for r in data if r.get(col) in vals])
        self.db.upserts.append((self.table, list(self.rows), dict(self.kw)))
        keys = {(r['pin'], r['recording_number']) for r in data}
        for r in self.rows:
            k = (r['pin'], r['recording_number'])
            if k in keys and self.kw.get('ignore_duplicates'):
                continue                       # ON CONFLICT DO NOTHING
            assert k not in keys, "fake: merge path not expected"
            data.append(dict(r)); keys.add(k)
        return _Res(self.rows)


class _DB:
    def __init__(self, tables):
        self.tables, self.upserts, self.touched = tables, [], set()
    def table(self, name): return _Q(self, name)


def _db():
    ereal_row = {'pin': '3211900015', 'recording_number': '20260427000596',
                 'excise_number': '3375477', 'sale_date': '2026-04-16',
                 'sale_price': None, 'seller_name': 'EREAL SELLER',
                 'buyer_name': 'EREAL BUYER', 'instrument': 'Quit Claim Deed',
                 'sale_reason': 'Other', 'is_arms_length': False,
                 'source_fetched_at': '2026-10-28T00:00:00+00:00'}
    return _DB({
        'parcels_v3': [{'pin': '3211900015', 'zip_code': '98008'},
                       {'pin': '7229350630', 'zip_code': '98006'},
                       {'pin': '8964800590', 'zip_code': '98004'}],
        'sales_history_v3': [ereal_row],
        'parcel_ereal_meta_v3': [{'pin': '3211900015', 'fetched_at': 'x'}],
    })


def _call(db, body):
    from fastapi import HTTPException
    from backend.api import harvest as H
    H.get_supabase_client = lambda: db
    os.environ['ADMIN_KEY'] = 'k'
    try:
        return H.ingest_sales_history(payload=body, x_admin_key='k')
    except HTTPException as e:
        return {'status': e.status_code}


def test_endpoint():
    print("endpoint /ingest-sales-history")
    rows, _ = _rows()            # 7 rows incl. the duplicate key
    db = _db()
    r = _call(db, {'market_key': 'WA_KING', 'rows': rows})
    t("dry run is the default", r['dry_run'], True)
    t("dry run wrote nothing", db.upserts, [])
    t("dup_in_batch", r['dup_in_batch'], 1)
    t("not_in_fabric (pin 1000000010)", r['not_in_fabric'], 1)
    t("already_present (eReal row)", r['already_present'], 1)
    t("new_rows", r['new_rows'], 4)
    t("new_by_zip", r['new_by_zip'], {'98008': 1, '98006': 2, '98004': 1})

    db = _db()
    r = _call(db, {'market_key': 'WA_KING', 'dry_run': False, 'rows': rows})
    t("write inserted", r['inserted'], 4)
    t("one upsert call", len(db.upserts), 1)
    tbl, sent, kw = db.upserts[0]
    t("into sales_history_v3", tbl, 'sales_history_v3')
    t("ignore_duplicates (ON CONFLICT DO NOTHING)", kw.get('ignore_duplicates'), True)
    t("on_conflict", kw.get('on_conflict'), 'pin,recording_number')
    t("existing key never sent",
      any(s['recording_number'] == '20260427000596' for s in sent), False)
    keys = [(s['pin'], s['recording_number']) for s in sent]
    t("sent keys unique", len(keys), len(set(keys)))
    ereal = [x for x in db.tables['sales_history_v3']
             if x['recording_number'] == '20260427000596'][0]
    t("eReal row untouched", (ereal['seller_name'], ereal['source_fetched_at']),
      ('EREAL SELLER', '2026-10-28T00:00:00+00:00'))
    t("eReal meta never touched", 'parcel_ereal_meta_v3' in db.touched, False)
    t("no signals/matches written",
      bool({'raw_signals_v3', 'raw_signal_matches_v3'} & db.touched), False)
    t("arms-length computed server-side",
      [s['is_arms_length'] for s in sent if s['recording_number'] == '20000314001055'],
      [False])

    # client-supplied is_arms_length is ignored
    bad = [dict(rows[1], is_arms_length=None, pin='8964800590',
                recording_number='X1')]
    db = _db()
    _call(db, {'market_key': 'WA_KING', 'dry_run': False, 'rows': bad})
    t("is_arms_length recomputed", db.upserts[0][1][0]['is_arms_length'], True)

    t("market guard", _call(_db(), {'market_key': 'CO_DENVER', 'rows': rows}),
      {'status': 400})
    t("batch cap", _call(_db(), {'market_key': 'WA_KING', 'rows': rows * 300}),
      {'status': 400})


def test_wire():
    print("wire request (postgrest-py 0.17.2)")
    from postgrest import SyncPostgrestClient
    q = (SyncPostgrestClient('http://x').from_('sales_history_v3')
         .upsert([{'pin': '1', 'recording_number': '2'}],
                 on_conflict='pin,recording_number', ignore_duplicates=True))
    t("Prefer resolution=ignore-duplicates",
      'resolution=ignore-duplicates' in q.headers.get('prefer', ''), True)


if __name__ == '__main__':
    test_lookups()
    test_parse_matches_ereal()
    test_dedupe()
    test_filters()
    test_endpoint()
    test_wire()
    print(f"\n{PASSES} passed, {FAILS} failed")
    sys.exit(1 if FAILS else 0)
