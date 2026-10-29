"""
Tests for the Dallas recorder URL-search fallback (2026-10-29) and the runner's
no-error silent-zero guard. No network, no browser: a fake page stands in for
Playwright. The fake grid line uses the tab layout the Dallas _ROW_RE parses;
party names are placeholders.

Run: python tests/test_dallas_url_fallback.py
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "harvesters"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import dallas_recorder as dr  # noqa: E402

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


ROW = ("SMITH JOHN\tDOE JANE\tAFFIDAVIT OF HEIRSHIP\t10/15/2026\t202600123456\t"
       "\tDALLAS\tLOT 1 BLK 2\n")
ROW2 = ("ROE RICHARD\tROE MARY\tWARRANTY DEED\t10/15/2026\t202600123457\t"
        "\tDALLAS\tLOT 3 BLK 4\n")


class FakePage:
    """URL loads render `url_text`; a form search renders `form_text`."""

    def __init__(self, url_text: str, form_text: str):
        self.url_text, self.form_text = url_text, form_text
        self.text = ""
        self.url = ""
        self.gotos = []

    def goto(self, url, **kw):
        self.gotos.append(url)
        self.url = url
        self.text = self.url_text if "/results" in url else ""

    def wait_for_load_state(self, *a, **kw):
        return None

    def query_selector_all(self, sel):
        return []

    def inner_text(self, sel):
        return self.text

    def query_selector(self, sel):
        return None


dr.time = types.SimpleNamespace(sleep=lambda s: None)  # no real waits
calls = []


def fake_ui(page, begin, end):
    calls.append((begin, end))
    page.text = page.form_text


dr._ui_drive_search = fake_ui
D = date(2026, 10, 15)

# ---- 1. URL load renders rows: no fallback ---------------------------------
calls.clear()
p = FakePage(url_text=ROW + ROW2, form_text="")
rows = list(dr.iter_window_rows(p, D, D))
t("URL grid with rows → 2 rows", len(rows), 2)
t("URL grid with rows → form not driven", calls, [])
t("URL path loaded once", len(p.gotos), 1)

# ---- 2. URL load renders no grid, form does: fallback reads the rows -------
calls.clear()
p = FakePage(url_text="Loading results for 10/15/2026-10/15/2026", form_text=ROW + ROW2)
rows = list(dr.iter_window_rows(p, D, D))
t("empty URL grid → form driven once for the window", calls, [(D, D)])
t("empty URL grid → rows come from the form search", len(rows), 2)
t("doc types parsed after fallback", sorted(r["doc_type"] for r in rows),
  ["AFFIDAVIT OF HEIRSHIP", "WARRANTY DEED"])

# ---- 3. a truly empty day stays empty (weekend) ----------------------------
calls.clear()
p = FakePage(url_text="no results", form_text="no results")
rows = list(dr.iter_window_rows(p, D, D))
t("empty both ways → 0 rows, no exception", len(rows), 0)
t("empty both ways → form tried once", len(calls), 1)

# ---- 4. switch off restores URL-only behaviour -----------------------------
calls.clear()
dr.URL_FALLBACK_UI = False
p = FakePage(url_text="Loading results", form_text=ROW)
rows = list(dr.iter_window_rows(p, D, D))
t("URL_FALLBACK_UI False → no form drive", calls, [])
t("URL_FALLBACK_UI False → 0 rows (old behaviour)", len(rows), 0)
dr.URL_FALLBACK_UI = True

# ---- 5. UI_DRIVE tenants are untouched -------------------------------------
calls.clear()
dr.UI_DRIVE = True
p = FakePage(url_text="", form_text=ROW)
rows = list(dr.iter_window_rows(p, D, D))
t("UI_DRIVE tenant → form driven once, no URL load", (len(calls), p.gotos), (1, []))
dr.UI_DRIVE = False

# ---- 6. runner weekday helper (guard input) --------------------------------
# Import the runner without running main(); playwright may be absent here.
sys.modules.setdefault("playwright", types.ModuleType("playwright"))
sync_api = types.ModuleType("playwright.sync_api")
sync_api.sync_playwright = None
sys.modules.setdefault("playwright.sync_api", sync_api)
import run_dallas_recorder as runner  # noqa: E402

t("Sat..Sun has no weekday", runner._has_weekday(date(2026, 10, 17), date(2026, 10, 18)), False)
t("Sat..Mon has a weekday", runner._has_weekday(date(2026, 10, 17), date(2026, 10, 19)), True)
t("single Wednesday", runner._has_weekday(date(2026, 10, 14), date(2026, 10, 14)), True)

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
