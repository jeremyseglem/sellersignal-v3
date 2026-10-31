"""
Tests for matching KC probate filings against the owner of record ON THE
FILING DATE (Signal lab H1, claude/SIGNAL_LAB.md; Harvester queue #9).

King County puts the buyer on title within weeks of a sale, so a decedent
whose home has sold used to be checked against the buyer's name. The rule:
when a deed was recorded after the filing, match the grantor(s) of the
first such deed instead of today's owner; if a market sale followed the
filing, write the match retired ('retired_sold_before_match'); a
non-market retitle (estate, heir, trust) keeps it live.

All names, pins and recording numbers below are invented. No network, no
database.

Run: python tests/test_owner_at_filing.py
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, '.')

from backend.harvesters import matcher as M
from backend.harvesters import owner_at_filing as O

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


def deed(date, seller, instrument="Statutory Warranty Deed", reason="None",
         price=850_000, rec=None):
    return {"pin": "0000000001", "recording_number": rec or date.replace("-", "") + "000001",
            "sale_date": date, "sale_price": price, "seller_name": seller,
            "instrument": instrument, "sale_reason": reason}


print("═══ deed_party_names ═══")
n = O.deed_party_names
t("LAST FIRST M", n("VELTMAN QUENTIN A"), ["QUENTIN A VELTMAN"])
t("couple, co-owner inherits surname", n("VELTMAN QUENTIN A+MARISOL B"),
  ["QUENTIN A VELTMAN", "MARISOL B VELTMAN"])
t("couple, one-word co-owner", n("VELTMAN QUENTIN+MARISOL"),
  ["QUENTIN VELTMAN", "MARISOL VELTMAN"])
t("two surnames", n("VELTMAN QUENTIN A+ORSK DAGNY"),
  ["QUENTIN A VELTMAN", "DAGNY ORSK"])
t("comma form", n("VELTMAN, QUENTIN A"), ["QUENTIN A VELTMAN"])
t("estate capacity words dropped", n("VELTMAN QUENTIN A ESTE"), ["QUENTIN A VELTMAN"])
t("PR capacity dropped", n("ESTATE OF VELTMAN QUENTIN A PR"), ["QUENTIN A VELTMAN"])
t("entity kept as is", n("VELTMAN FAMILY TRUST"), ["VELTMAN FAMILY TRUST"])
t("blank", n(""), [])
t("None", n(None), [])

print("═══ is_market_sale ═══")
m = O.is_market_sale
t("statutory warranty, None", m(deed("2026-05-01", "X")), True)
t("plain warranty deed counts (the PR #8 gap)", m(deed("2026-05-01", "X", "Warranty Deed")), True)
t("PR deed, estate settlement", m(deed("2026-05-01", "X", "Deed of Personal Rep", "Estate Settlement")), True)
t("quit claim", m(deed("2026-05-01", "X", "Quit Claim Deed", "Other", 0)), False)
t("priced quit claim still not market", m(deed("2026-05-01", "X", "Quit Claim Deed")), False)
t("under $10k", m(deed("2026-05-01", "X", price=9_999)), False)
t("no price", m(deed("2026-05-01", "X", price=None)), False)
t("gift reason", m(deed("2026-05-01", "X", reason="Quit Claim Deed - gift/full or part interest")), False)
t("trust reason", m(deed("2026-05-01", "X", reason="Trust")), False)

print("═══ owner_at_filing ═══")
oaf = O.owner_at_filing
t("no deeds -> None", oaf([], "2026-01-10"), None)
t("only earlier deeds -> None", oaf([deed("2020-03-01", "ORSK DAGNY")], "2026-01-10"), None)
t("same-day deed is not after", oaf([deed("2026-01-10", "ORSK DAGNY")], "2026-01-10"), None)
r = oaf([deed("2019-03-01", "ORSK DAGNY"),
         deed("2026-04-02", "VELTMAN QUENTIN A ESTE", "Deed of Personal Rep", "Estate Settlement")],
        "2026-01-10")
t("first deed after -> its grantor", r.names, ("QUENTIN A VELTMAN",))
t("market sale after -> retire", r.retire_reason is not None, True)
r = oaf([deed("2026-03-01", "VELTMAN QUENTIN A", "Quit Claim Deed", "Estate Settlement", 0)],
        "2026-01-10")
t("non-market retitle -> grantor, live", (r.names, r.retire_reason), (("QUENTIN A VELTMAN",), None))
r = oaf([deed("2026-05-20", "VELTMAN MARISOL", rec="20260520000009"),
         deed("2026-03-01", "VELTMAN QUENTIN A", "Quit Claim Deed", "Estate Settlement", 0,
              rec="20260301000003")], "2026-01-10")
t("unsorted input: first by date wins", r.names, ("QUENTIN A VELTMAN",))
t("later market sale still retires", r.retire_reason.startswith("market sale 2026-05-20"), True)
t("blank grantor -> no names (never today's owner)",
  oaf([deed("2026-03-01", "")], "2026-01-10").names, ())

print("═══ _dispatch_probate + _process_one ═══")


class _Q:
    def __init__(self, sink):
        self.sink = sink

    def upsert(self, rows, on_conflict=None, ignore_duplicates=False):
        self.sink.append((list(rows), ignore_duplicates))
        return self

    def update(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return self


class FakeSupa:
    def __init__(self):
        self.upserts = []

    def table(self, name):
        return _Q(self.upserts)


SIG = {"id": 1, "source_type": "kc_superior_court", "signal_type": "probate",
       "event_date": "2026-01-10", "document_ref": "26-4-00000-0",
       "party_names": [{"raw": "QUENTIN ARLO VELTMAN", "role": "decedent"}]}
USE = {p: {"prop_type": "R"} for p in ("0000000001", "0000000002", "0000000003", "0000000004")}


def owners():
    return {
        # sold on the market after the filing; today's owner is the buyer
        "0000000001": {"owner_name": "DAGNY ORSK", "market_key": "WA_KING", "zip_code": "98000",
                       "deeds": [deed("2026-04-02", "VELTMAN QUENTIN A ESTE",
                                      "Deed of Personal Rep", "Estate Settlement")]},
        # retitled to an heir after the filing (non-market): still a live lead
        "0000000002": {"owner_name": "MARISOL ORSK", "market_key": "WA_KING", "zip_code": "98000",
                       "deeds": [deed("2026-03-01", "VELTMAN QUENTIN ARLO", "Quit Claim Deed",
                                      "Estate Settlement", 0)]},
        # no deed since the filing: today's owner, unchanged behaviour
        "0000000003": {"owner_name": "QUENTIN A VELTMAN", "market_key": "WA_KING", "zip_code": "98000"},
        # buyer shares the decedent's name; the grantor at filing did not
        "0000000004": {"owner_name": "QUENTIN A VELTMAN", "market_key": "WA_KING", "zip_code": "98000",
                       "deeds": [deed("2026-02-15", "LUND ELSA")]},
    }


os.environ["OWNER_AT_FILING_ENABLED"] = "1"
c = {x["parcel_id"]: x["trigger_hint"] for x in M._dispatch_probate(SIG, owners(), USE)}
t("sold home matched on its grantor", sorted(c), ["0000000001", "0000000002", "0000000003"])
t("sold home carries retire status", c["0000000001"].get("retire_status"), "retired_sold_before_match")
t("sold home names the grantor it matched", c["0000000001"].get("owner_at_filing"), "QUENTIN A VELTMAN")
t("heir retitle is live", "retire_status" in c["0000000002"], False)
t("unchanged pin has no owner_at_filing", "owner_at_filing" in c["0000000003"], False)
t("buyer-name coincidence dropped", "0000000004" in c, False)

supa = FakeSupa()
n_rows = M._process_one(supa, SIG, owners(), USE, None, defer_mark=True)
t("_process_one writes 3 rows", n_rows, 3)
live = [r for rows, ig in supa.upserts if not ig for r in rows]
ret = [r for rows, ig in supa.upserts if ig for r in rows]
t("live upsert has no review status column", any("match_review_status" in r for r in live), False)
t("live pins", sorted(r["pin"] for r in live), ["0000000002", "0000000003"])
t("retired row via ON CONFLICT DO NOTHING", [r["pin"] for r in ret], ["0000000001"])
t("retired row status", ret[0]["match_review_status"], "retired_sold_before_match")
t("surname gate ran on the grantor (strict)", ret[0]["match_strength"], "strict")

sig_other = dict(SIG, source_type="obituary_rss", signal_type="obituary")
c = {x["parcel_id"] for x in M._dispatch_probate(sig_other, owners(), USE)}
t("other sources keep today's owner", sorted(c), ["0000000003", "0000000004"])

os.environ["OWNER_AT_FILING_ENABLED"] = "0"
c = {x["parcel_id"] for x in M._dispatch_probate(SIG, owners(), USE)}
t("kill switch restores today's owner", sorted(c), ["0000000003", "0000000004"])
t("kill switch: no deed load", M._deeds_for_rows(FakeSupa(), [SIG]), {})
os.environ["OWNER_AT_FILING_ENABLED"] = "1"

print("═══ _deeds_since keyset paging + cache ═══")


class _PageQ:
    def __init__(self, store):
        self.store, self.since, self.after = store, None, None

    def select(self, *a):
        return self

    def gte(self, col, v):
        self.since = v
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self.n = n
        return self

    def or_(self, expr):
        # "pin.gt.P,and(pin.eq.P,recording_number.gt.R)"
        p = expr.split(",")[0][len("pin.gt."):]
        r = expr.split("recording_number.gt.")[1].rstrip(")")
        self.after = (p, r)
        return self

    def execute(self):
        self.store["calls"] += 1
        rows = sorted((r for r in self.store["rows"] if r["sale_date"] >= self.since),
                      key=lambda r: (r["pin"], r["recording_number"]))
        if self.after:
            rows = [r for r in rows if (r["pin"], r["recording_number"]) > self.after]
        self.data = rows[:self.n]
        return self


class PageSupa:
    def __init__(self, rows):
        self.store = {"rows": rows, "calls": 0}

    def table(self, name):
        return _PageQ(self.store)


rows = [{"pin": f"{i // 3:010d}", "recording_number": f"2026{i:08d}", "sale_date": "2026-02-01"}
        for i in range(2500)]
rows += [{"pin": "0000000001", "recording_number": "201900000001", "sale_date": "2019-01-01"}]
ps = PageSupa(rows)
M._DEED_CACHE.update(loaded_at=0.0, since=None, by_pin={})
got = M._deeds_since(ps, "2025-01-01")
t("all rows since the date, none lost at page edges", sum(len(v) for v in got.values()), 2500)
t("old deed excluded", any(r["sale_date"] < "2025-01-01" for v in got.values() for r in v), False)
t("3 pages", ps.store["calls"], 3)
M._deeds_since(ps, "2025-06-01")
t("cache reused for a later since", ps.store["calls"], 3)
M._deeds_since(ps, "2024-06-01")
t("earlier since reloads", ps.store["calls"], 6)
M._DEED_CACHE.update(loaded_at=0.0, since=None, by_pin={})

db = {"0000000001": {"owner_name": "X"}}
M._attach_deeds(db, {"0000000001": [1], "0000000009": [2]})
t("_attach_deeds only touches known pins", (db["0000000001"].get("deeds"), "0000000009" in db), ([1], False))

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
