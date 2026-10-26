"""
Tests for the CT probate-courts harvester: district scope + silent-zero guard.
No network — _fetch_slice is stubbed. The stub row carries the exact keys the
live service returned on 2026-10-26 (caseId, caseNumber, code, courtName,
dateFiled, distNum, nameFirst, nameLast, nameMiddle); names are placeholders.

Run: python tests/test_ct_probate_districts.py
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
sys.path.insert(0, '.')

from backend.harvesters import ct_probate_courts as m

FAILS = 0
PASSES = 0


def t(label: str, got, want):
    global FAILS, PASSES
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r}\n         want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


m.POLITE_DELAY = 0  # no sleeping in tests

# ---- 1. district scope ------------------------------------------------------
print("district scope")
for pd in ("PD54", "PD52", "PD50", "PD51"):
    t(f"original district {pd} still swept", pd in m.DISTRICTS, True)
for pd in ("PD49", "PD46", "PD45", "PD24"):
    t(f"2026-10-26 district {pd} swept", pd in m.DISTRICTS, True)
t("every key is a PDnn districtNum",
  all(re.fullmatch(r"PD\d\d", k) for k in m.DISTRICTS), True)
t("Fairfield Probate Court is PD49", m.DISTRICTS["PD49"], "Fairfield")

# ---- 2. all slices fail -> raise (silent-zero guard) ------------------------
print("silent-zero guard")
_orig = m._fetch_slice


def _boom(session, district, prefix):
    raise ConnectionError("simulated outage")


m._fetch_slice = _boom
h = m.CTProbateCourtsHarvester()
raised = None
try:
    list(h.harvest(since=date.today() - timedelta(days=10)))
except RuntimeError as e:
    raised = str(e)
t("all-slices-failed raises RuntimeError", raised is not None, True)
t("raise message names the count",
  raised is not None and f"all {len(m.DISTRICTS) * len(m.ALPHABET)} slices failed" in raised, True)
t("stats.slice_errors == districts x 26",
  h.stats.slice_errors, len(m.DISTRICTS) * len(m.ALPHABET))
t("stats.slices_ok == 0", h.stats.slices_ok, 0)
t("stats.rows_seen == 0", h.stats.rows_seen, 0)

# ---- 3. slices succeed with zero rows -> no raise ---------------------------
m._fetch_slice = lambda session, district, prefix: []
h = m.CTProbateCourtsHarvester()
sigs = list(h.harvest(since=date.today() - timedelta(days=10)))
t("empty-but-healthy sweep does not raise", len(sigs), 0)
t("empty sweep counts slices_ok", h.stats.slices_ok, len(m.DISTRICTS) * len(m.ALPHABET))
t("empty sweep has no slice_errors", h.stats.slice_errors, 0)

# ---- 4. one PD49 row in window -> one signal, no raise (mixed errors ok) ----
today = date.today()
STUB = {
    "caseId": 123456,
    "caseNumber": "PC-26-00001",
    "code": "DR",
    "courtName": "Fairfield Probate Court",
    "dateFiled": (today - timedelta(days=3)).isoformat(),
    "distNum": "PD49",
    "nameFirst": "FIRST",
    "nameLast": "LAST",
    "nameMiddle": "",
}


def _one_row(session, district, prefix):
    if district == "PD49" and prefix == "L":
        return [dict(STUB)]
    if district == "PD24":
        raise ConnectionError("one district down")   # partial outage
    return []


m._fetch_slice = _one_row
h = m.CTProbateCourtsHarvester()
sigs = list(h.harvest(since=today - timedelta(days=10)))
t("one in-window PD49 row -> one signal", len(sigs), 1)
s = sigs[0]
t("document_ref prefixed with district", s.document_ref, "PD49-PC-26-00001")
t("signal_type probate", s.signal_type, "probate")
t("raw_data.district PD49", s.raw_data.get("district"), "PD49")
t("raw_data.case_id persisted", s.raw_data.get("case_id"), 123456)
t("event_date = dateFiled", s.event_date, today - timedelta(days=3))
t("partial outage counted, not raised", h.stats.slice_errors, len(m.ALPHABET))
t("rows_seen 1", h.stats.rows_seen, 1)

# ---- 5. out-of-window row is filtered --------------------------------------
old = dict(STUB, dateFiled=(today - timedelta(days=400)).isoformat(),
           caseNumber="PC-99-00002")
m._fetch_slice = lambda session, district, prefix: [old] if (district, prefix) == ("PD49", "L") else []
h = m.CTProbateCourtsHarvester()
sigs = list(h.harvest(since=today - timedelta(days=10)))
t("row filed 400d ago is filtered by since", len(sigs), 0)
t("but it was read (rows_seen 1)", h.stats.rows_seen, 1)

m._fetch_slice = _orig
print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
