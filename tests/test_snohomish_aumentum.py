"""
Tests for the Snohomish Aumentum transfer-history parser.
No network — fixtures are the JSON shapes observed on
wa-snohomish.publicaccessnow.com on 2026-10-25 (party names redacted).
"""
from __future__ import annotations

import sys
from datetime import date
sys.path.insert(0, '.')

from backend.harvesters.snohomish_aumentum import (
    parse_transfer_history, _parse_sale_date, _parse_price,
)

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


def _row(sale_date, price, doc_type, docnum="E000000"):
    return {"values": [
        {"column": "SaleDate", "value": sale_date, "isReplacedWithCustomValue": False},
        {"column": "AdjustedSalesPrice", "value": price, "isReplacedWithCustomValue": False},
        {"column": "DocNumber", "value": docnum, "isReplacedWithCustomValue": False},
        {"column": "ConveyanceForm", "value": docnum, "isReplacedWithCustomValue": False},
        {"column": "Grantor", "value": "GRANTOR REDACTED", "isReplacedWithCustomValue": False},
        {"column": "Grantee", "value": "GRANTEE REDACTED", "isReplacedWithCustomValue": False},
        {"column": "DocSubType", "value": doc_type, "isReplacedWithCustomValue": False},
    ]}


def _payload(rows):
    return {
        "headers": [{"column": c, "availableValues": []} for c in
                    ("SaleDate", "AdjustedSalesPrice", "DocNumber", "ConveyanceForm",
                     "Grantor", "Grantee", "DocSubType")],
        "groups": [{"rows": rows, "totals": None, "groupedColumns": None,
                    "textColor": None, "backgroundColor": None, "groups": None}],
        "totalItems": len(rows),
        "grandTotals": [],
    }


print("═══ DATE / PRICE ═══")
t("portal date format", _parse_sale_date("1/2/2013 12:00:00 AM"), date(2013, 1, 2))
t("plain date", _parse_sale_date("9/27/2012"), date(2012, 9, 27))
t("empty date", _parse_sale_date(""), None)
t("garbage date", _parse_sale_date("n/a"), None)
t("price 730000.00", _parse_price("730000.00"), 730000)
t("price with $ and commas", _parse_price("$1,665,000.00"), 1665000)
t("price 0.00", _parse_price("0.00"), 0)
t("price empty", _parse_price(""), None)

print("═══ TRANSFER HISTORY (observed shapes) ═══")
# Canary parcel shape: 3 statutory warranty deeds, newest first.
p3 = _payload([
    _row("1/2/2013 12:00:00 AM", "730000.00", "Statutory Warranty Deed", "E020377"),
    _row("9/27/2012 12:00:00 AM", "684000.00", "Statutory Warranty Deed", "E017203"),
    _row("7/8/2005 12:00:00 AM", "563500.00", "Statutory Warranty Deed", "481860"),
])
t("3-row history → newest date/price, count 3",
  parse_transfer_history(p3), (date(2013, 1, 2), 730000, 3))

# Rows not in date order — max SaleDate must win, not the first row.
p_unordered = _payload([
    _row("2/17/2016 12:00:00 AM", "240000.00", "Statutory Warranty Deed"),
    _row("7/29/2026 12:00:00 AM", "1665000.00", "Statutory Warranty Deed"),
    _row("9/28/2005 12:00:00 AM", "0.00", "Quit Claim Deed"),
])
t("unordered rows → max date wins",
  parse_transfer_history(p_unordered), (date(2026, 7, 29), 1665000, 3))

# $0 "Other" conveyance as the only row: date kept, price 0 (task stores
# prices only when > 0 — same semantics as the SCOPI parser).
p_zero = _payload([_row("3/12/2003 12:00:00 AM", "0.00", "Other", "123456")])
t("$0 Other row → date kept, price 0, count 1",
  parse_transfer_history(p_zero), (date(2003, 3, 12), 0, 1))

# Unknown pin: HTTP 200, totalItems 0, one empty group.
p_empty = _payload([])
t("empty history → (None, None, 0)", parse_transfer_history(p_empty), (None, None, 0))

# Defensive: groups null / missing.
t("groups null", parse_transfer_history({"groups": None, "totalItems": 0}), (None, None, 0))
t("no groups key", parse_transfer_history({}), (None, None, 0))

# Undated row is skipped but still counted.
p_undated = _payload([
    _row("", "100.00", "Other"),
    _row("5/28/2013 12:00:00 AM", "0.00", "Other"),
])
t("undated row skipped, counted",
  parse_transfer_history(p_undated), (date(2013, 5, 28), 0, 2))

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
