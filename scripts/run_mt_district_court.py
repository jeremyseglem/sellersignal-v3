#!/usr/bin/env python3
"""
Scheduled runner for the Montana District Court harvester (FullCourt Web).

Runs in a GitHub Action (NOT the Railway app) because the portal's F5 TSPD
bot defense rejects non-browser fingerprints from both the Claude sandbox and
Railway egress — but Playwright Chromium in GitHub Actions clears it in ~5s
(verified 2026-07-24, mt-browser-probe.yml runs 30101582073 / 30103158817).

Strategy: DP (District Probate) case-number enumeration per court. The portal
"login" is anonymous — a court-picker select (name=tenant) + hidden
loginAction submit, no credentials. civilCase.do takes formatCaseType /
formatCaseYear / formatCaseNumber and renders a Litigants table with
Role=Applicant (the PR/decision-maker) and Role=Decedent (the parcel-match
key). We walk DP-{year}-{seq} upward from a per-court/-year cursor, parse each
viewable case, and write probate/divorce signals to raw_signals_v3. The app's
existing matcher links them to parcels by decedent name — no app change.

The cursor (highest sequence seen per court+year) is stored in raw_signals_v3
itself (max document_ref) so each run resumes where the last stopped and only
walks NEW cases. A bounded miss-streak stops each year's walk at the current
filing frontier.

ENV:
  SUPABASE_URL           https://eeqsbvizgpuehphiaslo.supabase.co
  SUPABASE_SERVICE_KEY   service-role key (write) — GitHub secret
  WRITE                  "1" to write; anything else = dry run (default)
  YEAR                   filing year to sweep (default: current year)
  COURTS                 comma list of court keys (default: gallatin,flathead)
  MAX_MISS               consecutive not-found/unauth before stopping a year
                         (default 25)
  MAX_CASES              hard cap on lookups per court per run (default 400)

Dependencies: playwright + chromium (installed in the Action), requests (pip).
"""
import os
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend", "harvesters"))
import mt_district_court as mt  # noqa: E402
import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WRITE = os.environ.get("WRITE", "0") == "1"
# Env vars from the workflow can be set-but-empty (e.g. YEAR: '' default),
# which overrides os.environ.get's own default — so coalesce with `or`.
YEAR = int(os.environ.get("YEAR") or datetime.now().year)
COURTS = [c.strip() for c in
          (os.environ.get("COURTS") or "gallatin,flathead").split(",") if c.strip()]
MAX_MISS = int(os.environ.get("MAX_MISS") or "25")
MAX_CASES = int(os.environ.get("MAX_CASES") or "400")
# FULL_SWEEP=1 forces the walk to start at seq 1 regardless of the resume
# cursor, relying on the county-scoped skip index to hop over already-stored
# sequences. Use to recover gaps below the cursor (e.g. Flathead 2026 1-100,
# skipped by the pre-fix cross-court cursor contamination).
FULL_SWEEP = os.environ.get("FULL_SWEEP", "0") == "1"
# Lookups per browser context before recycling (TSPD session budget ~100).
RECYCLE_EVERY = int(os.environ.get("RECYCLE_EVERY") or "75")
TABLE = "raw_signals_v3"
SOURCE = "mt_district_court"
BASE = "https://dcportal.pubcourts.mt.gov/fullcourtweb"

# Court key → (tenant display name, jurisdiction market_key). Gallatin and
# Madison both fall under MT_GALLATIN territory; Flathead is MT_FLATHEAD.
COURT_META = {
    # court key → (tenant display name, jurisdiction market_key, county code)
    # County code is parts[1] of document_ref (DP-{code}-{year}-{seq}-{suffix}).
    # It scopes the resume cursor + skip index to THIS court — without it,
    # another court's refs advance the cursor (first Flathead run resumed at
    # seq 101 because Gallatin's max was 100, silently skipping Flathead
    # 2026 cases 1-100). None = unknown until first run (no refs match, walk
    # starts at seq 1; per-ref dedupe on write still protects).
    "gallatin": ("Gallatin District Court", "MT_GALLATIN", "16"),
    "madison":  ("Madison District Court", "MT_GALLATIN", None),
    "flathead": ("Flathead District Court", "MT_FLATHEAD", "15"),
}


def _headers():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json"}


def existing_refs() -> set:
    """All document_refs already stored for this source (for skip + cursor)."""
    if not (SUPABASE_URL and SERVICE_KEY):
        return set()
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=_headers(),
                     params={"source_type": f"eq.{SOURCE}",
                             "select": "document_ref"}, timeout=60)
    r.raise_for_status()
    return {row["document_ref"] for row in r.json()}


def start_sequence(refs: set, year: int, county_code: str | None) -> int:
    """Resume cursor: 1 + highest DP sequence already stored for this year
    AND this court's county code. document_ref shape: DP-16-2026-0000050-II
    → county 16, sequence 50. Only DP refs count — a DR/DV divorce ref must
    not advance the probate cursor — and only THIS court's refs count: each
    court has its own sequence space, so another court's refs must not
    advance the cursor either. county_code=None (court never harvested)
    matches nothing → walk starts at seq 1."""
    hi = 0
    for ref in refs:
        parts = ref.split("-")
        # DP - {county} - YEAR - SEQ - suffix
        if (len(parts) >= 4 and parts[0] == "DP" and parts[2] == str(year)
                and county_code is not None and parts[1] == county_code):
            try:
                hi = max(hi, int(parts[3]))
            except ValueError:
                pass
    return hi + 1


def write_rows(rows: list) -> int:
    """Upsert with batch dedupe (keep-last on (source_type, document_ref)) —
    same guard the topics-citations fix added; the enumeration shouldn't
    produce dupes but a case with a suffix variant could collide."""
    if not rows:
        return 0
    seen, deduped = {}, []
    for row in rows:
        seen[(row["source_type"], row["document_ref"])] = row
    deduped = list(seen.values())
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE}",
                      headers={**_headers(),
                               "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "source_type,document_ref"},
                      json=deduped, timeout=180)
    if not r.ok:
        print(f"  WRITE ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return len(deduped)


def select_court(page, tenant_display: str):
    """Anonymous tenant login: pick the court in the select, click the hidden
    loginAction submit. Lands on mainMenu.do."""
    page.goto(f"{BASE}/start.do", wait_until="commit", timeout=120000)
    # TSPD challenge resolves via JS then reloads.
    for _ in range(12):
        time.sleep(5)
        if page.query_selector("select#tenant"):
            break
    page.select_option("select#tenant", tenant_display)
    time.sleep(1)
    page.evaluate("""() => {
        const f = document.forms['loginForm'];
        const b = f.querySelector("input[name='loginAction']");
        if (b) b.click(); else f.submit(); }""")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(4)


def lookup_case(page, year: int, seq: int) -> str:
    """Retrieve one DP case detail page's HTML. Returns '' on navigation
    failure. showLitigants is checked so the Litigants table renders."""
    page.goto(f"{BASE}/civilCase.do?CourtCaseId=0",
              wait_until="domcontentloaded", timeout=60000)
    # The case-lookup form must be present before we fill it. After a tenant
    # switch the first hit can land on the dashboard or a redirect, so wait
    # for the form explicitly rather than assuming it's there.
    try:
        page.wait_for_selector("form[name='civilCaseForm']", timeout=15000)
    except Exception:
        return page.content()  # caller treats missing form as a miss
    page.evaluate("""(args) => {
        const [yr, seq] = args;
        const f = document.forms['civilCaseForm'];
        f.querySelector("input[name='formatCaseType']").value = 'DP';
        f.querySelector("input[name='formatCaseYear']").value = String(yr);
        f.querySelector("input[name='formatCaseNumber']").value =
            String(seq).padStart(7, '0');
        const lit = f.querySelector("input[name='reportBean.showLitigants'][type='checkbox']");
        if (lit && !lit.checked) lit.click();
        f.querySelector("input[name='retrieveAction']").click();
    }""", [year, seq])
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)
    return page.content()


def sweep_court(page, court_key: str, refs: set, dry_samples: list,
                new_page=None) -> dict:
    tenant, jurisdiction, county_code = COURT_META[court_key]
    print(f"\n[{court_key}] tenant={tenant!r} jurisdiction={jurisdiction} "
          f"county_code={county_code} year={YEAR}")
    # NOTE: court selection happens in the caller's new_page() factory (both
    # on initial page and on every mid-court recycle) — do not select here.

    seq = 1 if FULL_SWEEP else start_sequence(refs, YEAR, county_code)
    print(f"[{court_key}] resume at DP-{YEAR}-{seq:07d} "
          f"(full_sweep={FULL_SWEEP}, refs_in_db_for_source={len(refs)})")

    # Pre-index the DP sequences already stored for this year AND this court
    # so the resume walk skips them in O(1) (handles gaps if the cursor was
    # reset). Must be county-scoped like the cursor — otherwise Gallatin's
    # stored seqs make Flathead's walk skip its own unharvested cases.
    stored_seqs = set()
    for ref in refs:
        parts = ref.split("-")
        if (len(parts) >= 4 and parts[0] == "DP" and parts[2] == str(YEAR)
                and county_code is not None and parts[1] == county_code):
            try:
                stored_seqs.add(int(parts[3]))
            except ValueError:
                pass

    # miss_streak counts GENUINE frontier evidence only (not-found / not-
    # authorized). Transient failures (nav errors, TSPD/tar-pit noparse
    # pages) go to err_streak instead: retry the seq once, then skip it,
    # and abort the court loudly after ERR_ABORT consecutive failures.
    # Conflating the two is what killed Flathead 2025 twice on 2026-07-24:
    # a flaky 25-lookup stretch advanced miss_streak and falsely concluded
    # "year exhausted" at seq 126 when the real frontier was ~400+.
    ERR_ABORT = 8
    _last_recycle_at = [0]
    miss_streak, err_streak, looked, wrote, sigs = 0, 0, 0, 0, 0
    retried = set()
    batch = []
    while miss_streak < MAX_MISS and looked < MAX_CASES:
        if err_streak >= ERR_ABORT:
            print(f"[{court_key}] ABORT: {err_streak} consecutive transient "
                  f"errors at DP-{YEAR}-{seq:07d} — portal unhealthy, not "
                  f"advancing frontier. Cursor stays at last stored seq; "
                  f"re-run recovers from there.")
            break
        if seq in stored_seqs:   # already harvested this DP sequence
            seq += 1
            continue
        # TSPD grants each browser session a budget of ~100 case lookups
        # before serving 'Request Rejected' walls (observed 2026-07-25:
        # three consecutive runs each died at ~100 lookups regardless of
        # pacing). Recycle the context every RECYCLE_EVERY lookups to stay
        # inside the budget and let a single run finish a whole year.
        if new_page is not None and looked and looked % RECYCLE_EVERY == 0 \
                and looked != _last_recycle_at[0]:
            _last_recycle_at[0] = looked
            print(f"[{court_key}] recycling browser context at looked={looked}")
            page = new_page()
            time.sleep(2.0)
        looked += 1
        try:
            html = lookup_case(page, YEAR, seq)
        except Exception as e:
            print(f"  DP-{YEAR}-{seq:07d} nav ERR {type(e).__name__}: {e}")
            if seq not in retried:
                retried.add(seq)
                time.sleep(3.0)          # brief pause, retry same seq once
                continue
            err_streak += 1
            seq += 1
            continue

        low = html.lower()
        if "not authorized to view" in low or "no matching" in low \
                or "was not found" in low:
            kind = ("unauth" if "not authorized" in low else "notfound")
            print(f"  DP-{YEAR}-{seq:07d} miss:{kind}")
            err_streak = 0               # portal answered — errors cleared
            miss_streak += 1
            seq += 1
            continue

        case = mt.parse_case_detail(html)
        if not case:
            # No miss-string AND no parseable case detail — likely a TSPD
            # challenge/tar-pit page or a layout change. Transient: treat
            # like a nav error (retry once, then err_streak), NOT frontier
            # evidence.
            print(f"  DP-{YEAR}-{seq:07d} err:noparse len={len(html)} "
                  f"title={html[html.find('<title>')+7:html.find('</title>')][:60]!r}"
                  if '<title>' in html else
                  f"  DP-{YEAR}-{seq:07d} err:noparse len={len(html)} (no title)")
            if seq not in retried:
                retried.add(seq)
                time.sleep(3.0)
                continue
            err_streak += 1
            seq += 1
            continue

        miss_streak = 0  # a real case resets the frontier counter
        err_streak = 0
        row = mt.to_signal_row(case, jurisdiction)
        if row:
            sigs += 1
            if WRITE:
                batch.append(row)
                if len(batch) >= 25:
                    wrote += write_rows(batch)
                    batch = []
            elif len(dry_samples) < 5:
                dry_samples.append(row)
            print(f"  DP-{YEAR}-{seq:07d} {case['signal_type']:8s} "
                  f"{case.get('case_subtype') or ''} | "
                  f"parties={[p['raw'] for p in row['party_names']]}")
        else:
            print(f"  DP-{YEAR}-{seq:07d} viewable but not probate/divorce "
                  f"(subtype={case.get('case_subtype')})")
        seq += 1
        time.sleep(0.8)

    if WRITE and batch:
        wrote += write_rows(batch)
    print(f"[{court_key}] looked={looked} signals={sigs} wrote={wrote} "
          f"stopped_at=DP-{YEAR}-{seq:07d} miss_streak={miss_streak}")
    return {"looked": looked, "signals": sigs, "wrote": wrote}


def main():
    if WRITE and not (SUPABASE_URL and SERVICE_KEY):
        print("  WRITE requested but SUPABASE_URL/SERVICE_KEY missing — aborting.")
        sys.exit(1)

    refs = existing_refs() if (WRITE or SUPABASE_URL) else set()
    print(f"[mt_district_court] year={YEAR} courts={COURTS} write={WRITE} "
          f"already_in_db={len(refs)} max_miss={MAX_MISS} max_cases={MAX_CASES}")

    totals = {"looked": 0, "signals": 0, "wrote": 0}
    dry_samples = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        for court_key in COURTS:
            if court_key not in COURT_META:
                print(f"[skip] unknown court key {court_key!r}")
                continue
            # Fresh context per court — FullCourt pins the selected tenant to
            # the session, so switching courts in one context lands on the
            # wrong (or a stale) court. A new context re-runs the anonymous
            # tenant login cleanly. (First live run: flathead returned 0 with
            # a shared context because civilCaseForm never rendered after the
            # in-session switch.)
            # Fresh context per court — FullCourt pins the selected tenant to
            # the session, so switching courts in one context lands on the
            # wrong (or a stale) court. A new context re-runs the anonymous
            # tenant login cleanly. The same factory is handed to sweep_court
            # so it can recycle mid-court every RECYCLE_EVERY lookups (TSPD
            # session budget).
            ctx_holder = [None]

            def new_page():
                if ctx_holder[0] is not None:
                    try:
                        ctx_holder[0].close()
                    except Exception:
                        pass
                ctx_holder[0] = b.new_context(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 1000}, locale="en-US")
                pg = ctx_holder[0].new_page()
                tenant = COURT_META[court_key][0]
                select_court(pg, tenant)
                return pg

            try:
                page = new_page()
                res = sweep_court(page, court_key, refs, dry_samples,
                                  new_page=new_page)
                for k in totals:
                    totals[k] += res[k]
            except Exception as e:
                print(f"[{court_key}] SWEEP ERR {type(e).__name__}: {e}")
            finally:
                if ctx_holder[0] is not None:
                    try:
                        ctx_holder[0].close()
                    except Exception:
                        pass
        b.close()

    print(f"\n[mt_district_court] TOTAL looked={totals['looked']} "
          f"signals={totals['signals']} wrote={totals['wrote']}")
    if totals["looked"] == 0:
        # Every court's sweep died (portal timeout / TSPD tar-pit / layout
        # change) — a green run here masks a dead harvester, same failure
        # mode as the Travis recorder (f618403). Fail the Action so the
        # scheduled cron alarms instead of rotting silently.
        print("[mt_district_court] FATAL: zero cases looked at across all "
              "courts — failing loudly")
        sys.exit(1)
    if not WRITE:
        print("[mt_district_court] DRY RUN — no writes. Sample rows:")
        for row in dry_samples:
            print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
