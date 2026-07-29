# SellerSignal V3 — Manifesto

**Last updated:** 2026-07-29 evening (FL_PALM_BEACH launched — 10th market, first Florida market: 8 ZIPs / ~90.6k parcels live, structural buckets at cap; recorder + docket harvesters pending — see build journal). Prior: 2026-07-22 (map: all parcels visible + Earth lot-polygon persistence — schema/032 PENDING APPLICATION; earlier: production outage fixed: PostgREST h2 pool + CT slash-PIN dossier 404). Prior: 2026-07-21 (Sun Belt signal diagnosis — Travis recorder soft-blocked, Maricopa name fix, recorder-vs-docket ceiling). Prior: 2026-07-18 (CT statewide probate harvester live — probate leads across all 9 CT territories; earlier same day: CT Gold Coast: 06840, 06880, 06897, 06883 live; Darien deferred — see build journal). Prior: 2026-07-17 (6-ZIP expansion: 98116, 98144, 98036, 98296, 85258, 75219 — see build journal). Prior: 2026-06-16 (LAUNCH DAY. Went live: Stripe live key/price/webhook, Stannp `STANNP_MODE=live`, user purge; fixed dead Resend key in Supabase Auth SMTP; converted to password auth. First paying customer onboarded — live Stripe checkout→webhook→territory path proven end-to-end. CRITICAL fix `6ea8fe2`: the map + parcel-dossier read endpoints were publicly accessible with no auth — owner_name/address/signals for all parcels across all 90 ZIPs were scrapable unauthenticated. Added a `require_zip_access` gate to `map_data.py`/`parcels.py` (X-Admin-Key server exception preserved), switched the frontend map/parcel calls to authed, flipped AuthGate to secure-by-default, and made logout hard-redirect. Verified: no-auth → 401, authorized → 200. `/api/zip-polygons` left public (boundaries only, no PII) so ZIP browsing still works. Carry-forward: add FK on `agent_territories_v3.agent_id` (ghost claims); rotate exposed PAT/admin-key/service-role key.)
**Status:** Living document. Update on every session that changes architecture, ZIPs, or canonical paths.
**Source of truth:** This file. Anything in `docs/STATUS.md`, `docs/ZIP_BUILD_GUIDE.md`, or `docs/SESSION_END_*.md` may be stale — defer to this document when they disagree.

---

## Standing rules (Jeremy's)

These apply to every Claude session. Non-negotiable.

1. Never build without explicit confirmation.
2. Never assume; never invent data. Reference this manifesto and the build journal before proposing anything.
3. Direct answers, no hedging, no emojis. When wrong, own it without spiraling.
4. "Building" is jargon — use plain English ("in pipeline", "on watch list").
5. Don't drift from the working code path. The 114 live territories across 10 markets (WA_KING, WA_SNOHOMISH, AZ_MARICOPA, TX_DALLAS, TX_TRAVIS, TX_COLLIN, CT_FAIRFIELD, MT_GALLATIN, MT_FLATHEAD, FL_PALM_BEACH) are the standard; match against them.
6. Skip-trace and Lob letter sending are NOT wired for beta (placeholder buttons).
7. Brian is co-founder for product validation discussions.

---

## What SellerSignal is

An AI-powered intelligence platform for luxury real estate agents in defined ZIP territories. It surfaces motivated sellers using a categorical pressure model on public-record investigation signals (probates, divorces, tax foreclosures, obituaries) joined to parcel data.

**Differentiator:** identifies the decision-maker by name — the personal representative on a probate (a living adult child or spouse), not the deceased homeowner. Agent gets a Contact now lead with the actual person to call.

**Beta model:** $299/month per ZIP territory, exclusive (one agent per ZIP), invite-only first-to-claim.

**Geographic scope:** **114 live territories across 10 markets** as of 2026-07-29: King County WA (34), Snohomish County WA (8), Maricopa County AZ (25), Dallas County TX (9), Travis County TX (9), Collin County TX (5), Fairfield County CT (9), Montana Gallatin+Flathead (6), Palm Beach County FL (8). (Counts per live zip_coverage_v3; treat coverage endpoint as source of truth if this drifts.)

### WA_KING live ZIPs (32; other markets listed in Live measurements below)

```
Bellevue:       98004, 98005, 98006, 98007
Issaquah:       98027, 98029
Kirkland:       98033, 98034
Maple Valley:   98038
Medina:         98039
Mercer Island:  98040
Redmond:        98052, 98053
Sammamish:      98074, 98075
Woodinville:    98072, 98077
Seattle:        98103, 98105, 98112, 98115, 98117, 98119, 98136, 98199
Snohomish:      98290 (cross-county pilot, separate market_key WA_SNOHOMISH)
```

### Live measurements (snapshot 2026-06-12 evening)
```
total live territories: 85
  WA_KING:      32   (King County, WA — the original market)
  WA_SNOHOMISH:  6   (Edmonds + Lake Stevens; daily-report harvester)
  AZ_MARICOPA:  24   (Scottsdale/Phoenix; Recorder OCR harvester + county inversion;
                      today's adds: 85016 Biltmore, 85251 Old Town Scottsdale,
                      85012 Central Corridor, 85250 McCormick Ranch)
  TX_DALLAS:     9   (Park Cities/Preston Hollow cluster; today's adds: 75244, 75206 M Streets)
  TX_TRAVIS:     9   (Austin; today's adds: 78738 Lakeway, 78732 Steiner Ranch, 78704 Travis Heights)
  TX_COLLIN:     5   (NEW today: 75093 Plano West, 75034 Frisco SW, 75078 Prosper,
                      75069 McKinney, 75013 Allen — 53,332 parcels, 1,647 leads,
                      100% geometry at seed time via CCAD centroids)

Today's expansion wave totals: 14 ZIPs, ~4,668 structural Contact Now leads
(wave 1: 9 ZIPs / 3,021 leads; wave 2 Collin: 5 ZIPs / 1,647 leads).
TX signal sources: tx_dallas_recorder (live, daily cron), tx_travis_recorder
(blocked on UI panel-open, TOPICs covers Travis daily), tx_collin_recorder
(LIVE 2026-06-12 — first run 5,417 grid rows / 34 estate instruments / 13
county-resolved / 34 signals written; daily cron 7:50am CT).
```

---

## Architectural principles — MUST preserve

These are first-order design commitments from STATUS.md that still hold:

1. **No additive scoring.** Pressure is categorical (0/1/2/3), never continuous.
2. **No LLM-delegated decisions.** Claude generates narrative copy from verified facts only.
3. **Trust tiers over confidence numbers.** Every signal is high/medium/low.
4. **Hard pressure requires court verification.** NOD, trustee sale, court-verified probate/divorce, verified obituary.
5. **Forbidden signals.** Never score `previously_listed` alone as pressure (fires on ~82% of luxury parcels).
6. **One action per lead.** `recommend_action` returns exactly one category with one tone.
7. **Tone matches cause.** Foreclosure = urgent. Probate/divorce/obituary = sensitive.
8. **ZIP-first architecture.** Every piece of data, every API call, every subscription is scoped to a ZIP. `zip_coverage_v3` is the source of truth.
9. **Narrative, never decisions, for Claude.** Anthropic code paths are "generate narrative text from verified facts," never "decide what to do."

---

## The pipeline (how a lead is born)

```
KC Superior Court portal (https://dja-prd-ecexap1.kingcounty.gov)
  ↓ harvesters/kc_superior_court.py pulls case listings
  ↓
raw_signals_v3 (probate / divorce filings)
  ↓ harvesters/matcher.py links cases to parcels by canonicalized owner name
  ↓
raw_signal_matches_v3
  ↓ harvesters/kc_court_participants.py drills into each case for parties tab
  ↓
case_parties_v3 ← personal representative name + pr_classification (family/corporate/attorney/unknown)
  ↓ api/briefings.py enriches each match with contact_status
  ↓
playbook.call_now in /api/briefings/:zip
  ↓
agent UI (frontend/src/pages/BriefingPage.jsx)
```

**Eligibility contract Rule 6 (added April 2026):** A probate match is only promoted to Contact now when `contact_status == 'family_pr_identified'`. Probate matches without an identified family PR stay in Build Now.

---

## The canonical onboarding pipeline (new ZIPs)

The single canonical path for adding a new KC ZIP. Lives in `backend/tasks/zip_onboarding.py`. Trigger via `POST /api/admin/onboard-zip/{zip}?city=...`. Monitor via `GET /api/admin/onboard-status/{zip}`.

```
1. register       — create zip_coverage_v3 row (status=in_development)   ~1s
2. seed           — upsert parcels_v3 from data/seeds/wa-king-{zip}-owners.json
                    (owner_name, last_transfer_date, tenure_years, value,
                     address, owner_type)                                ~15s
3. classify       — assign signal_family archetype                       ~5s
4. band           — assign Band 0-4                                      ~5s
5. publish        — flip status=live (force=True)                        ~1s
6. refresh_counts — compute current_call_now_count snapshot              ~10s
─── ZIP IS LIVE FOR BUILD NOW HERE — agents can claim, briefing renders ───
7. canonicalize   — Haiku 4.5 name parsing for probate-matcher precision
                    (concurrency=3, best-effort, ~2 hours per ZIP)
                    Required for Contact now precision; not for Build Now.
```

**End states the orchestrator can land in:**
- `completed` — all 7 steps succeeded
- `live_canonicalize_pending` — steps 1-6 succeeded, step 7 deferred (another ZIP's canon was holding the lock). ZIP is fully live; canon needs re-trigger to run.
- `live_canonicalize_failed` — steps 1-6 succeeded, step 7 raised. ZIP is live; canon can be retried out-of-band.
- `failed` — pre-publish step failed; ZIP is NOT live.

**Operational rules learned the hard way (May 17, 2026):**
- **Fire one ZIP at a time.** Parallel-N onboarding exhausts the Supabase HTTP/2 stream pool and produces random failures at register/seed/classify/band. Wait until a ZIP reaches live state before firing the next.
- **Retry transient classify failures.** `ConnectionTerminated`/`Server disconnected` errors hit random pipeline steps. The orchestrator's 3-attempt `_retry` handles most, but occasionally a step exhausts retries — re-fire the whole orchestrator (idempotent, picks up where it left off).
- **Canonicalize takes ~2 hours per ZIP at conc=3.** It's the long pole. ZIPs are usable for Build Now immediately after step 6; Contact now precision improves as canon completes.

---

## Seed file builder

The seed JSON files (`data/seeds/wa-king-{zip}-owners.json`) are built by `scripts/build_kc_owners.py` from King County's public bulk assessor data:

- `EXTR_RPSale.csv` — https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip (~150 MB)
- `EXTR_RPAcct_NoName.csv` — https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Account.zip (~19 MB)

Owner names come from RPSale.BuyerName on the most recent sale, NOT from RPAcct (King County strips owner names from the RPAcct bulk download per RCW 42.56.070(8)).

**Address-coverage gate:** the builder refuses to write a seed file if address coverage falls below `MIN_ADDRESS_COVERAGE` (default 80%). This guards against the May 10 bug where six seed files were committed with 0% address coverage.

**Usage:**
```
mkdir -p /tmp/kc-data && cd /tmp/kc-data
curl -sL -A "Mozilla/5.0" \
  "https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip" -o RPSale.zip
curl -sL -A "Mozilla/5.0" \
  "https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Account.zip" -o RPAcct.zip
unzip -o RPSale.zip && unzip -o RPAcct.zip

TARGET_ZIP=98XYZ KC_DATA=/tmp/kc-data python3 scripts/build_kc_owners.py
```

See module docstring at the top of the file for full details.

---

## WA court system architecture (cross-county signal harvesting)

Discovered during the Snohomish discovery session (May 18-19, 2026). This is the master picture for how court signals work across all Washington counties — KC is the exception, not the template.

**Two distinct court records systems in WA:**

1. **King County only** — KC built its own custom portal at `dja-prd-ecexap1.kingcounty.gov`. Supports date-range + case-type filtered search via case listings → case detail → parties tab. Our existing harvesters (`kc_superior_court.py` + `kc_court_participants.py`) target this. KC is the **only** county on its own system.

2. **All other 38 WA counties** — use the statewide **Judicial Information System (JIS)** at `dw.courts.wa.gov` (ColdFusion, AOC-maintained). Name-search or case-number-search only — **no "all probate cases in date range" search exists.** Search form is reCAPTCHA-v2 gated. Results render via Tabulator (JS table from JSON XHR). Direct case-detail URLs (`?fa=home.casedetail&caseNumber=X`) return error pages — must go through the search flow.

**The unlock for non-KC counties: Daily New Case Reports.**

Most/all WA county clerks publish daily PDF reports of new case filings — no reCAPTCHA, no name search required, no subscription. Snohomish publishes at `https://snohomishcountywa.gov/5516/Daily-New-Case-and-Judgment-Audit-Report`. The PDF includes a structured table:

```
Case Number | File Date | Category | Case Type Code | Case Type Desc | Connection Type | Party
26-3-01021-31 | 5/15/2026 | Family | DIC | Dissolution of Marriage | PET | KAUR, TAYLOR LYNN
26-4-01015-31 | 5/18/2026 | Probate or Family | EST | Estate | DEC | Zettl, Judith Ann
```

**Case type code catalog (Snohomish, observed May 18 sample):**

| Code | Description | Signal type |
|------|-------------|-------------|
| EST | Estate | probate |
| WLL | Will Only | probate |
| TRS | Trust | probate |
| GDN | Guardianship | probate |
| DIC | Dissolution of Marriage (contested) | divorce |
| DIN | Dissolution of Marriage (notice) | divorce |
| TAXDOR | Revenue Tax Warrant | tax_foreclosure |
| TAXESD | Employment Security Dept tax warrant | tax_foreclosure |
| TAXLI | Labor & Industries tax warrant | tax_foreclosure |
| COM | Commercial | (potential LLC signal) |
| ABJ | Abstract of Judgment | (potential property judgment) |

**Connection types (parties on a case):**
- `DEC` — decedent (the deceased — primary match key for probate)
- `PET` — petitioner (often the personal representative once appointed, OR the divorce filer)
- `RSP` — respondent (divorce respondent, guardianship subject)
- `ATY` / `ATYZ` — attorney
- `WIPPET` / `WIPRSP` — petitioner/respondent with information protected
- `PLA` / `DEF` — civil cases
- `MNR` — minor

**Critical limitation: PR not on day-1 filing.**

The day a probate case is filed, only the decedent is named. The Personal Representative is appointed in a later filing (Petition for Letters Testamentary) — typically weeks later. This means Snohomish probate leads launch in `contact_status='no_pr_yet'` state (same as KC's transient probate state — the dossier UI handles it). PR enrichment is **Phase 2** (see "On the horizon").

**Snohomish-specific URL patterns:**

```
Daily New Case Reports landing page:
  https://snohomishcountywa.gov/5516/Daily-New-Case-and-Judgment-Audit-Report

Per-day report file:
  https://snohomishcountywa.gov/DocumentCenter/View/{doc_id}/{Month-DD-YYYY-New-Case-Report}

Daily Judgment Audit Reports also published (separate file):
  https://snohomishcountywa.gov/DocumentCenter/View/{doc_id}/{Month-DD-YYYY-Judgment-Audit-Report}
```

Reports are released after court close on each business day. May 18 (Mon) report covered cases entered into the system 5/15 (Fri) through 5/18.

**Phase 2 — PR enrichment (post-launch, not yet built):**

Three options for upgrading no_pr_yet leads to family_pr_identified:
1. **Statewide JIS scrape with reCAPTCHA solving** (2captcha-style integration, ~$2-3 per 1000 captchas) — works for all 38 non-KC counties.
2. **Snohomish County Odyssey Portal subscription** (paid annual, billed Feb 1) — authenticated access to case detail. Snohomish only.
3. **Daily court docket scrape** — if county clerks publish daily "case activity" reports (not just new filings) with party additions, we can detect PR appointments without scraping case detail.

Decision deferred until Phase 1 is live and we know how often agents ask for PR names that aren't yet populated.

---

## Snohomish County onboarding pipeline

Same orchestrator (`backend/tasks/zip_onboarding.py`) as KC ZIPs — the pipeline is source-agnostic. The only Snohomish-specific layers are the **seed builder** and the **court signal harvester**.

**Bulk parcel data source — Snohomish County Open Data Portal:**

- Catalog URL: `https://snohomish-county-open-data-portal-snoco-gis.hub.arcgis.com/api/feed/dcat-us/1.1` (DCAT JSON, 478KB, full county dataset index)
- Parcels feature service: `https://services6.arcgis.com/z6WYi9VRHfgwgtyW/arcgis/rest/services/Parcels/FeatureServer/0`
  - Direct REST query (recommended over CSV export for our use):
    `{FeatureServer/0}/query?where=SITUSZIP='98020'&outFields=*&f=json&returnGeometry=false`
  - Pagination via `resultOffset` / `resultRecordCount` (max 2000/page)
- Updated 3x per week by Snohomish County Assessor

**Schema highlights (vs KC's RPSale + RPAcct split):**

Snohomish has owner data **in a single feature service** — better than KC's two-file structure:

| Snohomish field | KC equivalent | Notes |
|-----------------|---------------|-------|
| `PARCEL_ID` | `Major+Minor` | primary parcel key |
| `OWNERNAME` | `BuyerName` (from RPSale) | joint owners on one line ("HANSON BART W & CHERYL K") |
| `OWNERLINE1`/`CITY`/`ZIP` | TaxpayerName mailing | for absentee detection |
| `TAXPRNAME` | (separate field) | useful for trustee/LLC distinction |
| `SITUSADDRESS`/`SITUSZIP` | `SitusAddr` | property address |
| `USECODE` | `PropertyType` | "111 Single Family Residence" etc. |
| `MKTTL` | `AppraisedTotal` | total market value (band input) |

**Target ZIPs and volumes (May 19, 2026 snapshot):**

| ZIP | City | Total parcels | Residential | Status |
|-----|------|---------------|-------------|--------|
| 98020 | Edmonds | 1,602 | 1,483 | beta-onboarding-target |
| 98026 | Edmonds (north) | 2,144 | 1,963 | beta-onboarding-target |
| 98290 | Snohomish/Lake Stevens | 4,676 | 3,966 | live (pilot, May 10 seed) |

**To-build modules (Phase 1 — to ship 98020/98026 launch):**

1. `scripts/build_snohomish_owners.py` — downloads Parcels feature service via paginated REST queries, normalizes to seed JSON. Mirrors `build_kc_owners.py` pattern. Output: `data/seeds/wa-snohomish-{zip}-owners.json`.
2. `backend/harvesters/snohomish_daily_report.py` — downloads daily New Case Report PDF, parses table, writes to `raw_signals_v3` with case_type/decedent/case_number. Mirrors `kc_superior_court.py` shape.
3. `backend/tasks/snohomish_daily_autofill.py` — background task that ticks once daily, calls the harvester for yesterday's new cases. Mirrors KC's autofill pattern.
4. SNO_ZIP_TO_CITY map additions in `backend/api/admin.py` for 98020 → "Edmonds", 98026 → "Edmonds".

The downstream pipeline (matcher, canonicalize, briefings, dossier) is already source-agnostic — no changes needed.

**98290 bonus:** Once the harvester writes Snohomish probate/divorce signals into `raw_signals_v3`, the matcher will pick them up against existing 98290 parcels' canonicalized owners. 98290 gains Tier 1 leads automatically alongside the new ZIPs.

**Already-existing Snohomish infrastructure (do not rebuild):**

- `backend/harvesters/snohomish_scopi.py` — per-parcel sales-history scraper. Used by `snohomish_tenure_autofill.py` to backfill the long-tail of pre-5-year transfers (Snohomish's bulk Sales Excel only goes back 5 years; SCOPI provides full history for tenure classification). Keep as-is.
- `data/seeds/wa-snohomish-98290-owners.json` — pilot seed, one-off (no committed builder). Will be regenerated cleanly via the new `build_snohomish_owners.py` when ready.

---

## Generic WA county onboarding template (future expansion beyond Snohomish)

The Snohomish work generalizes. The pattern for adding any non-KC WA county:

1. **Find the county's ArcGIS Open Data Portal.** Most counties publish at `{county}-county-open-data-portal-{org}.hub.arcgis.com` or via a county-branded ArcGIS Hub. Pull the DCAT catalog at `/api/feed/dcat-us/1.1` for the full dataset list. Find "Parcels" (sometimes "Tax Parcels" or "Cadastral").
2. **Find the County Clerk's Daily New Case Reports.** Search `{county} county clerk daily new case report site:gov`. Most publish PDFs to their DocumentCenter. Verify probate (EST/WLL/TRS/GDN), divorce (DIC/DIN), and tax warrant (TAXDOR) case types are included.
3. **Add `{COUNTY}_ZIP_TO_CITY` map** in `backend/api/admin.py` with the county's ZIPs.
4. **Add `WA_{COUNTY}` market_key** if not already present.
5. **Build the seed file** via the county's Parcels feature service (paginated REST query, max 2000/page).
6. **Run orchestrator** the same as KC.

Counties currently planned for post-Snohomish expansion: Pierce, Thurston, Whatcom, Kitsap (the major non-KC Puget Sound counties).

---


## Where things live

### Code

- **Repo:** https://github.com/jeremyseglem/sellersignal-v3 (private)
- **Branches:** only `main`. Direct commits, no PR workflow.
- **Local clone path for Claude sessions:** `/tmp/sellersignal-v3/` (ephemeral — re-clone each session)

### Production

- **Frontend + backend:** Railway project `stellar-connection`. Auto-deploys on push to main. ~60-90s build time.
- **Production URL:** https://sellersignal.co
- **Backend serves frontend:** FastAPI serves `frontend/dist/` as static files. No separate frontend host.

### Database

- **Supabase project:** `eeqsbvizgpuehphiaslo`
- **Dashboard:** https://supabase.com/dashboard/project/eeqsbvizgpuehphiaslo
- **Schema migrations:** `schema/001_*.sql` through `schema/011_lead_interactions.sql`. Migration 011 was applied April 2026 for Slice C's Lead Memory feature.

### External APIs

- **SerpAPI** — v2-heritage web search; NOT used in the primary harvester pipeline
- **Anthropic API** — Haiku 4.5 for owner-name canonicalization; Sonnet/Opus for Deep Signal narrative generation only
- **Google Maps + Street View** — parcel cards show satellite/street view photos
- **Stripe** — billing carried from v1 (not yet wired to V3 territory claims for beta)
- **Lob** — mail letters (NOT wired for beta, placeholder only)

### Domains

- `sellersignal.co` (production custom domain via Railway)

---

## Access keys (real — treat as secrets)

These values are not committed to the repo. Pull them from Jeremy's 1Password or Railway env vars at the start of each session.

```
ADMIN_KEY            — X-Admin-Key header for admin endpoints
                       (from Railway env: ADMIN_KEY)
GITHUB_PAT           — fine-grained PAT for git push from Claude container
                       (from 1Password: "SellerSignal GitHub PAT")
SUPABASE_URL         — https://eeqsbvizgpuehphiaslo.supabase.co
SUPABASE_SERVICE_KEY — Supabase service role key
                       (from Railway env: SUPABASE_SERVICE_KEY)
SUPABASE_ANON_KEY    — public anon key (from Railway env: SUPABASE_ANON_KEY)
ANTHROPIC_API_KEY    — Haiku 4.5 + Sonnet/Opus access
                       (from Railway env: ANTHROPIC_API_KEY)
```

**Standard git push pattern** (substitute your PAT):
```bash
git push https://jeremyseglem:${GITHUB_PAT}@github.com/jeremyseglem/sellersignal-v3.git main
```

**Standard admin curl pattern** (substitute your ADMIN_KEY):
```bash
curl -s -H "X-Admin-Key: ${ADMIN_KEY}" "https://sellersignal.co/api/coverage"
```

---

## Tech stack

- **Backend:** Python 3.11, FastAPI, uvicorn (Procfile: `uvicorn backend.main:app`)
- **Frontend:** React 18 + Vite + Leaflet (built into `frontend/dist/`, committed)
- **Database:** Supabase (Postgres). All tables `*_v3` to distinguish from archived v1 data.
- **Auth:** Supabase Auth (magic-link email)
- **Payments:** Stripe (carried from v1, not yet wired to V3 beta)
- **Background tasks:** Ten asyncio tasks in `backend/tasks/`:
  - `autofill.py` — case-parties scraper
  - `obit_autofill.py` — multi-source obit harvester
  - `treasury_autofill.py` — tax-foreclosure harvester
  - `rematch_autofill.py` — drains unmatched-signals queue
  - `snohomish_tenure_autofill.py` — SCOPI per-parcel detail page scraper (idle by default)
  - `canonicalize_autofill.py` — completes deferred / partial owner_canonical_v3 work
  - `snohomish_daily_autofill.py` — daily new-case-report PDF harvester (24h tick)
  - `renewal_notifier.py` — Stripe-renewal reminder emails at T-30/T-7/T-1
  - `letter_scheduler.py` — 6h tick; submits scheduled letters past `stannp_send_date` to Stannp
  - `letter_digest.py` — hourly tick; fires 07:00 America/Denver with prior-24h letter-event summary email per agent
- **Hosting:** Railway, single service, auto-deploy on push

---

## Code architecture

### Backend (`backend/`)

| Module | Responsibility |
|--------|----------------|
| `main.py` | FastAPI app, lifespan handler, route mounting |
| `api/admin.py` | Admin endpoints — registers, ingest, seed, classify, band, publish, onboard-zip orchestrator endpoint, canonicalize, KC_ZIP_TO_CITY map |
| `api/briefings.py` | Per-ZIP briefing endpoint — produces call_now/build_now/holds payload |
| `api/parcels.py` | Per-PIN parcel detail endpoint — feeds the dossier |
| `api/coverage.py` | Public coverage endpoint with `include_in_development` flag |
| `api/harvest.py` | All harvester admin + diagnostic endpoints (~3K lines) |
| `api/deep_signal.py` | Per-parcel "deep dive" — Claude synthesis from web research |
| `api/lead_interactions.py` | Lead Memory POST/GET |
| `api/auth.py` | `user_from_authorization` JWT decoder |
| `api/onboard.py` | Beta territory claim (bypasses Stripe) |
| `api/zip_gate.py` | Per-user ZIP authorization |
| `harvesters/kc_superior_court.py` | Pulls case listings |
| `harvesters/kc_court_participants.py` | Parties tab scraper |
| `harvesters/kc_treasury.py` | Tax foreclosure harvester |
| `harvesters/obituary.py` | Multi-source obit harvester |
| `harvesters/matcher.py` | Links raw_signals to parcels by canonicalized owner name |
| `selection/weekly_selector.py` | Eligibility-contract selector (Rule 6) |
| `tasks/zip_onboarding.py` | **Canonical orchestrator for adding a ZIP** |
| `tasks/canonicalize_autofill.py` | Background task — completes deferred/partial owner_canonical_v3 work via Priority 1 (orchestrator-flagged) + Priority 2 (round-robin). Uses the same _CANONICALIZE_LOCK as the orchestrator. |
| `tasks/autofill.py` | Background case-parties tick |
| `tasks/obit_autofill.py` | Background obit ticks |
| `tasks/treasury_autofill.py` | Background treasury ticks |
| `ingest/zip_builder.py` | The cmd_* functions the orchestrator calls (register, seed, classify, band, publish) |
| `ingest/owner_canonicalizer.py` | Haiku 4.5 owner-name parser |
| `ingest/backfill_owner_canonical.py` | `backfill_zip` function the orchestrator's canonicalize step calls |
| `ingest/arcgis.py` | ArcGIS ingest (used for one-off address backfill, NOT in onboard-zip flow) |

### Frontend (`frontend/src/`)

| Module | Responsibility |
|--------|----------------|
| `pages/BriefingPage.jsx` | Main agent screen — header oracle, action list, pipeline, map |
| `pages/TerritoriesPage.jsx` | Dashboard showing claimed ZIPs as cards |
| `pages/CoveragePage.jsx` | Public "what ZIPs are covered" page |
| `components/ParcelDossierV2.jsx` | 5-section dossier (WHY/NEXT STEP/CONTACT/WHAT TO SAY/EVIDENCE), archetype-driven |
| `components/ParcelDossier.jsx` | Old 2,352-line dossier — KEPT AS REVERT PATH, schedule for deletion |
| `components/MapPanel.jsx` | Leaflet map |
| `components/briefing/*.jsx` | Header oracle, lead rows, action list, pipeline list, map explore panel, claim modal |
| `lib/archetypePlaybooks.js` | 5 archetypes + general fallback |
| `lib/AuthContext.jsx`, `lib/supabase.js` | Auth wiring |
| `styles/tokens.css` | "The Estate" design system (warm ivory, dark nav, gold; Playfair / Source Serif / DM Sans) |

### Schema (`schema/`)

24 SQL migration files applied sequentially to the Supabase project. Most recent: `024_geocode_skipped.sql` (2026-05-21) adds `parcels_v3.geocode_skipped BOOLEAN NOT NULL DEFAULT FALSE` plus a partial index for the geometry backfill query path — lets stuck PINs (no record in source ArcGIS) be flagged and skipped on subsequent backfill runs instead of re-fetching the same set every call.

---

## Standard ops

### Starting a fresh session
```bash
git clone https://jeremyseglem:GITHUB_PAT@github.com/jeremyseglem/sellersignal-v3.git /tmp/sellersignal-v3
cd /tmp/sellersignal-v3
curl -s https://sellersignal.co/api/health  # confirm prod is up
curl -s -H "X-Admin-Key: $ADMIN" "https://sellersignal.co/api/coverage" | python3 -m json.tool | head
```

### Deploying a code change
1. Edit files in `/tmp/sellersignal-v3/`
2. Syntax check: `python3 -c "import ast; ast.parse(open('FILE.py').read())"`
3. Build frontend if changed: `cd frontend && ./node_modules/.bin/vite build`
4. Commit: `git add -A && git commit -m "..."`
5. Push: `git push https://jeremyseglem:GITHUB_PAT@github.com/jeremyseglem/sellersignal-v3.git main`
6. Wait 60-90s for Railway redeploy
7. Verify: hit an admin endpoint to confirm

### Adding a new ZIP
Documented above under "The canonical onboarding pipeline." Summary:
1. Build seed file: `TARGET_ZIP={zip} KC_DATA=/tmp/kc-data python3 scripts/build_kc_owners.py`
2. Commit seed file
3. Add entry to `KC_ZIP_TO_CITY` in `backend/api/admin.py` if not present
4. Push (Railway deploys)
5. `POST /api/admin/onboard-zip/{zip}?city=City`
6. Poll `GET /api/admin/onboard-status/{zip}` until state == `live_canonicalize_pending` or `completed`
7. Repeat for next ZIP (sequential, NOT parallel)

### Most-used admin endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/coverage` | Live ZIPs (add `?include_in_development=true` for all) |
| `POST /api/admin/onboard-zip/{zip}?city=X` | Trigger orchestrator |
| `GET /api/admin/onboard-status/{zip}` | Poll orchestrator state |
| `POST /api/admin/coverage-meta/{zip}?city=X` | Update display metadata (city/state/market_key) on an existing live ZIP. Repair tool for rows stuck with wrong values from earlier curl misformats. |
| `GET /api/harvest/canonicalize-autofill-status` | Background canon-autofill task state |
| `POST /api/harvest/canonicalize-autofill-pause` | Pause canon-autofill |
| `POST /api/harvest/canonicalize-autofill-resume` | Resume canon-autofill + clear backoff |
| `GET /api/harvest/diag/parties-count` | case_parties_v3 row stats |
| `GET /api/harvest/diag/recent-real-parties?limit=N` | Newest real participants vs sentinels |
| `GET /api/harvest/autofill-status` | Case-parties background autofill state |
| `POST /api/harvest/backfill-parties?confirm=true&zip_code=X&limit=N` | Trigger parties scrape |
| `POST /api/harvest/clear-sentinel-parties?confirm=true` | Wipe sentinel rows (DESTRUCTIVE) |
| `POST /api/harvest/rematch-reset-scoped?source_type=X&signal_type=Y&confirm=true` | **(2026-05-21)** Reset matched_at on a scoped slice of signals. Safer than the global `/rematch-reset`; touches only signals matching the source+type filter. Used today for the Snohomish probate re-run after the prop_type fix. |
| `POST /api/admin/geometry/{zip}?limit=500` | Geometry backfill. Auto-resolves market_key from `zip_coverage_v3` (works for KC and Snohomish without query param). Call repeatedly until `missing_geom=0` or matches the `not_found` floor. |
| `POST /api/admin/reingest-property-details/{zip}?market_key=X` | Backfills `owner_city`, `owner_state`, `is_absentee`, `is_out_of_state`, `prop_type`, `acres`, `*_value` from live ArcGIS. **Side effect to know:** adds new parcels that aren't in the seed JSON (live source may have more parcels for SITUSZIP=X than the seed captured). Required for absentee bucket to populate. |
| `POST /api/coverage/refresh-counts?confirm=true&zip_code=X` | Recomputes `zip_coverage_v3.contact_now_*` bucket counts. Run after any operation that adds/removes parcels or changes bucket-deciding fields (owner_state, prop_type). |
| `GET /api/harvest/admin/zip-quality-score/{zip}` | Onboarding validator with 7+ checks including `prop_type_eligibility_pct`. Will catch the 98290-style failure where every parcel fails the matcher's eligibility filter. |

---

## Build journal (most recent at top)

### 2026-07-29 — FL_PALM_BEACH launched: Palm Beach County wave 1 (8 ZIPs, ~90.6k parcels)

Tenth market, first Florida market — the supply-side expansion Jeremy called before demand-side integration. Recon → build → live in one session.

**Recon findings (drive the build):**
- **Parcels: best single-source layer of any market to date.** PBC Property Appraiser hosted FeatureServer `services1.arcgis.com/ZWOoUZbtaYePLlPw/.../Parcels_and_Property_Details_WebMercator/FeatureServer/0` carries OWNER_NAME1/2, full mailing address+state, SALE_DATE (98%+ coverage), TOTAL_MARKET, PROPERTY_USE, CONDO flag, YRBLT, and polygon geometry (outSR=4326 + returnCentroid supported) in ONE layer. No KC-style owner stripping. CONFID_FLG=Y statutory redactions ~0.1%.
- **No situs-ZIP column** (ZIP1/ZIP2 are MAILING zips) — per-ZIP filtering is envelope spatial query + exact ZCTA point-in-polygon (CT/MT pattern), polygons in `data/zip_polygons/fl.json` (TIGERweb ZCTA).
- **Recorder open:** `erec.mypalmbeachclerk.com` = Landmark Web 1.5.103 (Cott/Pioneer), no captcha, no account wall. Adapter is standard follow-up work. FL instruments to target at build: deeds, lis pendens, recorded death certificates, Notice of Trust (F.S. 736.05055 — filed with clerk on settlor's death; verify PBC doc-type list at build).
- **Court dockets soft-blocked from datacenter:** `applications.mypalmbeachclerk.com` (eCaseView probate/family) TLS-resets our egress — Travis shape. JEREMY BROWSER CHECK PENDING: does eCaseView guest search work in a browser, searchable by date range + case type? If yes, Montana pattern (GitHub Actions + headless browser) likely clears it and PBC goes full-stack.

**Shipped (commits 3a139a7 + follow-up fix):**
- `scripts/build_pbc_owners.py` — envelope query + ZCTA PIP; prop_type R (single family/townhouse/multifam<5/mobile) and K (condominium/co-op or CONDO=YES), else raw-use-truncated (matcher's eligibility filter rejects downstream, correctly); absentee via mailing state != FL or mailing city outside per-ZIP locality set; lat/lng centroids ride in at seed (no geometry backfill); 80% address gate.
- `data/zip_polygons/fl.json` — 8 ZCTA features.
- Wiring: PBC_ZIP_TO_CITY in admin.py; FL branches in seed-from-json dispatch, onboard-zip orchestrator (register-endpoint AND orchestrator-endpoint detect blocks — they are SEPARATE; first fire failed because only the register block was patched), both city fallback chains (+ MT added to the orchestrator chain, same Bellevue-default bug class), canon seed resolver; `FL_PALM_BEACH: FL` in _MARKET_STATE; TerritoryMap.jsx FL 'Palm Beach' metro + 'Florida' pill (also fixed the MT label gap: MT_GALLATIN→Bozeman, MT_FLATHEAD→Whitefish via MARKET_METRO_LABELS, TX far-flung pattern); dist rebuilt via build:safe.

**Onboarded sequentially via orchestrator, all 8 live, structural buckets at cap (trust/llc/absentee/tenure = 100 each), tenure coverage 98%+:**
```
33480 Palm Beach          11,142 parcels  (25% trust, 11% LLC — the wheelhouse)
33483 Delray Beach         9,078
33487 Boca Raton          12,374
33432 Boca Raton          11,626
33405 West Palm Beach      7,390
33408 North Palm Beach    12,408
33477 Jupiter             11,097
33410 Palm Beach Gardens  15,534
Total                     90,649
```
Canonicalize: 33480 ran inline; remaining 7 deferred to canonicalize_autofill (~2h/ZIP, off critical path — Contact-now precision improves as it drains).

**FL follow-ups (queued, in order):**
1. Jeremy: eCaseView browser check (decides full-stack vs recorder-plus).
2. Landmark recorder adapter (`fl_pbc_recorder`) + SOURCE_MARKET_SCOPE entry — deeds/lis pendens/death certs/notice of trust.
3. eCaseView probate+family harvester via Actions if browser check passes.
4. Wave 2 candidates: 33469 (Jupiter Island side), 33462 (Manalapan/Hypoluxo), 33435 (Ocean Ridge), 33486/33496 (Boca), 33418 (PGA National).

### 2026-07-29 — SESSION WRAP / next-chat handoff

Consolidated state after this session (details in the dated entries below). Opening a new chat for next steps.

**Shipped & working this session:**
- **Flat satellite map** (scuttled 3D Earth) — user-confirmed "loads well and works well." Esri imagery + street/place labels, pin per property, click-anywhere-on-parcel opens dossier. Do NOT reintroduce deck.gl 3D.
- **Recurring Railway OOM fixed at the source** — the rematch_autofill background task was loading a whole market's parcels (~300k rows) into memory every tick on the single worker. Now streams per-ZIP (~13k peak). The "Deploy Ran Out of Memory" emails should stop.
- **Arizona probate live: 131 leads across 24/25 Maricopa ZIPs** — new Superior Court docket harvester + county-wide decedent resolution against the 1.75M-row Assessor roll (matches by parcel identity, zero false positives). Daily cron. This is the recorder→docket template that transfers to any market with an open docket.
- **KC Superior Court harvester runnable** — login-wall fix + runner + daily workflow built; dry-run verified 503 signals (327 probate + 176 divorce) in 14 days.
- **Canon poisoned-retry fix** — API-failure fallback rows no longer freeze pins as unknown.

**Fleet health baseline:** 106 ZIPs clean — structural buckets full everywhere, geometry 99.95-100%. New-ZIP onboarding won't inherit debt.

**Open items — JEREMY'S SIDE:**
1. **KC_PORTAL_USER / KC_PORTAL_PASS as GitHub ACTIONS SECRETS** (repo Settings → Secrets → Actions — NOT Railway; the harvester runs in Actions). Then dispatch `kc-superior-court.yml` with `since_days=120 write=1` once → drains 3 months of KC probate + divorce across 34 ZIPs. Biggest remaining lead unlock.
2. **Key rotation** (admin key, GitHub PAT, KC portal password) — overdue, heavy session exposure. Do after backlogs drain.

**Open items — CLAUDE'S SIDE (next chat):**
- After KC secrets set: dispatch the KC backlog drain, then matcher + refresh-counts across 34 KC ZIPs.
- Apply `schema/033_parent_pin.sql` in Supabase dashboard (convenience-only), then re-run backfill-condos per ZIP for parent_pin writes.

**Tabled for discussion (do NOT build without explicit go):**
- **Probate/divorce bucket merge** — Jeremy wants them merged ("divorces so few, a separate tab looks silly"). BUT divorce only looked empty because the KC harvester was dead since April — the 14-day test pulled 176 divorces. Decision deferred until KC divorce volume is visible post-drain; if merged, label deliberately ("Life Events"/"Court Signals"), don't bury divorce.
- **Next territories / new markets** — Jeremy leaning toward expansion. Approach: docket-accessibility recon FIRST (Maricopa was the win, Texas the cautionary tale). Palm Beach FL likely open (Maricopa-style quick win); Hamptons, Nashville, Chicago North Shore, Boston, Fairfax VA, central NJ each need recon.

**Parked (genuinely blocked):**
- **Texas court dockets** — all three markets locked: Dallas Odyssey reCAPTCHA + attorney-only accounts, Travis Odyssey F5-blocked + tccsearch Cloudflare + re:SearchTX registration broken (Jeremy confirmed "won't even let me create an account"). TX stays recorder-only. Not worth forcing.

---

### 2026-07-29 — V4 map: scuttled 3D Earth for flat satellite (SHIPPED, user-confirmed working)

The Google photorealistic 3D ("Earth") map had an unfixable class of bug: MapLibre's flat layers (pins/streets/outlines at z=0) desynced per-frame from the deck.gl 3D terrain mesh, so overlays slid across the terrain on pan/zoom, AND terrain-draped layers lose the pick buffer so nothing was clickable. Three code-only fix attempts failed (invisible pins → black void → still-drifting). DECISION: scuttle 3D entirely — the requirement is "click any property, see details, pins visible," which a flat map delivers reliably and 3D fought at every turn.

**Shipped (`720323c`, `6a2387a`) — flat Esri satellite map, user-confirmed "loads well and works well":**
- Esri World_Imagery raster basemap (same rich imagery, flat — one projection, nothing drifts).
- Street/place names: satellite raster is imagery-only, so transparent Esri reference overlays on top — World_Transportation (roads) + World_Boundaries_and_Places (place names), above imagery / below pins.
- Native MapLibre circle pins, brightened with a dark contrast ring so they read over imagery; one pin per property.
- Click ANY property — the pin dot OR anywhere on the parcel body (queryRenderedFeatures on p-dots, else lng/lat point-in-polygon over the lot fabric) — opens the dossier / condo unit-list. Pure lng/lat on a flat map = always accurate.
- Per-parcel outlines DROPPED: every property has a pin, so outlines were redundant clutter. Lot fabric still loaded for click-anywhere resolution + the gold selected-parcel highlight.
- pitch locked to 0, dragRotate off — can't be tilted back into the broken 3D-style state.

**Rule:** do NOT reintroduce deck.gl 3D / Tile3DLayer / TerrainExtension into MapPanelV4. Flat satellite is the committed design.

### 2026-07-29 — Recurring OOM root-caused + fixed; fleet health baseline; AZ healed to 131

**OOM fix (commit `6a9d4ec`) — the recurring "Deploy Ran Out of Memory" crashes.** Root cause was NOT just the manual matcher calls: the rematch_autofill BACKGROUND task loaded an entire market's parcels (~300k rows AZ/KC) into one dict every tick on the single-worker instance. `run-matcher-market` had the same flaw. Both now stream per-ZIP (`_process_unmatched_streamed` + `_process_one(defer_mark=True)`): peak memory = one ZIP (~13k rows), ~20x reduction. Correctness preserved — signals marked matched only after checked against every ZIP in their market. Rule reaffirmed: never load a whole market's owners into memory on this instance.

**Fleet health baseline (106 ZIPs, 9 markets).** Structural buckets (trust/LLC/absentee/tenure) populated on ALL ZIPs — 0 zeroed. Geometry 99.95-100% fleet-wide (75219 condo gap closed). Court-signal state by market: WA_KING probate=2071 (divorce stale, awaiting portal creds), WA_SNOHOMISH=236, MT=122, CT=89, AZ=131. Gaps are all TX court-signal coverage (account-gated): TX_TRAVIS=0 (all 9 dark), TX_DALLAS=8 (recorder trickle), TX_COLLIN=2. Divorce built only in KC — known gap, not a regression.

**AZ healed:** all 25 Maricopa ZIPs refreshed post-drain — 131 probate across 24/25 (85054 genuinely has no resolved decedent). The 6 that read 0 were just un-refreshed after the match drain, not dark.

**Onboarding-readiness verdict:** live fleet is clean (structural + geometry complete), so new-ZIP onboarding won't inherit fleet debt. Remaining lead-volume gaps are the account-gated TX court dockets (Dallas + Travis recon done — both need a free portal account, KC-login pattern ready to wire) and KC divorce backlog (awaiting KC_PORTAL creds in Railway).

### 2026-07-28 — Maricopa probate docket harvester + county resolution (AZ: 0 → 104 court-grade probate leads)

Answered "why no probate in Arizona": the AZ market harvested county *recorders* (deeds) — probate *activity* lives in Superior Court *dockets* we'd never built. Built the docket harvester end to end, mirroring the MT enumeration pattern.

**Harvester** (`backend/harvesters/maricopa_probate_court.py`, `scripts/run_maricopa_probate.py`, `.github/workflows/maricopa-probate.yml`): enumerates `PB{year}-{seq}` on the Maricopa Superior Court probate docket (superiorcourt.maricopa.gov/docket/ProbateCourtCases — plain HTTP GET, the site "recaptcha" is chrome, not gating the search). Parses the party table (Party Name / Relationship / Sex / Attorney). **Critical classifier:** the PB prefix mixes decedent estates (Decedent + PR/Petitioner — our lead) AND guardianship/conservatorship (Ward/Conservator — NOT a seller signal, the weak commoditized segment). Only decedent estates emit signals; guardianships classified out. Petitioner-as-contact fallback for fresh estates (no_pr_yet). Daily 13:00 UTC cron, county-scoped cursor/skip/fail-loud from MT.

**County resolution — the accuracy fix (the important part).** AZ luxury real estate is overwhelmingly trust/LLC-titled ("NITCHMAN FAMILY TRUST"). The app matcher's 2-token name gate correctly rejects surname-only matches (no false positives — Jeremy's hard rule), so trust-owned estates matched ZERO despite 100 surname overlaps. Fix is NOT to loosen the gate — it's county resolution: `scripts/run_maricopa_probate.py` now resolves every decedent against the full **1,755,691-row** Maricopa Assessor owner roll (`build_maricopa_county_roll.py` → `lib_county_resolve.from_maricopa_roll`, requires surname + first given name — trust-only and wrong-first-name correctly rejected, verified). Attaches `resolved_parcels` + `county_resolution_ran` so the app matcher matches by PARCEL IDENTITY (dispatcher Layer 0), not fuzzy name. Roll cached weekly in the Action. `RERESOLVE=1` mode backfills resolution onto already-stored signals.

**Result:** 215 estate signals harvested (123 guardianships filtered), 116 resolved to county parcels, **73 matched with hits**, **104 probate Contact-Now leads across 15 live AZ ZIPs** (85251=17, 85260=14, 85254=13, 85255=9, 85250=8, 85258=7, 85016=7; 4 ZIPs still settling). AZ went from 0 court-grade probate to live. Zero false positives by construction.

**Reusable:** generic `POST /api/harvest/admin/run-matcher-market?market_key=X` endpoint (market-scoped owner load, avoids full-fleet load under contention). The whole pattern — docket harvest → decedent/guardianship classifier → county resolution → identity match — now transfers directly to Travis/Dallas/Collin (all same docket shape). This is the template that lifts the remaining Sun Belt territories.

**Ops note:** running `run-matcher-market` (full 25-ZIP owner load) in a tight loop wedged the single uvicorn worker → brief prod outage, recovered on redeploy, no data lost. Lesson: bulk owner-load endpoints run one ZIP at a time with spacing, never batched against the single worker. refresh-counts on large AZ ZIPs (15-19k parcels) takes ~20-90s each (full briefing rebuild) — patient, one at a time.

**Also this session:** KC Superior Court harvester restored (commit `c096254`) — login wall + form redesign since April fixed (login step via KC_PORTAL_USER/PASS env, form_token capture, filing-date range shape); verified 197 probate signals in a 10-day window vs 0 since April. **AWAITING: KC_PORTAL_USER/KC_PORTAL_PASS in Railway env to activate** — then drain 3-month backlog across 34 KC ZIPs. Canon poisoned-retry fix (`bbe3f8d`) — API-failure fallback rows no longer freeze pins. Fleet condo backfill + legacy re-seed + building-pin UX (earlier commits).

### 2026-07-24 — Full-fleet audit + fix pass: KC login wall, Snohomish source migration, 98036/98296 enrichment, topics dedupe, lot-polygon hardening

Fleet-wide diagnostic across all 106 live ZIPs (quality validator, per-source signal freshness, task health, lot-polygon state), followed by a fix pass. Findings and outcomes:

**P0 — KC Superior Court BLOCKED BY LOGIN WALL (unresolved, needs operator action).** No new KC probate/divorce signals since 2026-04-24/23. Root cause: KC moved the Records Access Portal behind account login — `/node/411` search 307s to `/user/login` ("Create new account" offered), case-detail nodes 404 unauthenticated. Explains both the 3-month harvest gap and the case-parties autofill health-gating itself (`search_rows_page1: 0`). Fix path: operator creates a portal account (check their T&C for automated-access language), creds go to Railway env vars, `build_session()` gains a login step. All 34 KC ZIPs are serving progressively stale probate/divorce inventory until this lands.

**Snohomish County retired both data sources; migrated (commits `a052b6a`+).** `snoco.org/proptax/` (SCOPI) now redirects to the Assessor homepage — every SCOPI tenure fetch fails ("VIEWSTATE not found"); replacement is a DNN app at `wa-snohomish.publicaccessnow.com` (not yet reverse-engineered). The attribute-rich `Parcels` FeatureServer is token-gated (499) — but the same data is public under `CADASTRAL__parcels_timezone` (same schema, original `SITUSTTYP` field spelling). Swapped the URL in all five sites (arcgis ingest, geometry_backfill, admin register default, map_data lot config, seed builder) with parse-side tolerance for both spellings. Verified: 98020 lot polygons 0 → 8,322.

**98036/98296 completed (were live with trust/llc/tenure buckets at ZERO).** Root cause chain: (a) tenure_years NULL on every parcel — and aging_trust/llc_long_hold/long_tenure all gate on tenure, so all three buckets zeroed; (b) seed builder's `SITUSZIP='{zip}'` equality misses ZIP+4 rows — original seeds were ~22% of the ZIP (2,812/12,812). Fixed WHERE to LIKE, rebuilt both seeds full-coverage from the new layer, joined tenure from the county's **Land Records bulk xlsx** (AGO item `30eb31ef...`, PIN → max(Sale1D/2D/3D)) at 97.7%/96.9% coverage, ran seed → reclassify → reband → refresh-counts. Buckets: 98036 trust/llc/tenure 0/0/0 → 100/100/100; 98296 → 100/72/100. SCOPI backlog collapsed 22,874 → 741 (dead-portal long tail — port the tenure scraper to PublicAccessNow or pause the task).

**topics-citations workflow fixed (commit before `a052b6a`).** Nightly cron failed on Postgres 21000 — duplicate `(source_type, document_ref)` rows in one upsert batch (TOPICS lists amended citations twice). Batch dedupe in `write_rows` keep-last. Verified live: wrote 59 signals (61 deduped to 59), freshness 7/13 → 7/22. NOTE: the other five recorder scripts share the same write shape without dedupe — latent.

**Dallas recorder is NOT broken — trailing by design.** `LAG_DAYS=10` because recordings post ~5-7 days behind; a green run on 7/23 wrote 122 signals through 7/13. Do not re-diagnose this as silent failure. Travis recorder remains hard-broken (portal soft-block, exit-1 on grid_rows=0) — own session needed. MT harvester is still diag-first scaffold (WAF blocks sandbox fingerprints) — own session needed.

**KC reingest sweep (20 ZIPs, ~173k rows, 0 failures).** All never-reingested KC ZIPs got fresh owner_state/prop_type/values. Verdict on the low absentee buckets: LEGITIMATE — clean data + bucket cascade leaves single digits (98008: 3 → 7 post-reingest; matches May's 98053/98074 result). Not missing leads. Side effect: reingest added parcels (98116 +~1.8k, 98144 +~2.2k) whose canon backfills via canon-autofill round-robin — validator canon % dips on reingested ZIPs until it catches up.

**Lot polygons: fleet warmed + partial-store hardening.** All 100 warmable ZIPs (AZ/CT/Collin/Travis/KC/Snohomish/Dallas) now persisted; MT has no lot source yet. Dallas GIS throttles concurrent crawls — warm it sequentially with spacing. Two map_data fixes: (1) stored partials under 50% of parcel count now top up missing pins instead of serving forever; exceptions fall back to stored instead of empty; (2) a `__complete__` marker row (JSONB sentinel geom) records crawl completion so legitimately low-coverage condo ZIPs (75219 Oak Lawn: true ceiling ~18%) don't re-crawl every deploy. Marker path verification pending next natural redeploy.

**Verified non-issues:** 06883 Weston zero probate matches is genuine base rate — PD50 Westport Probate Court explicitly covers Weston in the CT sweep set. CT probate autofill's 18 morning ReadTimeouts self-recovered.

**MT portal UNBLOCKED (probe workflow, 3 iterations — `mt-browser-probe.yml`).** The F5 TSPD bot defense blocks plain requests from sandbox AND Railway, but **Playwright Chromium in GitHub Actions clears it in ~5s**. Portal architecture confirmed: the "login" is anonymous — a `tenant` court select (option value = display name, e.g. `Gallatin District Court`) + hidden `loginAction` submit, NO credentials. Post-login lands on `mainMenu.do` (Dashboard). Key URLs: `judgmentOrderIndexSearch.do?searched=false` (date-range discovery — form fields `wrapper.orderStartDate`/`wrapper.orderEndDate` MM/DD/YYYY, per-field hidden `csrfToken`s, select2 widgets for order/status type), `civilCase.do?CourtCaseId=0` (case lookup), `partyCasesSearchResults.do` / `subjectSearchResults.do` (party search). Full form/menu HTML in the probe run artifacts (runs 30101582073, 30101967153, 30102355876). Remaining build is mechanical: precise form fill with the known names, parse results grid + case-detail LITIGANTS from captured HTML, wire an `mt-district.yml` Action mirroring the Dallas recorder pattern (write via REST with the batch dedupe from topics).

**MT probe v4 — case detail + litigants CONFIRMED (decisive).** `civilCase.do` renders full case detail anonymously. Probate case-type prefix is **DP**, case-number format `DP-{countycode}-{year}-{seq7}-{div}` (Gallatin countycode=16, e.g. `DP-16-2026-0000050-II`). The `civilCaseForm` takes `formatCaseType`/`formatCaseYear`/`formatCaseNumber` + hidden `retrieveAction` image submit; checking `reportBean.showLitigants` renders a **LITIGANTS** table with columns `LITIGANT | STATUS | ROLE | ATTORNEY | CASE RELATIONSHIP`. Verified live: DP-16-2026-0000050-II ("In the Matter of the...") returned `Olson, Brent M. — Applicant` (the PR/decision-maker) + `Olson, Andrew`. Sealed/juvenile cases return "You are not authorized to view cases with functional type Civil" and are simply skipped. **This means MT probate yields a named living decision-maker on day one** — better than Snohomish (PR appears weeks later) and no separate parties-tab drill like KC. Judgment Order Index Search (`judgmentOrderIndexSearch.do`) is the alternative date-sweep path: multi-select `wrapper.typesStrAr` (probate-relevant order-type IDs captured: Decree of Dissolution=10, plus the estate/appointment vocabulary), `wrapper.orderStartDate`/`orderEndDate` MM/DD/YYYY, hidden `retrieveAction`. Full case-detail + form HTML in run 30103158817 artifacts.

**MT harvest path (fully specified, ready to build):** anonymous tenant login (`tenant` select = court display name) → enumerate `DP-{countycode}-{year}-{seq}` ascending until a run of consecutive not-found/not-authorized (year exhausted) → for each live case parse the LITIGANTS table, take Applicant/Petitioner as the PR → write `source_type=mt_district_court, signal_type=probate` with document_ref=case number, decedent from case caption, PR name/role from litigants. County codes needed per court (Gallatin=16; capture Madison/Flathead codes on first run of each). Wire as `mt-district.yml` GitHub Action (TSPD requires real Chromium — mirror the probe's Playwright setup, NOT the requests-based recorder pattern) with topics-style batch dedupe on REST write.

**MT DISTRICT COURT HARVESTER BUILT + dry-run verified (2026-07-24).** Three new artifacts: parser in `backend/harvesters/mt_district_court.py` (`parse_case_detail` → Litigants table, `to_signal_row` → raw_signals_v3 shape), runner `scripts/run_mt_district_court.py` (Playwright DP-case enumeration per court, DB-cursor resume via max stored DP sequence, batch dedupe on write, miss-streak frontier stop), and workflow `.github/workflows/mt-district-court.yml` (dry-run default, daily 12:30 UTC cron writes, gallatin+flathead). Parser truth-tested against the captured DP-16-2026-0000050 case, then a live 40-case Gallatin **dry run** (run 30125407085) returned **33 clean probate signals** — each with decedent (matchable key) + PR/Applicant (contact) correctly separated, e.g. estate of Myrina Campbell → PR Andrew Kaufman; estate of Edwin Brainard → PR Paula Bentle. Gaps (sealed / non-DP sequences) are absorbed by the miss-streak. Two env bugs fixed during bring-up: DP-only cursor (a DR ref must not advance the probate walk) and set-but-empty numeric env coalescing (workflow passes `YEAR:''`). Madison is wired (MT_GALLATIN territory) but off by default. Attorney column is captured into raw_data.attorneys for the future intermediary-referral graph.

**MT LIVE WRITE COMPLETE — first probate leads in Jeremy's home market (2026-07-24, late).** Gallatin live write landed 79 signals; Flathead's first write returned 0 because FullCourt pins the tenant to the browser session — an in-session court switch silently keeps searching the first court. Fix (commit `aca5309`): fresh browser context per court + wait for `civilCaseForm` before fill. Verified by write run 30129079308: Flathead looked=120 → **78 signals written**, stopped at DP-2026-0000221 on miss-streak. Total `mt_district_court` signals: **157** (79 Gallatin + 78 Flathead), all 2026. Rematch autofill drained to 0 unmatched; refresh-counts run across all 6 MT ZIPs. **Final probate contact-now: 59715 Bozeman=10, 59718 Bozeman=9, 59714 Belgrade=9, 59937 Whitefish=6, 59730 Gallatin Gateway=1, 59716 Big Sky=0 — 35 total**, each with a named living PR on day one (no KC-style parties drill, no Snohomish-style no_pr_yet wait). Trust/LLC/absentee/tenure buckets at or near cap on all six. Daily cron (12:30 UTC) forces WRITE=1 via `github.event_name == 'schedule'` — verified in the workflow; manual dispatch stays dry-run by default. Optional follow-ups: 2025 backfill sweep (`year=2025` dispatch with write=1), enable madison.

**MT 2025 BACKFILL + THREE RUNNER HARDENING FIXES (2026-07-24 overnight → 07-25).** Final: **701 mt_district_court signals** (all matched, 0 unmatched), MT probate contact-now **113 total** — Whitefish 59937=32, Belgrade 59714=28, Bozeman 59715=26, Bozeman 59718=25, Gallatin Gateway 59730=1, Big Sky 59716=1. Up from 35 at the start of the night.

Four bugs found and fixed in sequence, each exposed by the previous fix:

1. **Cross-court cursor contamination (`48f3ad3`).** `start_sequence` and the skip pre-index filtered by year but not county code (document_ref = DP-{county}-{year}-{seq}: Gallatin=16, Flathead=15). Gallatin's refs (max seq 100) advanced Flathead's 2026 cursor to 101 — Flathead 2026 cases 1-100 were silently never enumerated. County code added to COURT_META (madison=None until first run); both cursor and skip index now county-scoped.
2. **No gap-recovery path (`a20a4ac`).** The cursor is 1+max-stored, so gaps BELOW it are unreachable. Added `FULL_SWEEP=1` env + workflow input: start at seq 1, rely on the county-scoped skip index. Recovery run 30131275247: Flathead 2026 seqs 1-100 → **78 signals**.
3. **Green run on total failure (`d31e9b8`).** A portal goto-timeout was swallowed by the per-court SWEEP ERR catch and the Action reported success on TOTAL looked=0. Now exits 1 when zero cases were looked at — same masking class as the Travis fix (f618403). Matters because the daily cron must alarm, not rot.
4. **Transient errors conflated with frontier evidence (`3bc6d5d`), then TSPD session budget (`a677603`).** Nav errors and TSPD tar-pit noparse pages ("Request Rejected", len=255) advanced miss_streak, so a flaky stretch falsely concluded "year exhausted" — Flathead 2025 died this way twice at seq 126 while the real frontier was 300+. Now: separate err_streak, retry each errored seq once, ABORT the court after 8 consecutive errors with cursor preserved (miss_streak untouched). Then added mid-court context recycling (`RECYCLE_EVERY=75`) after observing TSPD grants ~100 lookups per browser session.

**TSPD findings (operational knowledge for all MT runs):** F5 TSPD budgets are BOTH per-session (~100 lookups) AND per-IP — and after ~800 lookups across 7 runs in one night, the GitHub Actions egress range itself got flagged: a fresh run died in 16 lookups at the same wall. Sustained scraping needs spacing between runs, not just fresh contexts. The wall reads as `err:noparse len=255 title='Request Rejected'`.

**2025 backfill run ledger (all reconcile: 235 + 94 + 95 + 86 + 93 + 98 = 701):** Gallatin 2025 complete — 94 (seqs 1-126, run 30132488056) + 86 (101-217, run 30133894958), frontier reached on genuine miss-streak at ~217. Flathead 2025 — 95 (seqs 1-126, run 30133712836, Jeremy-dispatched after the first pass flaked to 0) + 93 (198-297ish... 126-297, run 30139246051) + 98 (through ~297, run 30139784019); **frontier NOT yet reached — cursor at seq ~297, walled by TSPD at 298-306 on two consecutive runs.** Note two of tonight's runs briefly overlapped in flight (dedupe held; avoid concurrent dispatches as practice).

**MADISON ENABLED (2026-07-25, `9e694ed`).** Probe run 30142829780 wrote **21 probate signals** (Madison 2026 seqs 2-23) and revealed county code **29** (refs DP-29-2026-...), now set in COURT_META. Madison is on the daily cron (`gallatin,flathead,madison`). Probe also exposed a second noparse shape: beyond-frontier sequences serve a FULL FullCourt 'Civil Case' page (len~42k, no litigants) — genuine frontier evidence, now classified `miss:emptycase`, distinct from TSPD walls (len<2000 / 'Request Rejected' → transient err). Madison 2026 is complete to frontier (~seq 23). All 21 matched; none in Big Sky's Madison-side parcels yet — Ennis/Virginia City decedents. Cron picks up future Big Sky-side filings automatically.

**KC CONDO SYSTEM + LEGACY RE-SEED (2026-07-27, commits `97cb80c`..`e664ad9`+).** Two-part fix for "map pins and property lines don't show for every property":

*Part 1 — condo backfill system.* KC's ArcGIS layer carries ONE record per condo complex (PIN = Major+'0000', with footprint); the per-unit PINs exist only in the bulk extract `Condo Complex and Units.zip` (EXTR_CondoUnit2.csv, ~115k units). New module `backend/ingest/kc_condo_backfill.py` + endpoint `POST /api/admin/backfill-condos/{zip}`: identifies condo units by extract membership, sets prop_type='K', pins units at the complex parcel centroid (never clobbers real geometry), writes parent_pin=Major+'0000' (defensive — migration 033 pending). Batched .in_() updates per complex; parcels select paginated past PostgREST's 1000-row cap. Ran across all KC ZIPs: **~29k condo units pinned**, every previously-"unpinnable" residual explained. May's 98053/98074 "true ceilings" were condos all along. Fleet geometry after: every KC ZIP 98.6-100% (residuals are genuine not-in-source PINs). Remaining map hole: Dallas 75219/75225 (~2.6k condo units — needs Dallas CAD source or geocode fallback).

*Part 2 — legacy seed gap.* The 10 oldest-cohort ZIPs (98004/05/06/07, 98033, 98040, 98052, 98105, 98112, 98199) were missing their condo units from parcels_v3 ENTIRELY (~21k units, incl. downtown Bellevue towers) — the early seed path excluded them. Rebuilt all 10 seeds with the current builder (100% address coverage), re-fired seed-from-json (upsert; seed-from-json now prefers wa-king-98004-owners.json over the legacy baseline), reclassify+reband, condo-backfill, geometry passes, refresh-counts. Parcel counts roughly doubled (98004 7,147→15,669; 98052→22,000; 98033→19,147). Structural buckets refreshed; **canon autofill is chewing the ~50k new owner names** — Contact-Now probate precision improves as it completes; consider a scoped KC rematch after canon so old signals can match the new condo owners.

*Prereqs/open from this work:* (1) apply `schema/033_parent_pin.sql` in Supabase dashboard, then re-run backfill-condos per ZIP to write parent_pin; (2) ~~building-pin UX~~ SHIPPED `1f251f6`+`61ebe48`: one pin per building with unit-count badge, tap opens Estate-styled unit list (category-sorted) → dossier; Earth-mode clicks route the same path; complex footprints (Major+0000) matched into lot crawls + self-healing top-up on completed ZIPs, served as unit property lines; parent derived from PIN so migration 033 is convenience-only; (3) ~~Dallas condo source~~ SOLVED `7823255`+: Dallas city layer collapses condo buildings into ACCT='MULTIPLE' polygons (no per-unit accounts, no parent linkage) — built the address-geocode fallback instead: `POST /api/admin/geocode-address-fallback/{zip}`, Census batch geocoder tier 1 (free; matched 99.8% in 75219) + Google Geocoding tier 2 for TIGER misses (Austin/75225 corridors; ~$10 one-time). Fleet-wide sweep pinned every remaining residual incl. Snohomish 98012. **FLEET FINAL: 1,049,784 parcels, ~40 missing (~100.0% pinned).** (4) prop-type reingest also ran across 23 KC ZIPs earlier in the session (owner_state/absentee/commercial codes).

**OPEN: Flathead 2025 tail — dispatch during MT daytime only.** Three manual dispatches at ~22:00-22:30 MT all died at the portal (select_option/goto timeouts, looked=0, failed loudly) while every 08:00-MT cron ran green — FullCourt has a nightly maintenance window, this was never purely TSPD. One `courts=flathead year=2025 max_cases=400` dispatch during US daytime finishes the year from cursor ~seq 297.

**PREVIOUSLY: Flathead 2025 tail.** Cursor at seq ~297; TSPD walled 298-306 across three runs (last attempt 30143177621 failed loudly at looked=0 — the guard working). One `courts=flathead year=2025 max_cases=400` dispatch after real cooldown (≥12h) walks from ~298; with the emptycase classifier, expect a clean genuine-frontier ending (~350-400, likely ~50-100 more signals). Then rematch drains automatically; run refresh-counts on the 6 MT ZIPs. Daily cron covers 2026 only and will not pick this up.

**MT cursor-contamination bug found + recovered (2026-07-24, later).** The 35-lead state above was incomplete: the resume cursor and skip pre-index filtered stored refs by year but NOT by county code, so Gallatin's refs (max seq 100) advanced Flathead's cursor to 101 — Flathead's 2026 cases 1–100 were never enumerated. Three commits: `48f3ad3` scopes cursor + skip index to `COURT_META` county codes (gallatin=16, flathead=15, madison=None until first run — None matches nothing, walk starts at 1, per-ref dedupe protects); `a20a4ac` adds `FULL_SWEEP=1` env/workflow input forcing the walk to start at seq 1 with the county-scoped skip index (gap recovery below the cursor — required because the fixed cursor alone starts at max+1 and never revisits holes); `d31e9b8` exits 1 when TOTAL looked=0 (a swallowed `Page.goto` timeout — TSPD tar-pit on one runner IP — had produced a green run on a total failure; same masking class as Travis `f618403`; retry on a fresh runner cleared it). Recovery run 30131275247: full sweep from seq 1, looked=125, **wrote 78 more Flathead signals** from the 1–100 gap. MT totals after recovery: **235 signals, 0 unmatched. Probate contact-now: 59718 Bozeman=11, 59714 Belgrade=11, 59715 Bozeman=10, 59937 Whitefish=9, 59730 Gallatin Gateway=1, 59716 Big Sky=0 — 40 total.** 2025 backfill dispatched (run 30132488056, gallatin+flathead, cap 400/court) — results to be journaled when it lands.

**MT harvest path fully proven (probe v4).** Enumerated a live Gallatin probate case end-to-end from an anonymous session via `civilCase.do` — form `civilCaseForm`, fields `formatCaseType`/`formatCaseYear`/`formatCaseNumber` (DP / 2026 / zero-padded 7-digit seq) + hidden `retrieveAction` image submit, with `reportBean.showLitigants` checked. Captured case `DP-16-2026-0000050-II` "In the Matter of the Estate of Andrew Olson", Case Subtype "Informal Intestate", filing date 03/20/2026, and the Litigants table with roles: **Applicant = Olson, Brent M.** (the PR / decision-maker) and **Decedent = Olson, Andrew**. This is the complete lead shape — decedent name for the parcel match, PR name for the pitch — from a no-credential session. Case-type prefix DP = District Probate. `formatCaseType` other-than-DP returns "You are not authorized to view cases with functional type Civil" (sequence 0000010 was a sealed/other-type case), so the harvester enumerates DP-year-sequence and skips unauthorized/not-found gaps. Two harvest strategies now both confirmed viable: (1) `judgmentOrderIndexSearch.do` date-range sweep (types `wrapper.typesStrAr`: Decree of Dissolution=10, Decree of Legal Separation=14, etc. for divorce; probate letters appear via case enumeration) filtered to a filing window; (2) DP case-number enumeration for probate estates. Enumeration is simpler and directly yields the Estate + PR shape — that's the primary path for the harvester build.

**Travis headed-mode ruled out (`travis-headed-probe.yml`).** The search box stays disabled under HEADED Chromium + xvfb, exactly as under headless — the tenant's bot check is IP/fingerprint-level, not headless detection. Dallas (same platform, same code) passes; Travis blocks. Remaining options: residential/ISP proxy for the Action, or lean on `tx_topics_citations` (statewide, county-resolves Travis when TCAD_ROLL is loaded) as Travis's probate channel.

**Still open after this session:** KC portal account (operator); Travis session; SCOPI port-or-pause decision; admin key + PAT rotation (both still live from July 13, heavy use today); MT lot-polygon source; canon catch-up on 98116/98144 (self-healing).

### 2026-07-22 (later) — Map fixes: every parcel visible + Earth load time

Two pre-existing map complaints from Jeremy, both diagnosed to hard causes.

**A. "Random smattering of dots" = a hard row cap, not randomness (commit `0def9ea`).** `/api/map/{zip}` defaulted to `limit=5000` and PostgREST returns rows unordered, so each load rendered an arbitrary 5,000-parcel slice. **81 of 100 territories exceeded it** — 85255 showed 21% of its parcels, 98103 25%, 98052 32%. Everything outside the slice was invisible AND unclickable, which is exactly what zooming in looked like. Fix: `slim=1` query param drops `address`/`owner_name`/`value` from the map payload (they're only needed on click, and the dossier endpoint already supplies them), and the row cap defaults to 30,000 when slim. Whole-ZIP response is 0.26MB gzipped vs 0.72MB for the OLD truncated one — every parcel now renders for less bytes than a quarter of them used to. Frontend requests `slim=1`; bundle `index-uzspGSuf.js` live. Verified: 85255 returns 24,041 parcels in 3.2s.

**B. Earth load time — the lot-polygon fabric, not the tiles (this commit + `schema/032`).** `/api/map/{zip}/lot-polygons` fetched lot geometry LIVE from county ArcGIS on every cache miss, 150 pins per request, paging the whole ZIP. Measured: 06883 21s/3.0MB, 98004 21s/5.4MB, **85255 55s/13.1MB** (one run hit a 60s timeout). The only cache was in-process, so every Railway redeploy threw it away and the next visitor paid the full crawl — and the V4 Earth layer waits on this fabric. Added `lot_polygons_v3` (zip_code, pin, geom JSONB, market_key, fetched_at; PK (zip_code,pin)). The endpoint now reads persisted geometry first, self-warms on a miss (fetch → serve → store), and **degrades to the exact old live path if the migration isn't applied** — same defensive pattern as `024_geocode_skipped`. Verified post-deploy pre-migration: 06883 returns 3,850 polygons, `source: arcgis`, no errors.

Also parallelized the deck.gl dynamic import with the earth-config fetch (they were serial; ~600KB of chunks loaded only after the config round-trip).

**⚠️ OPEN OPS STEP — `schema/032_lot_polygons.sql` is NOT yet applied.** Claude has no DDL path (service key gives PostgREST access only, and there's no SQL-exec endpoint). Jeremy must run it in the Supabase SQL editor. Until then the code is live and safe but still crawls ArcGIS. After applying:
1. Warm each ZIP once — `curl -H "X-Admin-Key: $ADMIN" https://sellersignal.co/api/map/{zip}/lot-polygons` per ZIP (self-stores; expect 20-55s the first time, ~1s after).
2. Spot-check that a second call returns `"source": "db"`.


### 2026-07-22 — PRODUCTION OUTAGE: all 104 territories 500'd (h2 pool) + CT dossier 404 (slash PINs)

**Symptom (Jeremy):** "api error 500 on a number of territories", map pins missing everywhere, clicking a lead zoomed the map but opened no dossier.

**Outage root cause — postgrest hardcodes HTTP/2 (commit `fad8edc`).** `postgrest==0.17.2`'s `SyncPostgrestClient.create_session` hardcodes `http2=True`. `backend/api/db.py` returns ONE `@lru_cache`'d client, so every API request handler AND all 7 background tasks multiplexed over a SINGLE HTTP/2 connection to Supabase. When that connection went bad (stream exhaustion under task load, or a server GOAWAY), every subsequent request through the shared client failed — `ConnectionTerminated error_code:1/9`, `Invalid input StreamInputs.SEND_HEADERS in state 5`. Briefings, map, and parcel endpoints all 500'd together because they share the client.

This is the true mechanism behind Active Issue #11 ("background-task contention on Supabase HTTP/2 stream pool"), which had been treated as intermittent flakiness for two months. It became constant after the platform grew to 104 ZIPs + a 7th background task (ct_probate_autofill).

**Fix:** `_force_http1_pool()` in `backend/api/db.py` monkeypatches `create_session` to `http2=False` with an explicit `httpx.Limits` pool (40 max / 20 keepalive / 30s expiry), applied before `create_client`. HTTP/1.1 gives httpx independent pooled connections — a broken connection fails ONE request instead of poisoning the process. Verified against the real installed library before shipping (patch applies, session constructs, transport is `HTTPTransport`). Pure transport change; PostgREST semantics identical.

**Verification:** swept all 104 live territories → 104/104 HTTP 200. Then RESUMED canonicalize_autofill (paused as a band-aid during triage) and re-tested under that load — briefings stayed 200. That's the real proof: task storms no longer take down the API.

**Second, unrelated bug — CT dossier 404 (commit `f2392f0`).** CT parcel PINs contain slashes (`50580-31/11/353`, `33620-07-1216/S`). Starlette decodes `%2F` before routing, so the single-segment `@router.get("/{pin}")` never matched and returned a bare routing 404 — the dossier never opened in ANY of the 9 CT territories. KC/AZ/TX PINs have no slashes, which is why the bug was CT-only and invisible until CT launched. Fix: `/{pin:path}` converter, plus explicit delegation for `/{pin}/why` (the greedy `:path` route would otherwise swallow it) — which incidentally makes `/why` work for slash PINs for the first time.

Verified post-deploy: dossier + why = 200 on all 6 CT ZIPs with leads (06830/06840/06880/06897/06883/06807) and regression-clean on 98004, 98116, 98036, 85258, 75219, 78703.

**Ops note — Railway deploy lag.** `f2392f0` sat undeployed for ~15 min while `fad8edc` was already live. Diagnosed with a clean discriminator: a single-segment unknown pin returns the HANDLER 404 (`Parcel X not found`) while a multi-segment path returns the ROUTING 404 (`Not Found`). Use that pattern to tell "not deployed" from "broken" instead of guessing. (Precedent: 2026-05-19/20 Railway webhook rate-limiting silently skipped commits.)

**Lesson.** Two months of intermittent 500s, auth retries, and "contention" workarounds were all one hardcoded `http2=True` in a dependency. When a failure mode recurs across unrelated subsystems (auth, briefings, canon, matcher) the shared substrate is the suspect, not each subsystem.


### 2026-07-21 — Sun Belt signal diagnosis: Travis recorder soft-blocked; Maricopa name pollution; the recorder-vs-docket ceiling

**Why:** 49 Sun Belt territories (AZ_MARICOPA 25, TX_TRAVIS 9, TX_DALLAS 10, TX_COLLIN 5) across ~520K parcels were producing 21 court-derived leads combined, vs WA_KING's 2,477 and CT's 78. Diagnosis pass across all four.

**Travis: the recorder is DEAD and cannot be fixed by selector work.** Sequence of findings (6 probe runs via `tx-browser-probe`, all DOM facts in the workflow history):
1. Daily Action reported `success` while logging `UI_DRIVE: date inputs not found` on every chunk then `WROTE 0 signals` — silent failure, unknown duration.
2. Travis migrated its date control to a react-downshift PRESET LIST (`#date-range-select`, options `date-range-select-listbox-option-N`: 1=Last 24 Hours, 2=Last 3 Days, 3=Last 1 Week ... 8=Last 1 Year). No fillable date inputs exist anymore. Fixed the driver to operate the combobox (`TRAVIS_PRESET_OPTION`, default 3) and rewrote the runner to do ONE preset sweep with client-side `recorded_date` filtering instead of incompatible per-day chunking.
3. Still 0 rows. Post-submit URL never left the home page.
4. **Root cause: the tenant soft-blocks automated browsers.** `#basicSearchInputBox` renders `disabled: true` and stays disabled for 60s+ (polled 0/5/10/15/20/30/45/60s), `readyState: complete`, NO Cloudflare challenge text, NO loading state, department react-select already on "Land Records". The Search button is likewise `disabled`. Navigating `/results?...` directly fires **zero** backend API calls — the SPA never dispatches a search. A rendered-but-inert form is the signature of a soft block, not a markup change.
5. Made the runner **exit 1 on zero grid rows** so the Action goes red instead of green. The green checkmark is what hid this.

**Travis path forward: NOT the recorder.** Options are (a) residential-proxy/stealth automation — fragile cat-and-mouse, or (b) **Travis County probate court dockets**, which is the structural fix already on the roadmap and yields richer court-tier signals than deed instruments. (b) is the recommendation.

**Maricopa: name pollution (fixed, draining).** Decedent names carried recorder doc-code/instrument junk into `party_names` (e.g. `"PB PB 2026~-0053797 ALFRED MOSTARDO"` → normalized `"PB PB ALFRED MOSTARDO"` → never matches a parcel owner). Robust stripper + one-off repair endpoint for stored rows shipped (`784cd4b`, `8afbf92`, `308e60e`); also fixed `rematch_autofill` misreading PostgREST's omitted `count` under load as zero-pending (`e0d278a`), which had idled the 1,033 reset signals. **Hit rate 14.0% → 47.4%.** Residual junk shape observed and NOT yet handled: `"PP LODG : OF O TAY SIDNEY PAUL MULHERIN"` — "PP"/"LODG" aren't in the junk-token set. Second stripper pass + repair once the drain settles; measure how many remaining zero-hits are this shape vs legitimately unmatched.

**The structural ceiling (applies to all four Sun Belt markets).** Lifetime signal volumes: Dallas 625, Maricopa 1,033, Collin 125 — vs KC's 8,846. Recorders index DEED instruments (affidavits of death, TODs); probate ACTIVITY lives in court dockets. CT proved the delta in one day: Greenwich's deed recorder yielded 53 leads over a month; the statewide probate court service yielded 78 in an afternoon. **Every Sun Belt county has a probate court with public docket search** (Maricopa Superior Court case lookup; Dallas County probate courts; Travis/Collin on Odyssey-style portals). Recon each — captcha-gating varies by deployment. This is the highest-leverage remaining build: it lifts 49 territories at once AND is Travis's unblock.

**Recon order recommended:** Maricopa Superior Court (largest market) → Travis County (also unblocks the dead recorder) → Dallas County → Collin.


### 2026-07-18 (later) — CT statewide probate harvester live: probate leads across all 9 CT territories

**The unlock:** ctprobate.gov exposes a statewide public JSON case-lookup service — no captcha, no auth (`/services/case-lookup?caseTypeCode=1&districtNum=PDxx&status=2&nameLast=<prefix>`). Probate in CT files with the state's probate district courts, NOT town clerks — so the per-town recorder fragmentation that blocks deed-level signals is irrelevant for probate. One adapter covers every CT territory including towns whose parcels aren't live yet (Darien).

Service mechanics (recon-verified): results hard-cap at 1000 rows oldest-first; every date/sort param is ignored; but `nameLast` is a PREFIX match returning complete slices under the cap. Harvest strategy: per-district A-Z prefix sweep, split any capped slice one letter deeper, filter client-side on dateFiled. Districts wired: PD54 Greenwich, PD52 Darien–New Canaan, PD50 Westport/Weston, PD51 Norwalk–Wilton.

**Shipped:** `backend/harvesters/ct_probate_courts.py` (source_type `ct_probate_courts`, decedent-tier signals, `raw_data.case_id` persisted on every signal for future fiduciary detail-enrichment); orchestrator registry key `ct_probate`; matcher `SOURCE_MARKET_SCOPE` entry → CT_FAIRFIELD; `backend/tasks/ct_probate_autofill.py` (24h tick, 10-day lookback, env prefix `CTPROBATE_`); admin endpoints `/api/harvest/ct-probate-autofill-{status,pause,resume,trigger}`; lifespan + shutdown-cancel wiring. Truth-tested locally against the live service before deploy.

**First production run (60-day window):** ~202 signals harvested, rematch_autofill drained the queue in-process, 22 parcel matches written. Post refresh-counts, CT probate buckets: 06830=15, 06831=29, 06807=10, 06870=7, 06878=4, 06840=5, 06880=6, 06897=2, 06883=0 (Weston small + newest). Greenwich cluster totals rose above the recorder-only baseline — the statewide feed catches filings the deed-side recorder never saw.

**Open follow-ups:**
- **Fiduciary tier:** search API returns the DECEDENT only; leads are `no_pr_yet` shape. The case-detail surface (executor/administrator names → family_pr_identified) wasn't findable from the container (site JS bundles blocked). Jeremy to click into a case in his browser and report the URL — that reveals the detail endpoint. `raw_data.case_id` on every signal is the join key when it lands.
- **Trusts case type:** the service also exposes caseTypeCode=2 (Trusts) per district — deliberate follow-up pending Jeremy's call on mapping trust FILINGS into the signal taxonomy.
- **CT divorce:** jud.ct.gov Superior Court civil/family lookup returns 503 to datacenter IPs (likely IP-class blocking, not outage). Jeremy to verify it loads in a residential browser; if yes, it's a proxy/fetch-strategy question.
- **Older sibling harvesters:** the per-town recorder roadmap (RECORDhub first) is now SECOND priority — it only gates deed-level signals (lis pendens, transfers), not probate.

### 2026-07-18 — CT Gold Coast parcels-first: 06840, 06880, 06897, 06883 live (Darien deferred)

Four Fairfield County towns live, all fully loaded day one (CT seeds carry tenure + mailing state inline): **New Canaan 06840** (7,192 parcels), **Westport 06880** (9,893), **Wilton 06897** (6,305) — each trust=100 llc=100 absentee=100 tenure=100 at cap; **Weston 06883** (3,986) trust=66 llc=43 absentee=82 tenure=100. Geometry 100% (centroids ride in at seed). 100 → 104 live territories.

Builder changes (commit `ee1…`): `build_ct_owners.py` now has a `_TOWN_CONFIG` map (per-town ZIP_CITY + local mail-city set for absentee logic) and scopes the ZCTA spatial join to the current town's own ZIPs (with all towns' polygons in ct.json, border parcels matched neighbors' ZCTAs and KeyError'd; they now fall to unzoned like the original Greenwich build). Five ZCTA polygons appended to `data/zip_polygons/ct.json` from the OpenDataDE census GeoJSON.

**Darien 06820 deferred:** the town withholds situs addresses from BOTH statewide layer vintages (2023 `Location` empty; 2024 `Location_1` populated on 10 of 7,670 rows). No VGSI tenant; town GIS is MapGeo (`darienct.mapgeo.io`) — needs its own recon (MapGeo internal API or the town assessor's online DB) before a seed can pass the 80% address gate. Note the 2024 CAMA layer (`Connecticut_CAMA_and_Parcel_Layer_2024`) renames fields (`link_1`, `Location_1`, adds `Property_City`, `Land_Acres`, beds/baths) — worth migrating the builder to it when Darien work happens.

**CT recorder-signal follow-up (committed direction, not yet built):** Gold Coast towns are one-recorder-platform-per-town — Darien on Cott RECORDhub, New Canaan legacy self-hosted, Norwalk homegrown, Fairfield town on uslandrecords.com, Westport account-walled. Greenwich's publicsearch.us covers Greenwich only. First adapter should be **RECORDhub** (modern multi-town Cott platform; towns actively migrating onto it — buys Darien now, appreciates over time). Until adapters land, the four new towns run parcel-derived signals only; Greenwich remains the fullest-stack CT territory.

**Onboarding-under-canon discipline (reconfirmed):** onboarding while ANY canonicalize holds the lock fails intermittently at seed/classify/band/counts (`Server disconnected`); small ZIPs sometimes squeeze through on spaced re-fires, larger ones don't. New Canaan's canon (7,192 parcels) ran ~45 min; Weston onboarded in ~25s the moment it released. Fire ZIPs into lock-free windows.


### 2026-07-17 — 6-ZIP expansion (98116, 98144, 98036, 98296, 85258, 75219) + Snohomish field-rename fix

Six new territories live, all on existing market rails (commits `96818f6` seeds/city-maps, `f9…` arcgis fix). Per-ZIP outcomes at session end:

- **98116 Seattle (West Seattle/Alki), WA_KING** — 9,577 parcels, geometry 100%, canon complete (9,517 processed, $10.51, 58 min), reingest done. Buckets: trust=69 llc=100 absentee/tenure full; probate=3. Quality 65.4 warn (court history only 9 months deep in this ZIP; grows with harvest).
- **98144 Seattle (Mt Baker/Leschi), WA_KING** — 9,373 parcels, geometry 100%, reingest done. Buckets: trust=47 llc=100. Canon via autofill.
- **98036 Lynnwood + 98296 Snohomish, WA_SNOHOMISH** — seeded 2,812/1,792 from the county layer; reingest-property-details topped up to **12,836 / 10,038** (same undercount pattern as 98020). absentee=100 both. Trust/llc/tenure buckets **0 — expected maturation state**: tenure is null until SCOPI autofill sweeps (~22K new parcels queued; enabled and running). **Ops follow-up: once tenure coverage is decent, re-run `/admin/reclassify-archetypes/{zip}` + `/admin/reband/{zip}` + refresh-counts** — archetypes currently classify as unknown/young/early without tenure and everything bands ≤1. 98020's history is the template.
- **85258 Scottsdale (McCormick Ranch), AZ_MARICOPA** — 15,024 parcels, 100% addresses, trust=100 llc=100 (4,799 trusts in the seed). Court/recorder signal density 0 until canon completes (deferred to autofill) and matcher picks up county-wide recorder signals.
- **75219 Dallas (Turtle Creek), TX_DALLAS** — 8,589 parcels, trust=76 llc=100 absentee=100 tenure=100. **Geometry 70.1%** vs ~92% on other Dallas ZIPs — high-rise condo density; ~2,570 units not in DCAD's CONDO shapefile. Map dots missing for those; dossiers unaffected. City set to "Dallas"; consider "Turtle Creek" for letter-copy luxury framing (Jeremy's call, pending).

**Snohomish upstream schema rename (fixed in two places):** the county renamed `SITUSTTYP` → `SITUSSTTYP` on their Parcels FeatureServer (~July 2026). Broke BOTH the seed builder (`scripts/build_snohomish_owners.py`) and the backend reingest (`backend/ingest/arcgis.py`) — each silently treated the service's 400 error payload as an empty page. Both fixed; the seed builder now fails loudly on FeatureServer `error` payloads. The poisoned-silence pattern again: any ArcGIS consumer that does `resp.get("features", [])` swallows schema errors.

**Ops notes from this session:** onboarding while another ZIP's canonicalize holds the lock reliably fails with `Server disconnected` at random steps (seed/classify/band) — don't hammer; wait for canon to release, then steps 1-6 complete in ~20s. The onboard-status object is in-memory and wiped by Railway redeploys. `refresh-counts` also hits transient `Connection reset` during contention; retry after a wait. Geometry endpoint accepts large limits (`?limit=3000` ≈ 3-4 min/call) — far fewer roundtrips than 500.

**Bainbridge Island (98110) queued behind current work** — recon done: 12,251 parcels; addresses/values/class in free bulk extracts (`Parcels.txt`/`Property_addresses.txt`/`Valuations.txt` join on `rp_acct_id`) + ArcGIS polygons. **Blockers:** Kitsap strips owner names from all bulk files AND publishes no sales extract (no KC-style BuyerName workaround) — names would need a per-parcel scrape of the county parcel-search portal (SCOPI-pattern, ~12K fetches). No Snohomish-style daily new-case PDF found on the Kitsap clerk site; county is on reCAPTCHA-gated statewide JIS — court-signal source needs its own discovery. A genuine new-market build, not a template stamp.

### 2026-07-09 (later) — Preview-walk fixes + institutional-owner screen

Jeremy's V4 preview walk caught, all fixed same session: (1) **BriefingBody scope crash** — v4Active state was in the page wrapper, swap in the body: ReferenceError broke briefings for ALL users ~40min; verification checklists now require rendering the touched page, both themes. (2) Hook-safety restructure: HomePage/TerritoriesPage are now pure chooser components (HomeLegacy/TerritoriesLegacy extracted) so the server-flag flip can't violate hook order at Phase 5. (3) Sign in restored to V4 nav. (4) Hero collision guards (viewport-height media rules; terminal keeps ≥14px on desktop — compression comes from spacing). (5) **Briefing map is Earth-ONLY per Jeremy — no display pills.** MapPanelV4 rewritten: earth-config authorized → mesh IS the map (labels re-lit, lots draped, leads glowing, PIP + nearest-centroid clicks + map-level click handler so clicks fire even without deck picks); silent treated-satellite fallback otherwise. Root cause of "Earth not loading": umbrella `import('deck.gl')` produced NO Vite chunk → scoped `@deck.gl/*` dynamic imports (chunks verified in dist). Pins now pass through untouched (String() coercion could miss handlePickLead identity checks). (6) **Institutional-owner screen** (`_is_institutional_owner`, backend/selection/weekly_selector.py): schools/churches/government/utilities/hospitals/cemeteries etc. excluded from ALL buckets and call-now at both selection entry points — Brunswick School INC was ranking #1 in Greenwich's LLC bucket. Deterministic keyword screen; applies live at briefing build, so effective immediately on deploy.

TODO next session: per-market _LOT_SOURCES for CT/AZ/TX lot polygons (CT OPM statewide parcel FeatureServer; Maricopa + Dallas ArcGIS already known from geometry backfill); parcel outlines at zoom are WA-only until then.


### 2026-07-09 — V4 UI migration: plan committed + Phase 0 (flag plumbing)

The full-scale redesign (July design sessions: homepage v18, briefing real-data demo, territories atlas demo) begins porting to production as **V4** (v1/v2 archived, V3 live, so the redesign is V4 — never "v2"). Canonical plan: **`MIGRATION_V4.md`** at repo root — phases 0-5, naming conventions, mobile acceptance gates per phase, risk register, rollback procedure. Core commitments: same components/new skin (no logic, data, or API-contract changes), V3 default until Jeremy flips `UI_V4` in Railway (rollback = env-var unset, no redeploy), mobile ships with V4 not after it (inline-style purge doubles as the mobile unlock).

Phase 0 shipped (invisible; UI byte-identical for all users by default):
- `GET /api/config` gains `ui_v4` (Railway env `UI_V4`, default off)
- `frontend/src/styles/v4-tokens.css` — warm-dusk "ink & brass" token set fully scoped to `[data-theme="v4"]` (inert until attribute set) + breakpoint canon (480/768/1080, mobile-first convention)
- `frontend/src/lib/uiVersion.js` — activation util: `?v4=1` / `?v4=0` per-browser preview override (localStorage `ss:ui_v4_preview`) → server flag; sets `<html data-theme="v4">`; lazy-injects V4 Google fonts only when active; fail-safe to V3 on any error
- Wired in `main.jsx`; built with `build:safe`

Phase 1 shipped same day: **`v4-remap.css`** — V3's entire token vocabulary (--bg/--text/--accent/semantic/tone colors, shadows, radii) redefined to warm-dusk values under `[data-theme='v4']`. Because V3 components are disciplined about styling through tokens (audit found zero literal hex in the leaf/auth pages — only never-firing var() fallbacks; V3 already carried the V4 font stack from The Estate), the remap rethemes the shell + every var-based page automatically. Spacing/transitions untouched (layout parity). Preview: `?v4=1` on /terms, /privacy, /login, /signup, /profile, /profile/voice. Known: surfaces with hardcoded module-CSS (BriefingPage era) are only partially themed in preview — that's Phase 4 scope; flag stays off by default.

Phase 2 shipped same day: **HomeV4** — the approved v18 homepage as a production component (`pages/HomeV4.jsx` + `styles/home-v4.css`, all selectors scoped `.hv4`), lazy-loaded only when the V4 skin is active so V3 users load zero extra bytes. Hero build video extracted from the demo to `frontend/public/assets/hero-build.mp4` (1.9MB static asset, not in bundle). All demo behaviors ported as hooks: nav scroll state, terminal beats typed in sync with the clip (hold-then-loop, replay), ticker, market tiles, count-up stats, founders section. The ZIP checker is the LIVE three-state flow (open→/signup, claimed→wait-list email w/ source=homepage_checker, not_covered→expansion_request), not the demo's simplified fetch — lose nothing. `uiVersion.js` now dispatches `ss:ui-v4` on activation; HomePage branches to HomeV4 via that event + isV4(). Also same session: **HOTFIX `ed456a5`** — My Leads was rendering a raw 42703 for all agents (`letters_sent_v3.sent_at` never existed; schema 023's column is `mailed_at`); and **`f908c23`** — `GET /api/map/earth-config`: server-held Google 3D Tiles key (env `GOOGLE_MAPS_3D_TILES_KEY`, separate from Street View key) handed only to territory owners/operators; 404 when unconfigured so the UI hides EARTH entirely. Known Phase 2 notes: market tiles hotlink Unsplash (license-fine; replace with owned market photography later); founders "Speak with the founders" links mailto jeremy.seglem@ pending real forwarding addresses.

Phase 3 shipped same day: **TerritoriesV4** — the atlas (`pages/TerritoriesV4.jsx` + `styles/territories-v4.css`, `.tv4`-scoped, lazy). Uses the SAME live data and flows: authed `/agent/territory-status` (statuses mine/claimed_by_other/available + market_key + counts), the SAME exported `ClaimModal` component and the SAME `billing.createCheckout` Stripe flow — the dive (camera drop, satellite develop, gold ZCTA boundary draw) is theater in front of an unchanged transaction. Boundaries from existing public `/api/zip-polygons`; new tiny public `GET /api/coverage/avg-values` serves a committed snapshot (`backend/data/zip_avg_values.json`, mean assessed value per ZIP computed 2026-07-08 from live parcels; refresh = recompute offline + commit). All ZipCard/header/subhead copy verbatim incl. operator + my-zip variants; TAKEN seals on held territories, YOURS seal (click-through to briefing) on the agent's own. Mobile-first: rail is a bottom drawer under 1080px, side panel above; Earth mode deliberately absent from the picker (velvet rope). maplibre-gl added as a dependency (lazy chunk — V3 users load none of it).

Phase 4 shipped same day — and collapsed beautifully on audit: **the entire briefing component tree (BriefingPage.module.css, all briefing/* components, ParcelDossierV2) carries ZERO hardcoded hex** — the Phase-1 remap already themes the dossier's five sections, script tabs, letters modal, notes, and lists. Phase 4's real work: (1) one literal `#8B6914` in BriefingPage → `var(--accent)`; (2) **`MapPanelV4.jsx`** — same `{mapData, playbook, selectedPin, onPickPin}` contract as the Leaflet panel (which stays in-tree untouched); warm-dusk atlas + treated-satellite altitude + real lot-polygon parcel fabric (hover/selection feature-states, gold selected boundary, family color semantics preserved luminance-tuned) with graceful centroid-dot fallback; EARTH pill appears only when `/api/map/earth-config` authorizes (velvet rope), deck.gl loaded by dynamic import on first tap (Tile3DLayer interleaved beneath labels, SSE 24, labels flip white-on-black in Earth, point-in-polygon click resolution over the lot fabric since draped layers aren't pickable); (3) backend **`GET /api/map/{zip}/lot-polygons`** — gated proxy to the WA statewide Current_Parcels FeatureServer (envelope query, digit-normalized PIN match, in-process 24h cache, returns `{}` on any failure so the page never breaks; non-WA markets fall back to dots pending per-market source configs); (4) `client.js` exports `mapApi`. deck.gl added as dependency — lazy chunk, V3 users and non-Earth V4 users load none of it. Route-shadowing lesson now doctrine: literal routes above catch-alls (bit twice: earth-config, avg-values).

Next: Phase 5 (founder preview week → default flip). Remaining known gaps: legal pages are placeholders (drafted copy exists in demos, pending lawyer review); Working-section/notes/letters flows untouched by design (they were already token-clean); mobile bottom-sheet pattern for the briefing rail is Phase-5 punch-list material after Jeremy's phone walk.


### 2026-06-16 — LAUNCH DAY: go-live (Stripe/Stannp/purge) + CRITICAL data-exposure fix (map/parcel read endpoints were public) + auth hardening

**Go-live.** Flipped the platform from test to live:
- **Stripe live.** New live secret key + live recurring price (`$299/mo`, `price_1TdZrB…`) + new live webhook endpoint at `https://sellersignal.co/api/billing/webhook` (5 events: subscription created/updated/deleted, invoice payment_succeeded/failed). Set via Railway env, no redeploy. The old test webhook ("fascinating-spark") pointed at the wrong path (`/api/webhook`) and was abandoned. Backend uses the secret key only; checkout is Stripe-hosted (`stripe.checkout.Session.create`). Agent buy flow is `POST /billing/create-checkout` — NOT the free `/agent/claim-zip` path.
- **Stannp live.** `STANNP_MODE=live` (same API key both modes). Letter scheduler ticks every 6h and mails `letters_sent_v3` rows with status='scheduled' past their send-date; queue was empty post-purge so nothing went out unintentionally.
- **User purge.** Signup is pure `supabase.auth.signUp`; `auth.users` is the source of truth. Purge = delete `auth.users` rows, which cascades to `agent_profiles_v3` (and thus `assigned_zip` claims, lead interactions/notes/tags). Left 4 users: jeremy + brian (operators, hardcoded in the signup trigger), the first paying customer, and one stray test signup.

**Auth/email repair.** Supabase Auth recovery + magic-link emails were failing `535 Authentication credentials invalid` — the Resend API key stored in Supabase Auth SMTP was dead/rotated. Created a fresh Resend key, re-pasted into Supabase → Auth → SMTP (host `smtp.resend.com`, port 465, user `resend`, sender `alerts@sellersignal.co`). Note: corporate email scanners (johnlscott.com, theagencyre.com) consume one-time tokens in magic-links by pre-fetching them, which is why **password auth is the preferred login mode** — set Brian's password admin-side via the Auth Admin API (no email round-trip needed). Carry-forward: verify Railway `RESEND_API_KEY` (backend transactional mail) is the new key, not the dead one.

**First paying customer — live Stripe path proven end-to-end.** Onboarding surfaced a real bug: `_zip_is_claimed()` (billing.py) checks `agent_territories_v3` for status='active', but **that table has no FK to `auth.users`**, so the purge left orphaned 'active' beta rows that blocked the first real buyer from claiming a previously-beta-tested ZIP. Worked around by deleting orphaned rows (`delete from agent_territories_v3 where status='active' and agent_id not in (select id from auth.users)`). Then checkout → payment → `subscription.created` webhook → territory row all fired correctly. **Carry-forward (root fix, still pending): add FK `agent_territories_v3.agent_id REFERENCES auth.users(id) ON DELETE CASCADE`** so purges self-heal instead of needing manual cleanup.

**CRITICAL: lead PII was publicly scrapable.** While debugging logout (data stayed painted on a shared screen), found a far bigger hole: the map and parcel-dossier read endpoints had **no auth gate at all**. Empirically (no credentials): `GET /api/map/{zip}` returned every parcel with `owner_name`, address, signal_family, value, pressure (4,150 rows for 98290); `/api/parcels/{pin}` and `/why` returned the full dossier incl. owner name. Briefings was correctly gated (401) but map/parcels were not — so the core lead data (who/where/why) was open across all 90 ZIPs. Two causes:
1. **Backend:** `map_data.py` + `parcels.py` never called `require_zip_access` (unlike briefings).
2. **Frontend:** `AuthGate` was demo-by-default (`VITE_AUTH_REQUIRED === 'true'`) — a build-time-inlined var that wasn't set when the deployable bundle was built, so the UI gate was bypassed entirely (same build-time-env trap as the earlier Supabase-config incident).

**Fix (commit `6ea8fe2`, deployed 2026-06-16 16:10 UTC):**
- Backend: added a `_gate(zip_code, authorization, x_admin_key)` helper to `map_data.py` and `parcels.py` mirroring the briefings gate — allows the X-Admin-Key server-loopback exception, otherwise `require_zip_access(user_from_authorization(authorization), zip)`. Applied to `/api/map/{zip}`, `/map/{zip}/bounds`, `/map/streetview/{pin}` (gates on the parcel's own zip — added `zip_code` to its select), `/api/parcels/{pin}`, `/api/parcels/{pin}/why`. **The public `/api/zip-polygons` endpoint (boundaries only, no PII) is intentionally left open** — it powers the territory-SELECTION map, so gating map/parcels does NOT break ZIP browsing.
- Frontend: `client.js` `map.*` + `parcels.*` switched from `request` → `authedRequest` (sends JWT). `AuthGate` flipped to **secure-by-default** (`VITE_AUTH_REQUIRED !== 'false'`) — auth is enforced unless a demo build explicitly disables it. `signOut` now does a hard `window.location.assign('/')` so the React tree is wiped on logout (no stale data on shared machines). Built with `npm run build:safe` (bundle `index-DGmd4sNp.js`).
- **Server-side gate is now authoritative** — the frontend gate is UX + defense-in-depth, not the security boundary.

**Verification (live):** no-auth → map/parcels/bounds/briefings all 401; X-Admin-Key path → 200 (authorized access intact); agent JWT path smoke-tested (briefing + dossier load for owned ZIP). Hole sealed.

**Still owed (security hygiene):** rotate the GitHub PAT, admin API key, and Supabase **service_role key** (all were exposed in chat during this work; service-role rotation also requires updating Railway `SUPABASE_SERVICE_KEY`).

### 2026-06-15 — Institutional-owner leakage fix (owner-type classifier expansion + tenure plausibility guard + 90-ZIP reclassify rollout)

**The problem.** Greenwich (06830) operator view surfaced institutions at the very TOP of the long-tenure bucket — "Marys Roman Catholic Convent St" (126yr), "Exchange For Womens Work" (89yr), "Boys Club Assoc Greenwich" (87yr), "Authority Wilbur Peck Housing" (74yr), "Pauls Evangelical Lutheran St" (71yr), "York Telephone Nynex" (71yr), "Veterans Byram" (69yr) — all wrongly tagged `owner_type='individual'`. Root cause: `_derive_owner_type` (`backend/ingest/arcgis.py`) had a narrow institutional marker set and let these fall through to `individual`. The tenure bucket (`_select_long_tenure_bucket`, `weekly_selector.py`) gates on `owner_type=='individual'` AND ranks by `tenure_years` descending — so any mis-tagged entity with a long hold sorts straight to the top of what should be the highest-intent individual-owner list. A luxury-positioning credibility problem, not just a data nit.

**Fix A — classifier expansion (commits `3bb67a5`, `cb4200e`, `a26fa87`).** Broadened `_derive_owner_type` markers: gov (`AUTHORITY`/`REDEVELOPMENT`/`BOROUGH|VILLAGE|TOWN OF`/`METROPOLITAN DIST`/`COMMISSION`); nonprofit (`ASSOCIATION|ASSN|ASSOC`/`HOMEOWNERS`/`CLUB`/`CONVENT|MONASTERY|RECTORY|SEMINARY`/`FOUNDATION`/`ENDOWMENT`/`SOCIETY`/`CONSERVANCY`/`HABITAT`/`UNIVERSITY|COLLEGE|ACADEMY`/`HOSPITAL`/`MUSEUM|LIBRARY`/`CEMETERY`/`INSTITUTE`/`EXCHANGE`/`COUNCIL`/`LEAGUE`/`CONDOMINIUM|COOPERATIVE`/ religious denominations `LUTHERAN|METHODIST|BAPTIST|PRESBYTERIAN|EPISCOPAL|EVANGELICAL|CONGREGATIONAL|UNITARIAN|ADVENTIST|PENTECOSTAL|MENNONITE|ORTHODOX|CATHOLIC|TABERNACLE`/ fraternal+veterans `VETERANS|LEGION|ELKS|ROTARY|KIWANIS|KNIGHTS OF|MASONIC|VFW`); llc/commercial (`COMPANY|ASSOCIATES|REALTY|PROPERTIES|INVESTMENTS|MANAGEMENT|DEVELOPMENT|BUILDERS|CONSTRUCTION|VENTURES|CAPITAL|BANCORP`/ utilities `TELEPHONE|ELECTRIC|GAS|UTILITIES|RAILROAD|RAILWAY`). **Surname-collision guarded** (precision matters more than recall here — a false entity tag silently deletes a real individual lead): dropped false-positive markers that are real surnames/words — `HOA` (hit Vietnamese "Hoa" given names), `ABBEY|BANK|GUILD|POWER|CHRISTIAN`; `KNIGHTS` requires the literal `KNIGHTS OF`. Validated locally + in production dry-run across all 7 markets: the surfaced institutions route correctly, and real people stay `individual` — Power/Powell, Christian/Christopher, Knight/"Knights Susan", Gaston, Hall, Banks, Railey, Legge, Fox, Forest. The reclassify endpoint also carries a never-downgrade guard (`HIGHER_SPECIFICITY={llc,trust,estate,gov,nonprofit,company}`) so a re-run never knocks a more-specific type back to individual.

**Fix B — tenure plausibility guard (commit `a26fa87`, `weekly_selector.py`).** Added `_MAX_PLAUSIBLE_INDIVIDUAL_TENURE=80` and an upper bound in `_select_long_tenure_bucket` (now `15 <= tenure_years <= 80`). A living individual essentially never personally holds a deed 80+ years (bought as an adult 80yr ago ⇒ ~100+ today); past that it is a near-certain mis-classified entity the keyword pass missed, a deed that never transferred after death (an estate, not a callable individual), or a bad `sale_date`. This is a robust **name-independent backstop that went live globally across all 90 ZIPs on deploy** — it suppresses extreme-tenure institutions everywhere (even before per-ZIP reclassify) and also guards against inflated-tenure `sale_date` data artifacts. (The 69–71yr institutions like NYNEX/Lutheran/Veterans sit under 80yr, so the keyword pass does the heavy lifting for that tier; the cap catches the extreme tail like the 126yr convent regardless of name.)

**Rollout — reclassify + refresh across all 90 ZIPs.** Ran `POST /api/admin/reclassify-owner-type/{zip}` (re-derives `owner_type` over existing rows in place) + `POST /api/coverage/refresh-counts?confirm=true&zip_code={zip}` for every live ZIP. **Operational gotcha (worth a future refactor):** the reclassify endpoint does row-by-row `UPDATE`s, which holds the single Railway worker for the duration; bursting calls saturates it and produces transient `/health` timeouts + 5xx (recovers in ~15s once stopped). Reliable method = **paced, health-gated, single-ZIP** (wait for healthy → reclassify → refresh → short sleep). HOA/condo-dense ZIPs ran into the thousands of changes (98027=2624, 98119=2427, 98053=2025, 98117=2016, 98011=1662, 85085=1637, 98109=1531; several others 0 = already clean). A batch-update refactor of the endpoint would make future sweeps fast and gentle.

**Verification.** Greenwich 06830 tenure bucket → top 10 all real individuals (Evelyn Headley 79.7yr, Leon Kahan, Marie Delia, Russell Hughes…), **0 non-individuals, max exactly 80yr** — convent/BoysClub/Exchange/HousingAuthority/Lutheran/NYNEX/Veterans all gone. KING spot-checks: 98039 Medina (0 non-individual, max 44yr), 98112 Madison Park (0, 49yr), 98052 Redmond (0, 49yr) — surname guards holding in the wild (Powell/Christopher/Fox/Forest all individual).

**Known residual (left alone, low frequency).** Pre-existing position-based rules for `TEMPLE|PARISH|CHURCH|CHAPEL` misroute a handful of real surname-people (e.g. "TEMPLE JOHN PAXTON") to nonprofit. Not touched this pass — tightening it risks breaking legitimate "Temple Beth…" / "X Parish" detection, and the frequency is low.

**State for next session.** Classifier + tenure guard deployed (`a26fa87`); all 90 ZIPs reclassified + counts refreshed; tenure buckets verified clean. Follow-ups: (1) the 5 script builders (`scripts/build_{ct,dallas,maricopa,snohomish,kc}_owners.py` `classify_owner_type`) still carry the OLD narrow classifier — sync the institutional markers into them for future-seed correctness (only the live `_derive_owner_type` was fixed). (2) Consider a batch-update path on the reclassify endpoint (single-worker friendliness). (3) `reband` + `reclassify-archetypes` were NOT re-run after reclassify — secondary (they affect band/dossier framing, not the lead-quality bucket that this fix addresses), but MANIFESTO convention is to run them after an owner-type sweep.

### 2026-06-14 (evening) — Pre-launch readiness audit (90 territories) + TX condo map geometry fix + recorder runner flush refactor

Launch-prep session. Outcome: all 90 territories audited launch-clean; Dallas/Travis map geometry lifted from 92%/82% → 99%/98%; all 3 TX/CT recorder runners hardened against overrun data loss.

**A. Recorder runner per-chunk flush refactor (commits `ba3f314`, `a026438`).** All three `publicsearch.us` recorder runners (`run_dallas_recorder.py`, `run_collin_recorder.py`, `run_greenwich_recorder.py`) used accumulate-all-then-write-once — a cancelled/overrun run lost the entire batch (the Maricopa trap; also silently lost slow daily-cron batches, likely why Dallas had only 207 signals when 30 days alone = 318). Refactored to load the county owner index up front + resolve+write each chunk immediately via a new `_resolve_rows(idx, rows)` helper. Daily-cron behavior identical for short windows; now durable/resumable. Dallas dry-run (run #12, days=30) validated: DCAD index 860,392 accounts, 18,237 grid rows → 318 estate, 0 errors, per-chunk "flushed" logs correct. **Cost finding:** a 30-day Dallas window takes ~90 min (huge county) → full-depth Dallas probate backfill is impractical; flush-safety is what makes partial runs survivable. Right-sized decision: do NOT block launch on expensive Dallas/Collin probate scans — TX markets are launch-ready from structural buckets (Dallas ~2,835 / Collin ~1,648 / Travis ~2,903 Contact-Now leads); probate is a high-intent bonus the now-hardened daily cron builds forward (~10 Dallas estate/day).

**B. Pre-launch readiness audit — all 90 territories.** Inventory PASS (all 90 stocked, ~32,058 Contact-Now leads, zero empty briefings). Status PASS (all live, all parcels loaded). Letter/brand-voice pipeline PASS (admin `/voice-smoketest` generates valid multi-day sequences; Anthropic key live). Territory-claim flow PASS and **Stripe-independent** (`claim-zip` validates role/live/unclaimed and writes assignment — no payment gate, so beta agents can claim before Stripe goes live). All `/map` and `/briefings` 500s observed were transient single-worker cold collisions (healthy on retry) — mitigated by the cache fix; the deferred cache-warmer would eliminate them. `investigated_count=0` across 89/90 ZIPs is expected (per-agent action metric, no agents yet).

**C. TX condo/unit map geometry fix (commits `7597dc1`, `9c72b1c`, `d238978`).** Audit found Dallas 92% / Travis 82% of signal parcels had map coordinates; 90–94% of the misses were condos/units. Diagnosed: the county parcel GIS layers (Dallas City Hall `DallasTaxParcels`, Travis TCAD `EXTERNAL_tcad_parcel`) carry NO per-unit condo geometry — stacked units share one building footprint (Dallas literally labels them `ACCT='MULTIPLE'`). Verified known-good pins match the GIS 4/4 while condo pins are absent, so re-running the existing pin→GIS backfill was a dead end. Fix: added a **Census batch-geocoder fallback** to `geometry_backfill.py` (free, keyless, ~10k/req) — for pins GIS can't resolve, geocode the unit-stripped building address to a WGS84 point (a condo pin belongs on its building). Gated by `geocode_fallback` flag (default off; WA/AZ/Collin untouched, already ~100%). Added `retry_skipped` flag to reclaim parcels the GIS-only autofill had marked `geocode_skipped` before the fallback existed (75205 Highland Park had 562 such — all reclaimed). Hardened `geometry_autofill` to pass `geocode_fallback=true` so it self-heals future reingested condos instead of GIS-skipping them. New endpoint params: `POST /api/admin/geometry/{zip}?geocode_fallback=true&retry_skipped=true`. **Result: Dallas 92→99%, Travis 82→98%** (all ZIPs ≥95% except 75225 at 93% — its residual is two Census-untracked condo towers on W Northwest Hwy; genuinely unmatchable, future second-geocoder cleanup). Census match rate on condo addresses ~88–100%.

**State for next session:** TX/CT supply right-sized (CT deep pull banked +56 probate earlier; TX structural buckets carry launch). Map geometry launch-clean across all markets. Readiness audit clean. Next: Jeremy's manual flips (Stripe live keys, `STANNP_MODE=live`, verify `RESEND_API_KEY`, order Stannp sample pack, boot beta agents) — all decoupled from the core experience; then beta boot.

### 2026-06-14 — Maricopa deep PD pull + recorder eligibility fix (probate harvesting SOLVED; honest Contact-Now ceiling)


**The problem.** AZ_MARICOPA (24 ZIPs) was stuck at 7 Contact-Now probate leads vs KC's 2,126. Root cause was NOT the matcher — it was signal starvation. The recorder harvester had only ever pulled ~27 probate (`PD`) signals over a ~2-week window, vs KC's 8,846 court signals over 12 months. At the same ~22% in-ZIP hit rate, 27 signals can only yield ~7 hits. (Diagnosed via `/api/harvest/diag/signal-date-range?signal_type=probate&source_type=...` which gives total/matched/0-hit/earliest/latest.)

**Why the harvester was starved — two compounding bugs, both fixed.** Every GitHub Action run since 06-11 was CANCELLED: (1) the runner accumulated all rows in memory and wrote to Supabase ONCE at the end, so any mid-run cancellation persisted zero; (2) the weekly county-roll cache build (1.76M parcels, sequential `resultOffset` pagination ~9-11s/page) blew the 350-min job ceiling, got cancelled, and since the cache only saves on success it never warmed — so every run rebuilt from scratch and died. Vicious cycle, the dominant blocker. NOTE: the Maricopa recorder is Cloudflare-gated from datacenter IPs — only the GitHub Action vantage can fetch it, so ALL parser/fetch validation must go through Action runs, never local.

**Fixes shipped (workflow id 293329302):**
- `7cc79f6` — runner walks the window in 30-day sub-slices and flushes writes PER SLICE (cancellation-safe, resumable via existing skip-seen). Added `END_OFFSET_DAYS`. Daily 14-day cron behavior unchanged.
- `bd6f918` — county-roll builder parallelized via `ThreadPoolExecutor` (`ROLL_WORKERS=10`, `fetch_page(offset)` helper). Roll build ~57min (was 5+ hrs) → completes under timeout → cache finally sticks → runs stop dying. (Speculative further speedup: keyset pagination on `APN_DASH` instead of `resultOffset` — non-blocking, cache covers the week.)
- `bffe0b6` — CAPTURE mode (`capture=1`): dump raw OCR for any doc code without roll/parse/write, for probing the code catalog. Skips the roll-build steps.
- `7fb5f9b` — `briefings.py`: `az_maricopa_recorder` was MISSING from the recorder-PR-classification source set (renamed `_TX_SOURCES`→`_RECORDER_SOURCES`). AZ probates fell through to `contact_status='not_applicable'`, discarding their `PD`-parsed family PR. Now classified like the TX/CT recorders (family-looking PR → `family_pr_identified`; corporate → `unworkable_pr`; absent → `no_pr_yet`). Verified AZ recorder signals carry `party_names` with a `personal_representative` entry, same shape as TX/CT, so the branch works; parser sets `pr_name` but not `pr_classification` — briefing re-derives via `_CORP_PR_RE` regex, so that's fine.

**Deep PD pull (Action run, days=730, write=1): 27 → 998 signals, 7 → 143 in-ZIP hits, full 2 years back to 2024-06-13.** This is the real win — King-County-style pipeline depth. Harvesting is now permanently fixed and self-healing (roll cached, incremental resumable writes, daily cron).

**Parser tier ruled out as empty.** Capture runs over a full year returned: `JP` (Decree of Distribution) = 0, `DC` (Death Certificate) = 0, `BB` (Beneficiary Deed) = 0. `PD` is the ONLY productive Maricopa recorder probate code. No additional parsers worth building.

**Honest conclusion — the eligibility fix is a CORRECTNESS fix, not a volume fix.** After `7fb5f9b` + full 24-ZIP refresh, AZ Contact-Now probate went 15 → 14 (DOWN one — correctly deferred a no-PR false positive). The deep pull did NOT raise Contact-Now. Verified in code: there is NO event-date freshness gate on Contact-Now (the only 7-day logic is `_is_new_this_week`, a display badge in `_shape_pick`, not a gate). The 143→14 funnel is `eligible_for_call_now` (strict parcel match + actionable family PR, Rules 1/2/3/6) + owner dedup. So the Contact-Now probate ceiling (~14) is a DATA-QUALITY bound — how many in-ZIP `PD` docs both strict-match an owner AND name a parseable family PR — NOT freshness and NOT signal volume. The deep pull's payoff is Build-Now depth (143 in-ZIP hits). The fix's real value: the dossier now names the actual PR to call (was blank under `not_applicable`), and no-PR probates are correctly deferred. (Earlier-in-session hypothesis that the eligibility path was suppressing a big lead jump was WRONG and is owned here.)

**Ops lesson reinforced.** `refresh-counts` is an in-process briefing recompute on the single uvicorn worker — firing 24 back-to-back saturated the worker and timed out reads (site degraded ~2 min, recovered; `/api/health` stayed 200 throughout). Refresh in small paced batches with sleeps, never rapid-fire 24. No commit-SHA in `/api/health`, so deploys are verified via background-task `started_at` reset.

**Still open:** PAT rotation owed (workflow-scoped classic PAT used this session — kept OUT of repo per active issue #7); CT + Collin coverage rows still show `city='Bellevue'` (fix via `/admin/coverage-meta/{zip}` on those 10 ZIPs); Greenwich post-canon recorder close-out.

### 2026-06-12 (night) — CONNECTICUT LIVE: Greenwich 5-ZIP launch (7th state-market, 90 territories)

**CT_FAIRFIELD market launched same-day from discovery to live.** Discovery verified all four legs: (1) CT OPM statewide parcel+CAMA FeatureServer (services3.arcgis.com/3FL1kr7L4LvwA2Kb/.../Connecticut_State_Parcel_Layer_2023/FeatureServer/0) with Owner/Co_Owner/mailing/values/Sale_Date — one integration covers all 169 towns; per-town CAMA schema variance is real (Wilton/Westport State_Use anomalies). (2) Value screen: Greenwich 3,706 res parcels assessed >$2M (~$2.85M+ market at CT's 70% ratio) — richest territory ever screened. (3) Statewide probate Case Lookup (apps.ctprobate.gov/caselookup) — NO captcha, name+district POST works programmatically; empty-name browse 500s, so it's a verification tool (obit→lookup enrichment is the Phase 2 path, like Snohomish PR enrichment). Districts: PD54 Greenwich, PD52 Darien-New Canaan, PD50 Westport. (4) greenwich.ct.publicsearch.us — our recorder platform; other Gold Coast towns are NOT on it (CT records at town level).

**Launch (commits `180a30e`→`4c082e1`):** `scripts/build_ct_owners.py` — statewide layer filtered Town_Name='Greenwich', ZCTA point-in-polygon spatial join (layer has no ZIP column; ray-casting against data/zip_polygons/ct.json), pin=Link, value=Appraised_Land+Building, tenure from Sale_Date, four-way owner_type classifier (trust/llc/company/individual — first cut lumped trusts into company; Greenwich = 1,561 trusts + 2,225 LLCs), USPS locality cities (Old Greenwich/Riverside/Cos Cob matter for letter copy), centroids ride in seeds = 100% geometry. Seeds are pin-keyed dicts (loader contract). 17,506 parcels / 100% addresses. Scaffolding: CT_ZIP_TO_CITY + onboard auto-detect + ct-fairfield prefix, _MARKET_STATE, matcher `ct_greenwich_recorder`→{CT_FAIRFIELD}, briefings PR-in-signal branch, CT state pill + Greenwich metro tab, seed-from-json repair endpoint gained Travis/Collin/CT dispatch branches (pre-existing gap), zip_builder city chain gained COLLIN/CT.

**Result: 5 ZIPs LIVE, 1,808 structural leads day one** — 06830: 400 (all caps maxed), 06831: 400 (maxed), 06870 Old Greenwich: 332, 06878 Riverside: 352, 06807 Cos Cob: 324.

**Greenwich recorder LIVE (one capture iteration, the Collin method):** grid columns differ from BOTH TX tenants — DOC#/BOOK/PAGE-first, short per-volume doc numbers (composite document_ref GW-{book}-{page}-{num}), and a PROPERTY ADDRESS column (direct parcel resolution, lands in legal_description). Tenant row-regex override in the runner, proven locally against the captured sample before dispatch. CT estate doc types added (Certificate of Devise, Probate Certificate, Fiduciary Deed). First full run: 552 grid rows / 4 estate instruments / 3 of 4 town-resolved (17,513-account inversion) / 4 signals written. Daily cron 9:40am ET. Capture workflow host input now takes the state segment (greenwich.ct).

**Collin close-out executed:** canon cleared all 5 Collin ZIPs → scoped reset (34 signals) → rematch (5 matches) → 75013 has Collin's first probate Contact Now lead; Collin total ~1,648. Greenwich's 4 recorder signals await the same close-out once CT canon completes (canon was on 06807 at session close).

**Still open:** Maricopa RESOLVE_BACKFILL exceeded even the 350-min ceiling at days=60 (no checkpointing — needs a window-offset input for chunked backfill); re-dispatched days=21 as the high-value recent slice. Greenwich post-canon close-out. Travis recorder parked (their search backend 500s for real users; cron is the recovery canary). PAT rotation owed.

### 2026-06-12 (cont.) — Expansion wave, Collin County launch, canon root-cause fix, blank-page saga, Maricopa inversion, Collin recorder live

**Canon worker saturation — ROOT-CAUSED AND PERMANENTLY FIXED (commit `ae7b05a`).** The two site-wide outage-like slowdowns traced to `_fetch_existing_pins` in `backend/ingest/backfill_owner_canonical.py`: it pulled the ENTIRE `owner_canonical_v3` table (600K+ rows = 600+ sequential 1000-row queries) on EVERY canon tick — including idle sweeps — because the original was written when one 6K-parcel ZIP existed ("For a 6K-parcel ZIP this is trivial," said the comment). Rewritten to per-ZIP pin-membership `.in_()` queries (400/chunk; the caller already holds the ZIP's pin list). Proven under maximum load: canon actively canonicalizing 75013's 14,924 parcels while production health held at 0.13–0.8s (vs 21–30s timeouts that morning). **Canon stays ON permanently — no env gate, no pause-during-onboarding needed.** En route: a broken push (`403c26a`) briefly shipped a corrupted file — reverted within ~90s (`5814dc8`), prod stayed up. Sandbox lesson logged: a failed python heredoc inside a multi-line bash block does NOT stop subsequent separate-line commands; verify syntax before commit lands in the same block.

**Blank-lead-page saga — RESOLVED (commits `e19137d`, `90cf2a4`, `182c13e`).** Root cause via the new ErrorBoundary screenshot + source-map resolution: Leaflet initialized inside the hidden mobile map tab (zero-size container) → NaN map transform → the first flyTo on lead-click threw `Invalid LatLng (NaN,NaN)` and blanked the React tree. Fixed: MapPanel calls `invalidateSize()` before flyTo, try/catch with setView fallback, guarded fitBounds. Permanent infrastructure added en route: top-level `ErrorBoundary.jsx` (blank screens now show the error + reload button), `Cache-Control: no-cache` on index.html in backend/main.py (kills stale-shell pinning — the class of "works after hard refresh" reports), and dossier-fetch loading/"tap to retry" states in BriefingPage.

**Maricopa county inversion shipped (commits `0ea9644`, `1c4dc27`, `13b93ba`).** Mirrors the TX pattern: `scripts/build_maricopa_county_roll.py` pulls the full Assessor MapServer county-wide (1,758,095 parcels → gzip CSV: apn/owner_name/address/zip/city/puc), `CountyOwnerIndex.from_maricopa_roll` loads it (acct=APN_DASH; RES = puc startswith '01' — Maricopa residential PUC is 01xx, fixed in `13b93ba`), `run_maricopa_recorder.py` gained a resolution post-pass + `RESOLVE_BACKFILL=1` mode to re-resolve historical signals, weekly roll cache in maricopa-recorder.yml (timeout 110min). Pre-inversion truth: only 4 real AZ probate Contact Now leads platform-wide; AZ/TX divorce=0 is structural (no court divorce source in those markets). **Backfill run still in flight at session close** — close-out when it lands: `rematch-reset-scoped?source_type=az_maricopa_recorder&signal_type=probate&confirm=true` → `/rematch-autofill-trigger` → refresh all 24 AZ counts → report real probate numbers.

**Territory map fixes (commits `76cebdf`, `d9ef74e`).** territory-status endpoint omitted `market_key` from both record dicts — the frontend grouped ALL TX ZIPs into one zoomed-out "Texas" tab. Fixed + TX_COLLIN groups under the 'Dallas' metro tab (MARKET_METRO_LABELS). Mobile: metro pills moved from an absolute overlay to a normal-flow horizontally-scrollable bar above the map; legend bottom-left.

**Expansion wave 1 — 9 ZIPs, 3,021 leads.** All value-screened from local rolls before onboarding. Travis: 78738 Lakeway (331), 78732 Steiner Ranch (307), 78704 Travis Heights (396 — seed geometry only 55.4%, urban condos missing from EXTERNAL_tcad_parcel; geometry-backfill candidate). Dallas: 75244 (172), 75206 M Streets (332). Maricopa: 85016 Biltmore (386), 85251 Old Town Scottsdale (400 — all caps maxed), 85012 Central Corridor (316), 85250 McCormick Ranch (381). Maricopa ArcGIS screen gotchas worth keeping: FCV_CUR is a STRING (CAST(FCV_CUR AS INTEGER) in where clauses), PHYSICAL_ZIP needs quotes, residential = PUC LIKE '01%'. Next-up candidates banked: Maricopa central-corridor cluster 85020/85021/85013/85014; Collin 75002 Allen East (3,546 $1M+ parcels).

**Collin County (TX) — 6th market launched. 5 ZIPs, 53,332 parcels, 1,647 leads.** Seeds from the CCAD public FeatureServer (`scripts/build_collin_owners.py`; services2.arcgis.com/uXyoacYrZTPTKD3R/.../CCAD_Parcel_Feature_Set/FeatureServer/4; pin = propID; res filter propCategoryCode LIKE 'A%'; **returnCentroid=true rides geometry in the seed — 100% map coverage at seed time, no backfill step**, a first). Query gotcha: CCAD's layer silently returns 0 rows for LIKE+AND combos — use equality `situsZip = 'X'`. Scaffolding: COLLIN_ZIP_TO_CITY + auto-detect (admin.py), `_MARKET_STATE` TX_COLLIN→TX, geometry config (pin_field propID), matcher SOURCE_MARKET_SCOPE tx_collin_recorder→{TX_COLLIN} + tx_topics_citations += TX_COLLIN, briefings `_TX_SOURCES` += tx_collin_recorder, TOPICs COUNTY_MARKETS "Collin"→TX_COLLIN + COLLIN_ROLL index in the runner, TIGERweb polygons (use tigerWMS_Current/MapServer/2 — the PUMA/TAD/TAZ service's layer 2 became an ACS group and no longer works). `scripts/build_collin_county_roll.py` deliberately emits the MARICOPA CSV SCHEMA so `from_maricopa_roll` serves both counties — one loader, two markets. Onboarding note: biggest ZIPs needed up to ~8 orchestrator re-fires through transient httpx disconnects (each retry advances one step; expected behavior).

**Collin recorder LIVE — the UI_DRIVE saga (commits `5cbfe67`→`54fdd0f`).** collin.tx.publicsearch.us and travis.tx.publicsearch.us run a NEWER frontend generation that does NOT auto-execute /results URL-param searches on direct page load (Dallas still does — 7,371 grid rows on yesterday's cron). Solution: **UI_DRIVE mode** in the shared dallas_recorder module (flag default False; Travis/Collin runners set `dr.UI_DRIVE=True` + `dr.HOME_URL`) — `_ui_drive_search` goes to the home page, dismisses the announcement banner, fills the aria-labeled Starting/Ending Recorded Date inputs (M/D/YYYY), and clicks the Search submit; the existing grid-read + pagination takes over. Three distinct bugs found en route, all proven by an instrumented interactive-capture workflow (dallas-search-capture.yml gained host + keyword inputs, control dumps, and post-click URL/body diagnostics):
  1. `extract_grid_text` grabbed the FIRST `<table>` (Collin has an earlier empty utility table) — now selects the table containing the GRANTOR header, longest-table fallback, body fallback.
  2. Virtualized grids split header and data tables — added a parse-body-text fallback in iter_window_rows when the table parse yields 0.
  3. **The decisive one, found by running the real parser LOCALLY on the capture's exact body text instead of iterating workflow runs:** `_ROW_RE` required a TOWN column between BOOK/VOLUME/PAGE and LEGAL that Dallas has but Collin doesn't. Made the town group optional; proven locally against both tenant shapes before dispatch (`54fdd0f`).
First full run (days=14, write=1): **5,417 grid rows, 34 estate instruments with NAMED PERSONAL REPRESENTATIVES** (e.g. decedent HODGES KENNETH E → PR HODGES BETTY S), 13/34 county-resolved against the 429,742-account CCAD index, 34 signals written. Daily cron 7:50am CT. Empty keyword = full grid (968 docs/day observed); 05/23-24 zero rows = Memorial Day weekend, legit. **METHODOLOGY LESSON (standing): when a remote parse/extract fails and a ground-truth sample exists in captured output, run the real function on it locally FIRST — the regex bug was findable locally all along and cost 4 workflow iterations before the local test found it in one.**

**The pre-canon race consumed the Collin signals (open at session close).** The rematch task processed all 34 Collin signals at 16:26 against a market whose canonicalization hadn't run yet (75093 canon=0%) → matched_at set, match_count=0, signals consumed. Third occurrence of the "matched once pre-canon = permanently consumed" pattern (Snohomish 2026-05-19, Travis 2026-06-11). Close-out once canon clears all 5 Collin ZIPs (in flight, ~hours): `rematch-reset-scoped?source_type=tx_collin_recorder&signal_type=probate&confirm=true` → `/rematch-autofill-trigger` → refresh 5 Collin counts. Worth a structural fix eventually (e.g., matcher skips markets with canon < threshold instead of consuming); scoped reset handles it operationally. Also observed: one transient ReadError made the rematch task LOOK frozen for 30+ min (it had actually completed server-side and gone idle on its 1-hour interval); `/match-only` is no longer usable at 85 territories (global owner load — predates multi-market scoping).

**Still open from today:** Travis recorder panel-open (date inputs collapsed behind `#date-range-select`; click chain incl. JS dispatch not expanding it — interactive capture iteration in flight; non-blocking, TOPICs covers Travis daily). Maricopa backfill close-out (above). Travis parcels carry state='WA' internally (cosmetic repair pass queued). 78704 geometry backfill. PAT rotation (exposed in chat again). `/api/parcels` returns 200 unauthenticated (noticed, unaddressed). 85260 lead flapping (may be moot post-canon-fix).

### 2026-06-12 — KC GIS migration, Dallas build-out, Travis County (Austin) launch

**KC "outage" was a platform retirement (Jeremy called it).** The 3-day "KC GIS down" diagnosis was wrong. King County RETIRED its legacy self-hosted stack (gisdata + gismaps.kingcounty.gov) on June 1, 2026 — every layer page carried a "RETIRING JUNE 1st, 2026" notice we missed. Post-retirement both hosts answer datacenter clients with 503s/TLS resets; Anthropic's fetcher (different vantage) reached them fine, which broke the outage theory. Successor found via the AGOL sharing search API: ESRI-hosted services on KC's ArcGIS Online org (`services.arcgis.com/Ej0PsM5Aw677QF1W/.../PARCEL_ADDRESS_PUB_AREA_3069/FeatureServer/0`) — IDENTICAL schema, maxRecordCount 1000, datacenter-accessible. Repointed both WA_KING configs (arcgis.py reingest + geometry_backfill). Reingested all 20 KC gap ZIPs (~180K parcels); geometry coverage went 0-30% → 74-91% (true ceilings). **LESSON (now standing): "server down for days" is almost never the right explanation — check for deprecation/retirement notices and test from an independent vantage (web_fetch/web_search) before accepting it.** Residual: 98117 has one deterministic 1,000-row reingest batch that fails every retry (constraint-violating row suspected; ZIP at 88% regardless).

**Dallas County completed — 7 live territories.** Value-screened all county ZIPs from the local DCAD roll (RES medians + p75 for barbell detection). Added 75214 Lakewood (11,125 parcels — seed was committed but onboard had never run; the coverage row was a stub), 75229 Preston Hollow W/Strait Lane (9,652 — median $0.71M but p75 $1.26M, classic barbell), 75220 Devonshire (5,988, same shape). With 75205/75225/75230/75209 that's ~2,440 structural leads. 75201 (downtown hi-rise, $0.98M median) staged but skipped — condo dynamics. Remaining county is sub-$0.65M median. The "territories map shows Texas but click leads to nothing" report was stale browser cache — bundle + polygons verified correct in production (hard refresh fixes).

**Travis County (Austin) launched — 6 live territories, the biggest single-market launch yet.** Probe results that greenlit it: travis.tx.publicsearch.us is the SAME neumo platform as Dallas (HTTP 200, no Cloudflare challenge, same /results param shape — recorder port is a subdomain+source_type override); TCAD publishes its full appraisal roll free (traviscad.org/publicinformation → "2026 Preliminary Appraisal Roll Export", 554MB zip, TrueProdigy Legacy 8.0.32 fixed-width, layout xlsx posted alongside); geometry via the ESRI-hosted EXTERNAL_tcad_parcel layer (City of Austin publishes it; PROP_ID = roll prop_id with leading zeros stripped = parcels_v3.pin for TX_TRAVIS). Value screen (492K properties): 78746 Westlake $1.77M / 78703 Tarrytown $1.41M / 78730 River Place $1.13M / 78733 Eanes $1.11M / 78731 NW Hills $1.00M / 78735 Barton Creek $0.84M-median-$1.63M-p75 barbell (Jeremy added it). Built `scripts/build_travis_owners.py` (multi-ZIP single roll scan; deed_dt is MM-DD-YYYY; OV65/HS exemption flags available in layout for future aging signal), `CountyOwnerIndex.from_tcad_roll` (Travis inversion), `run_travis_recorder.py` (shared dallas_recorder module now has overridable RESULTS_URL + SOURCE_TYPE), travis-recorder.yml + TCAD cache in topics workflow, per-county owner indexes in the TOPICs runner (a Travis decedent must NEVER be resolved against the Dallas roll), TX_TRAVIS everywhere (matcher scope incl. tx_topics_citations expansion, briefings _TX_SOURCES, geometry config, admin maps/auto-detect), 6 TIGERweb polygons, and the **Dallas/Austin metro tab split** (TX groups by market_key now, not state — the far-flung-same-state failure mode the original map comment predicted). Final: 34,576 parcels, 1,878 contact-now leads (361/372/344/282/257/262).

**Two recurring bugs killed at the root during the launch:**
- **Register-default city ("Bellevue") bug — structurally fixed.** BOTH resolution chains (onboard endpoint + cmd_seed in zip_builder) now carry ALL county maps (KC→SNO→MARICOPA→DALLAS→TRAVIS), and cmd_seed treats a stored "Bellevue" on a non-KC ZIP as the known artifact (falls through to the maps). The coverage-meta repair endpoint fixed the 6 mis-tagged Travis rows.
- **False-absentee poisoning (7,573 of 8,536 parcels in 78731).** seed_from_json derived is_absentee against `row['state']`, which defaulted to WA when the onboard call omitted `?state=` (the auto-detect only converted state=="WA", not None) — every TX-resident owner read as out-of-state. Fixed twice over: auto-detect branches handle `state in (None, "WA")`, and `_derive_flags` now TRUSTS seed-provided is_absentee/is_out_of_state (Dallas + Travis builders compute them against the real situs state) instead of re-deriving.

**Ops notes:** onboarding under canon-autofill contention still needs pause/onboard/resume + retries (78731 took 5 attempts across the session; every failure was the transient httpx disconnect at classify/band). The rematch drain got an interruptible idle + `/rematch-autofill-trigger` wake endpoint (single asyncio.sleep(3600) was unwakeable — cost three deploy-restart cycles). New read-only diag endpoints: `/diag/signals-by-source`, `/diag/parcel-by-pin`, `/diag/match-trace` (single-signal pipeline tracer — proved the TX match stack correct when production showed zeros from a deploy-timing artifact).

### 2026-06-11 (cont.) — TOPICs statewide probate harvester + the county-wide inversion

**TOPICs harvester (statewide TX court-side probate discovery).** Texas OCA's "Citations by Publication/Posting" feed at topics.txcourts.gov/CitationsPublic covers ALL 254 counties in one sequential-ID stream (~58/day, 63% probate; no captcha, plain HTTP). Detail page carries cause number + court/county + decedent ("ESTATE OF X, Deceased") + pub dates; the PDF attachment names the APPLICANT (future PR) — extracted via pypdf layout mode. Built `backend/harvesters/topics_citations.py` + `scripts/run_topics_citations.py` (cursor-free: binary-probe live edge, walk back to SINCE_DAYS cutoff; upsert on (source_type, document_ref) makes re-runs idempotent AND re-enriches existing rows) + daily Action at 14:00 UTC. Nonexistent IDs redirect to the search page (don't 404) — existence test is the cause-number CELL having a value. Coverage caveat: publication/posting subset skews heirship/unknown-heirs (~15% of Dallas probate volume); testate-with-executor underrepresented. New TX markets onboard by adding a COUNTY_MARKETS entry + matcher SOURCE_MARKET_SCOPE entry.

**The county-wide inversion (architecture change, Jeremy-approved).** Both TX probate channels initially yielded ZERO in-ZIP matches — diagnosed as coverage math, not bugs: 4 live ZIPs = ~31K of 862K county accounts (1.2%); county-wide death signals filtered through that slice ≈ 0/week. Verified the decedents DO own county property we were blind to (BURHOE THOMAS ALLEN EST OF, Irving). The fix: resolve every decedent against the FULL DCAD roll at harvest time (`scripts/lib_county_resolve.py` — token-indexed 860K-account index, ~14s build, runs in the Action where the DCAD zip lives via weekly actions/cache). Resolution requires surname + FIRST given name (first-name anchor added after catching false positive: Billy Ray Garner vs GARNER JOHNNY RAY on shared middle name). Resolved parcels attach to raw_data; matcher gained Layer 0 (parcel-identity match when a resolved acct is in a live ZIP — strict only if unambiguous: est_of / strong / single-hit; common-name multi-hits are weak) and Layer 0.5 (heir-identity, weak, from resolving the applicant/PR). **County resolution outranks fuzzy matching:** when the resolution marker is present, legacy Layer-1 surname fuzz is SKIPPED — the roll is authoritative about what a decedent owns. This killed 4 verified false-positive strict matches (Denise Owen→strangers named Owen; the WA-tuned COMMON_SURNAMES list mis-grades TX names). `rematch-reset-scoped` now also DELETES stale match rows for in-scope signals (reset alone left invalidated matches live). Rule 6 extended for TX in briefings.py: TX sources carry the PR in the signal itself — family-looking applicant → family_pr_identified; corporate/attorney pattern → unworkable_pr; none → no_pr_yet. Resolution rates: TOPICs 23/37 (62%), recorder 88/144 (61%). Non-live-ZIP resolved parcels in raw_data = expansion intel (e.g. 75214/75218 hits observed).

### 2026-06-11 (later) — Geometry incident + the correct geometry pattern

**INCIDENT: geometry_autofill background task took production down for ~8 hours.** First deployment of a new background task (built to automate per-ZIP lat/lng backfill) starved the single Railway worker's event loop — `backfill_geometry_zip_async` contains sync Supabase calls that ran ON the loop, plus the task's target-picker ran 62 counting queries per tick. Even `/api/health` stopped answering (TLS connected, zero bytes). Recovery: push that default-disables the task (`GEOM_AUTOFILL_ENABLED=0`) + wraps the backfill in `asyncio.to_thread` with an isolated event loop. **Lesson (hard): any new background task must be audited for sync IO on the event loop before deploy, and should ship behind an env gate, default off.** The task is now redundant (see below) — delete in a cleanup pass.

**The correct pattern (Jeremy's call: "why not use the same ingest method as King County"):** coordinates should come from the proven ingest paths, not a parallel backfill machine.

- **Dallas:** the City of Dallas ArcGIS layer has NO situs-ZIP field, so by-ZIP reingest can't work there. Instead: DCAD publishes parcel polygons (`GIS PRODUCTS/PARCEL_GEOM.zip`, EPSG:2276) + condo building footprints (`CONDO.zip`). `build_dallas_owners.py` now computes WGS84 centroids (pyshp + pyproj) and writes `lat`/`lng` INTO the seed; condo-unit accounts (`\d\dC\d{4}...`) take their building's centroid from CONDO.shp. `seed-from-json` already accepts lat/lng (line ~150). Re-seeded all 4 Dallas ZIPs → coverage 75205=92%, 75225=86%, 75230=82%, 75209=96% in one pass, zero new machinery. **Future Dallas ZIPs get coordinates at seed time automatically.**
- **Snohomish gap ZIPs** (recently onboarded, 0% geom): `reingest-property-details?market_key=WA_SNOHOMISH` — the proven endpoint; its parser has always written lat/lng. 98021/98275/98026 → 100%; 98012 → 73% (true ceiling — the Snohomish FeatureServer excludes condos/sub-units, known limitation). Counts refreshed.
- **KC gap ZIPs — PENDING, blocked on KC server outage.** ~20 recently-onboarded KC ZIPs sit at 0-30% geometry (~120K parcels): 98115 98117 98034 98038 98029 98011 98028 98008 98177 98109 98102 98065 98103 98119 98027 98072 98075 98136 98074 98053(partial). The fix is one `reingest-property-details/{zip}` per ZIP — but `gisdata.kingcounty.gov` was DOWN during this session (TLS handshake failure from two networks; Snohomish control worked perfectly, proving the endpoint is fine). **Re-run the KC reingest list when the server returns.** AZ ZIPs have no gap.

Also this session: onboarded **75209** (4th Dallas ZIP, 5,945 parcels, median $1.03M, 350 contact-now leads) → **62 live territories**. Note the recurring onboard bug: register defaulted city to "Bellevue" on 3 of 4 Dallas ZIPs despite the map lookup — repaired each time via `coverage-meta`; root cause in the register path needs a look (active issue).

### 2026-06-11 — Dallas County, TX live (3rd state). Recorder harvester via headless browser.

**The headline:** Texas is now a third market alongside WA and AZ. Built a complete Dallas County recorder harvester end-to-end and onboarded the first three luxury ZIPs (Highland Park / University Park / Preston Hollow). 61 live ZIPs total.

**The access lesson that unlocked it.** Spent the prior session wrongly declaring TX portals "blocked" after raw curl from the sandbox (datacenter IP) hit 403 / Cloudflare challenges. The correction (Jeremy's): the KC scraper works by *rendering like a real browser and reading rendered data*. Re-applied here — a headless Chromium (Playwright) running in a GitHub Actions runner clears the Cloudflare managed challenge where datacenter curl gets 403. **Rule reinforced: portal friction is portal-specific, not market-specific; the public data is in every county. Escalation rungs: (1) form-mechanics-respecting requests, (2) headless browser.**

**Portal recon (GitHub Actions, real browser):**
- Dallas recorder `dallas.tx.publicsearch.us` (vendor: neumo) — real browser CLEARS Cloudflare; renders the Official Records grid as HTML text (no OCR). THE BUILD TARGET.
- Travis `tccsearch.org` — Cloudflare challenge persists even with a real browser (needs stealth/residential IP). Banked as harder.
- Dallas Courts Portal (Tyler) and Travis JP Odyssey — lookup-keyed, no date-filed discovery. The RECORDER is the discovery surface (same as Maricopa).

**neumo query contract (captured live):**
- Results URL: `/results?department=RP&recordedDateRange=YYYYMMDD,YYYYMMDD&searchType=quickSearch&keywordSearch=false&searchOcrText=false`
- Grid columns: GRANTOR | GRANTEE | DOC TYPE | RECORDED DATE | DOC NUMBER (12-digit 20##########) | BOOK/VOL/PAGE | TOWN | LEGAL DESCRIPTION (incl Subdivision/Lot/Block).
- **Pagination: the URL `page=N` param is IGNORED.** Must CLICK the in-DOM control `button[aria-label='next page']` (▶, disabled on last page). 50 rows/page, ~800-900 recordings/day. Verified click advances the grid.
- **Certification lag ~5-7 days** — windows ending at today return 0 rows for the most recent days. Runner trails by `LAG_DAYS=10`.
- **DOC TYPE taxonomy is TX-specific.** The death->property signal is **AFFIDAVIT OF HEIRSHIP** (~2% of daily recordings), NOT "Affidavit of Death"/"PR Deed" (those are AZ/WA names). Confirmed against a 250-row distinct-doctype tally. The decedent is tagged `DECD` and lands in EITHER grantor or grantee column — parser matches the DECD-tagged party as decedent regardless of column.

**Code shipped (all on main):**
- `backend/harvesters/dallas_recorder.py` — render → click-paginate → parse grid text → classify doc type (DEATH_DOCTYPE_SIGNALS, Affidavit of Heirship primary) → DECD-aware `to_signal_row` emitting `raw_signals_v3` (source_type=`tx_dallas_recorder`, jurisdiction=`TX_DALLAS`, party_names[0]=decedent matchable, legal_description as property_hint, doc_number as document_ref).
- `scripts/run_dallas_recorder.py` — Playwright runner: clears Cloudflare once on root, iterates 1-day chunks, click-paginates each, dedupes on doc_number, dry-run default, trails certification lag. ENV: WRITE / DAYS / CHUNK_DAYS / LAG_DAYS.
- `.github/workflows/dallas-recorder.yml` — installs playwright+chromium, dry-run default, daily cron 13:30 UTC (passes write=1), dispatch inputs.
- `scripts/build_dallas_owners.py` — DCAD seed builder. Joins `ACCOUNT_INFO.CSV` + `ACCOUNT_APPRL_YEAR.CSV` on ACCOUNT_NUM; filters DIVISION_CD=RES + PROPERTY_ZIPCODE; same classify_owner_type + 80% address-coverage gate as build_kc_owners.py. **TX is non-disclosure: value = appraised TOT_VAL, tenure = DEED_TXFR_DATE, NO sale_price.** Emits owner_state/city/zip + is_absentee/is_out_of_state + prop_type so the absentee bucket populates without a later reingest.
- `backend/harvesters/matcher.py` — registered `'tx_dallas_recorder': {'TX_DALLAS'}` in SOURCE_MARKET_SCOPE.
- `backend/ingest/seed_from_json.py` — `_MARKET_STATE['TX_DALLAS'] = 'TX'`.
- `backend/api/admin.py` — `DALLAS_ZIP_TO_CITY` map; Dallas auto-detect + seed-prefix `tx-dallas` in register / onboard-zip / seed-path / `_load_seed_names` (5 spots, matching the Maricopa pattern).

**DCAD bulk source:** `https://www.dallascad.org/dataproducts.aspx` → `DCAD2026_CURRENT.ZIP` (207MB, comma-delimited, latin-1). URL-encode the backslashes in the `id=` param or the shell mangles it to a 0-byte download. Key files: ACCOUNT_INFO.CSV (owner/address/legal/deed-date/GIS_PARCEL_ID), ACCOUNT_APPRL_YEAR.CSV (TOT_VAL).

**Value screen (median TOT_VAL):** 75205 Highland Park $2.20M ✓ · 75225 University Park $2.18M ✓ · 75230 Preston Hollow $1.13M ✓ · 75209 $1.03M (borderline, deferred) · 75229 $702K, 75220 $532K (below luxury floor, skipped).

**Onboarding outcome:** all 3 ZIPs live (register→seed→classify→band→publish→refresh_counts all `ok`). Canonicalize deferred/failed on transient Supabase HTTP/2 disconnect — non-blocking (Build Now reads raw structural fields; matcher's `_load_owners_db` reads `parcels_v3.owner_name` directly, not a canonical join). Seed batches hit the same transient `RemoteProtocolError: Server disconnected` (1000-2000 parcels dropped per run); idempotent re-seed to failed=0 fixed it. Band 3 (active prospect): 75205=10, 75225=16, 75230=21. aging_trust contact-now bucket confirmed populating (75205=119 eligible, 75225=129, 75230=137).

**Signal write:** first live recorder run wrote 80 Affidavit-of-Heirship probate signals (window 05/25–06/01, 4,099 grid rows scanned, 0 errors). Matching is QUEUED behind the WA drain — `rematch_autofill` scopes each tick to the market of the OLDEST unmatched signal, and the Dallas signals are newest, so they auto-match once the ~6,500 WA backlog clears. No intervention needed; verify probate buckets after the drain reaches TX.

**Dry-run discipline paid off (caught before any write):** wrong doc-type needles (Affidavit of Death → Heirship), broken URL pagination (→ click-based), the certification-lag date gap, and reversed decedent/heir columns — all surfaced in dry runs.

**Pending for Dallas:** (1) confirm probate match yield into the 3 luxury ZIPs after the WA drain clears; (2) Harris/Houston is the next TX target — find the correct `*.tx.publicsearch.us` recorder host and repeat this pattern; (3) diagnostic workflows (`tx-portal-probe`, `tx-browser-probe`, `dallas-recorder-map`, `dallas-search-capture`) can be removed later.


### 2026-06-10 (cont.) — Enriched seed pipeline, batch canonicalization, all 19 AZ ZIPs staged

**Seed pipeline now carries owner_state / owner_city / lat / lng (commit `cf53e4e`).** `build_maricopa_owners.py` emits MAIL_STATE/MAIL_CITY plus the Assessor layer's WGS84 LATITUDE/LONGITUDE attributes. `seed_from_json.py` passes the new fields through (optional — legacy KC/SNO seeds re-run unchanged), resolves the parcel `state` column from market_key via `_MARKET_STATE` (85254 had been seeded `state='WA'`), and derives `is_out_of_state`/`is_absentee` per row. Net effect: an AZ ZIP needs **no geometry backfill and no Phase-1.5 reingest** — the Issue #14 worker-blocking backfill is unnecessary for this market, and the Snohomish-style absentee=0 hole can't recur.

**Absentee selector generalized (same commit).** `weekly_selector.py` compared `owner_state != 'WA'` (hardcoded) in both the bucket filter and the counts block — AZ absentee was structurally 0. Now compares against each lead's own situs state (`L.get('state')`, fallback WA); `briefings.py` lead shape carries `state`. Verified: 85254 reseeded (19,280 rows, 0 failures) + reclassify + reband → **absentee bucket 0 → 100 (capped)**, 2,565 real OOS owners (CA-heavy).

**Batch canonicalization shipped (commits `8369226` + fixes).** Three admin endpoints replace the 2h-per-ZIP sequential canon drain for bulk onboarding:
- `POST /api/admin/canon-batch/submit/{zip}` (`dry_run=true` supported) — reads the committed seed file, skips pins already in `owner_canonical_v3`, dedupes identical raw names, submits one Anthropic Message Batch (same model/prompt/validator as the real-time path; 50% token discount). AZ ZIPs get a prompt addendum covering Maricopa's surname-first slash co-owner format ("GRABER TAYLOR/AMELIA") which the KC prompt never described — ~35% of AZ names.
- `GET /api/admin/canon-batch/status/{batch_id}` — poll.
- `POST /api/admin/canon-batch/ingest/{batch_id}?zip_code={zip}` — downloads results, validates with the same `_validate_and_normalize`, fans deduped results out to all pins sharing the name, bulk-upserts. Idempotent.

**Required order: seed → canon-batch → onboard.** `owner_canonical_v3.pin` has an FK to `parcels_v3.pin`, so parcels must be seeded first (seeding does NOT make a ZIP live — that needs register+publish). Onboarding after ingest means the orchestrator's canonicalize step finds everything already_done and the ZIP launches Contact-Now-ready. The real-time canon path stays for incremental/drip work.

**All 19 remaining AZ ZIPs seeded into parcels_v3** (247,129 rows, zero failures; 266,409 Maricopa parcels total with 85254). None live yet. Proving batch for 85377 (`msgbatch_01CEL2Su5kgECED3So7TYAuV`, 2,405 unique names) submitted; ingest + slash-format quality check pending, then the other 18 submit in parallel, then onboard all 19.

**Street View is down PLATFORM-WIDE (open, Jeremy-side):** every Street View Static request 403s with "You must enable Billing on the Google Cloud Project" — confirmed on both an 85254 pin and a KC pin (9808100010). Not a code issue; the Google Cloud project behind the Maps key has billing disabled. Fix: enable billing in console.cloud.google.com (no deploy needed), then referrer-restrict the key to sellersignal.co and API-restrict it.

**85254 canon quality note:** it was canonicalized under the KC-only prompt before the AZ addendum existed. Once 85377 proves the addendum, a ~$2 batch re-run of 85254 would upgrade its slash-format parses. Jeremy's call, queued.

### 2026-06-10 — Matcher source→market scoping + 582-row cross-market cleanup (gate for Maricopa 19-ZIP rollout)

Pre-rollout audit found **cross-market match contamination**: the matcher loaded all parcels platform-wide and matched any signal against any parcel by surname, regardless of county. Observed case: Snohomish probate `26-4-01148-31` (decedent Russell, Paula E) matched to a Scottsdale AZ parcel owned by a Russell trust, `trust_level: high`. False-match probability scales with parcel count — a hard gate before adding 19 more AZ ZIPs (~300K parcels).

**Fix (commit `4802086`):** `SOURCE_MARKET_SCOPE` map in `harvesters/matcher.py` — `kc_superior_court`/`kc_treasury` → WA_KING; `wa_state_courts` → WA_SNOHOMISH; `az_maricopa_recorder` → AZ_MARICOPA; `obituary_rss` → WA-wide; **unknown sources unrestricted** (update the map when a new harvester ships). owners_db entries now carry `market_key` (empty → WA_KING, the pre-multi-market default). Candidates filtered post-dispatch in `_process_one`.

**Audit + cleanup (commits `4802086`, `b608296`):** new read-only `GET /api/harvest/diag/cross-market-matches` found **582 violations of 13,912 total matches (4.2%)**: 260 kc→Snohomish, 321 Snohomish→KC, 1 Snohomish→AZ. New confirm-gated `POST /api/harvest/clear-cross-market-matches` (idempotent, recomputes live, returns affected ZIPs) deleted all 582. Re-audit: zero. Coverage counts refreshed on all 28 ZIPs — **every delta was 0 except 98115 (+2)**: the false matches were never in stored Contact-Now counts, so no visible launch-eve drop anywhere.

**Operational lessons:**
- `POST /api/coverage/refresh-counts` with NO zip_code (all-ZIP mode) **blocks the single uvicorn worker and browns out production** (health 000 mid-run) — same class as Issue #14. Use per-ZIP calls (~72s each) with spacing.
- Back-to-back per-ZIP refreshes saturate the Supabase pool (issue #11): during the sweep, 98199's briefing 500'd with broken-pipe repeatedly and looked like a ZIP-specific bug; it was queue-position + pool exhaustion. Recovered untouched once the sweep stopped. Don't diagnose ZIP-specific failures while a refresh sweep is running.
- Within-WA cross-county matches are not 100% provably false (a decedent can own property in an adjacent county), but surname-only evidence across counties is overwhelmingly collision; accuracy-first says scope to county. Jeremy approved deleting all 582.

### 2026-06-10 — Territory map: metro switcher (presentation fix for multi-metro)

With 85254 (Phoenix) now drawable alongside the 28 WA ZIPs, the territory map's single `fitBounds` spanned Seattle→Phoenix (~1,100 mi) — an unusable national view. Fixed in `frontend/src/components/territories/TerritoryMap.jsx` (one file): group live ZIPs into **metros** (keyed off `state` — WA→"Seattle", AZ→"Phoenix"; per-metro bounds come from the actual polygons so each view is tight) and show **one metro at a time** via on-brand pill tabs (top-center, clear of Leaflet's top-left zoom; only rendered when >1 metro exists). Defaults to the agent's own metro if they hold a territory, else the largest. The polygon collection is fetched once and cached in a ref; switching metros re-renders the cached collection (filtered to the metro's ZIP set) and re-fits bounds — no refetch. WA-only behavior is unchanged (single metro → no tabs, same fit). Rebuilt `dist` via `npm run build:safe` (bundle `index-B9wUCmcL.js`; guard confirmed runtime config fetch). Commit `03aa786`. Scales cleanly to future metros (each new market_key's state becomes another tab); if a far-flung *same-state* cluster ever onboards (e.g. Spokane WA), switch the grouping key from `state` to market_key/county.

### 2026-06-10 — AZ geometry backfill: 85254 on the maps (Phase 1 geometry, deferred from 06-08)

Phase 1 onboarded 85254 (Scottsdale) live but **deferred geometry** — the Maricopa seed carried no lat/lng, and the geometry backfill + ZIP-polygon bundle were WA-only. Result: 85254 was live in coverage and the ZIP list but **invisible on both maps**. Two distinct gaps, both closed this session:

**1. Territory map (ZIP boundary polygons).** `/api/zip-polygons` loads committed static bundles at `data/zip_polygons/{state}.json` (Census ZCTA boundaries; props `{zip,lat,lng}`). Only `wa.json` existed → AZ ZIPs had no polygon. Created **`data/zip_polygons/az.json`** with 2020 Census ZCTA polygons for all **20 AZ target ZIPs** (TIGERweb `tigerWMS_Current/MapServer/2`, `outSR=4326`, centroid from `CENTLAT/CENTLON`; 756 KB). `/api/zip-polygons` now returns 29 features incl. 85254. Future AZ onboards already have polygons.

**2. Briefing map (per-parcel pins).** 85254's 19,280 parcels had `lat/lng = NULL`. Added **`AZ_MARICOPA` to `geometry_backfill.MARKET_CONFIGS`** + an isolated `coords_from_attributes` branch in `_fetch_geometry_for_pins`. AZ differs from WA two ways: (a) the Assessor layer geometry is Web Mercator polygons, but it also exposes per-parcel **WGS84 `LATITUDE`/`LONGITUDE` attributes** (exact parcel points) — so we read those directly, `returnGeometry=false`; (b) the layer's **`APN` is undashed** (`16703002`) while `parcels_v3.pin` is dashed (`167-03-002`) — the branch undashes pins for the `APN IN (...)` WHERE and maps each result back to the original dashed pin via an `apn_map`. **WA path byte-for-byte unchanged** (attr_mode=False → original code). Endpoint `/api/admin/geometry/85254` auto-resolved `market_key=AZ_MARICOPA` from coverage and worked unmodified.

Ran the backfill in chunks (`?limit=`): **19,280 → 0 missing, fetched 100%, not_found 0 throughout** (no wrongful geocode_skipped marks — the Assessor endpoint cooperated cleanly from Railway; earlier curl flakiness was local rate-limiting). `/api/map/85254` now returns all parcels with coords; bounds sit tightly on Scottsdale (33.58–33.66, -111.98 to -111.92).

Commit `7813190` (geometry_backfill + az.json). Git note: remote had diverged (Phase 2 harvester commit landed with a different hash + a UI-added workflow), so aligned local via `reset --hard FETCH_HEAD` and **cherry-picked** the AZ geometry commit on top rather than rebasing the divergent harvester commit.

**Operational lesson (logged as Active Issue #14):** the geometry backfill writes **per-pin on the single uvicorn worker**, inside the async handler — so the event loop is **blocked for the whole update phase** (~3–5 min per 1,500-pin chunk). The site returns connection timeouts *during* a chunk and recovers between. Tolerable for one ZIP at low beta traffic, but the remaining 19 AZ ZIPs would be ~19× this. Move the update to a threadpool / background job before the next big geocode. Also note the **bash/client ~5-min ceiling**: `limit=3000` outran the client timeout (server kept processing; no data lost — next call re-fetches remaining nulls). `limit=1500` is the safe chunk size.


### 2026-06-08 — Maricopa County (AZ) Phase 1: first out-of-state market; 85254 pilot live

First market outside Washington. Validates that the downstream pipeline (matcher,
canonicalizer, selector, briefings, dossier, orchestrator) is genuinely source-agnostic —
only the seed builder + market wiring are net-new. Commit `6256bfe`.

**Strategy.** Per Jeremy: best 20–30 ZIPs per market, then move on (not full-county, not
dynamic). WA (28 KC+Snohomish ZIPs) is now a finished area; Maricopa is next.

**Structural finding.** In WA, pressure events are *litigated* (court portals). In AZ they are
*recorded* (County Recorder). The Recorder — not the court — is the primary signal-discovery
surface, and it's KC-class or better: the Document Search supports **document-code + date-range
discovery** (e.g. all "Notice of Trustee Sale" in a window). The Superior Court docket is
name/case-number only (no date/type discovery) — so divorce is the one signal genuinely harder
than KC; eviction (Justice Courts, name-only, targets landlords) is low-value in luxury ZIPs.
Full analysis in `MARICOPA_FEASIBILITY.md`.

**Parcel layer (richest of the 3 markets).** Maricopa County Assessor Parcels MapServer
(`gis.mcassessor.maricopa.gov/.../Parcels/MapServer/0`) carries owner-of-record (`OWNER_NAME`),
value (`FCV_CUR`), inline `SALE_DATE`/`SALE_PRICE` (tenure — no SCOPI-style autofill needed),
`MAIL_*` vs `PHYSICAL_*` (absentee), `PUC`+`LC_CUR` (prop_type), and `LONGITUDE`/`LATITUDE` as
columns (WGS84 — no geometry backfill, no reprojection). Web Mercator layer (102100).

**Locked target ZIP set (20).** Flagship anchors fixed regardless of formula (85253 Paradise
Valley, 85331 Cave Creek, 85262 Desert Mountain, 85377 Carefree); the rest by median price ×
sales velocity with SFH dominance required (85255/85254/85018/85259/85266/85260/85028/85054/
85050/85085/85268/85298/85249/85207/85284/85086). Condo cores (85251 Old Town, 85016 Biltmore)
screened out. Full list + values in `MARICOPA_FEASIBILITY.md`.

**Code shipped (commit `6256bfe`).**
- `scripts/build_maricopa_owners.py` — seed builder, mirrors `build_snohomish_owners.py`. Filters
  `PHYSICAL_ZIP`, composes street from `PHYSICAL_STREET_*`, parses `FCV_CUR`/`SALE_*`, 80%
  address gate. Output `data/seeds/az-maricopa-{zip}-owners.json`.
- `backend/api/admin.py` — `MARICOPA_ZIP_TO_CITY` (20 ZIPs); `onboard_zip` auto-detects Maricopa
  → `market_key=AZ_MARICOPA`, `state=AZ`, `az-maricopa-` seed prefix (same opt-out shape as
  Snohomish); `seed-from-json` dispatch extended.
- `backend/harvesters/matcher.py` — `AZ_MARICOPA` added to the prop_type market-aware default
  (`final_pt='R'`); Phase-2 forward-compat (Maricopa PUC `01xx`=SFR/R, `07xx`=condo/K).
- NOT needed: arcgis.py MARKET_CONFIGS (orchestrator seeds from JSON, not ArcGIS ingest),
  geometry_backfill config (lat/lng inline), canonicalizer rules (market-agnostic).

**85254 pilot — LIVE.** Bare `POST /onboard-zip/85254` exercised the auto-detect (zero params →
AZ_MARICOPA/Scottsdale/AZ). register→seed→classify→band→publish→refresh_counts all ok. 18,280
parcels; archetypes (trust_young 4,755, individual_settled 3,055, llc_investor_early 1,918, …);
bands (Band2=1,255, Band2.5=179); **1,229 Build Now leads** (trust 76, LLC 100-cap, tenure
100-cap). call_now/probate/divorce=0 (Phase 2). absentee=0 (seed omits owner_state — Phase-1.5
reingest, same as Snohomish launch; `MAIL_STATE` is in source).

**Known transient hits (issue #11 contention, not AZ bugs):** seed dropped ~2,000 parcels
(batches 2,8 "Server disconnected"; 17,280/19,280 — idempotent re-fire recovers); canonicalize
failed on the same disconnect (`live_canonicalize_failed` end state; irrelevant to Phase 1 — no
court signals to match — retry when Phase 2 lands).

**Phase 2 (next, not built).** Recorder harvester: doc-code+date pulls for Notice of Trustee
Sale (foreclosure) + Affidavit of Death/Succession + PR Deed of Distribution (death/estate, PR
named on the recorded instrument). Divorce court-bound (name-only). Tax via Treasurer delinquent
list (annual, $25 FTP). Then port the other 19 ZIPs (repeat: build seed → onboard, one at a time).

### 2026-06-02 — Brand voice prompt fix + My Leads letter badges + /letters page + daily email digest


Five-part session. Started as one bug fix (letters referencing "2024" as the year to sell and "spring" as the time to list), grew into three new features for surfacing letter activity to the agent.

**Brand voice prompt fix (commits `6edf74e`, `09da575`)**

Jeremy spotted multiple letters in his SixLettersModal preview that referenced "If 2024 becomes the year you move forward" and "families who list in late winter and early spring." Initial grep audit across the codebase came up empty — no hardcoded "2024" or "spring" anywhere. Spent an extended back-and-forth before locating the source: the SixLettersModal's frontend code first tries `profile.generated_scripts[archetypeKey].letter_sequence` (the Anthropic-generated brand voice content stored on the agent profile), falling back to the static templates in `frontend/src/lib/sixLetters.js` only when missing. The stale content was in Jeremy's brand voice content from a generation run that happened when Claude's training data still anchored to 2024 — that JSON got persisted to `agent_profiles_v3.generated_scripts` and replayed on every parcel.

Two fixes:
1. **`backend/agent_voice/prompts.py`** — added a TIME LANGUAGE rules block to `SYSTEM_PROMPT` forbidding calendar years (2024/2025/2026), seasonal "time to sell" claims (spring market, late winter, before year-end), and absolute positioning ("first quarter", "as we head into [period]"). Plus added 13 new regex patterns to `_BANNED_REGEXES` so future regenerations trigger retry if the model slips. Smoke-tested: all 7 of Jeremy's actual offending strings get caught; no false positives on the existing evergreen template language.
2. **`POST /api/admin/regenerate-agent-scripts?email=<email>`** — new admin-key-gated endpoint that fires the same generation logic as the JWT-authenticated `/api/agent/generate-scripts`, but addressed at any agent by email. Refactored the core "read profile → run 6 archetypes → write back" logic into a shared `run_generation_for_user(user_id)` helper that both endpoints call. Used immediately to regenerate Jeremy's scripts: 6/6 archetypes succeeded in 121s, ~50K tokens, all output passed the stale-time audit. Reusable for any future prompt iteration without needing each agent to manually click Regenerate.

**Feature A — My Leads letter badges + filter chips (commit `3819e41`)**

Prereq dependency surfaced during scoping: today, starting a sequence or sending a single letter does NOT write to `lead_interactions_v3`. That table only got touched on manual "Mark mailed" clicks in the dossier. Consequence: parcels with active sequences didn't appear in My Leads automatically until the agent manually engaged. Wrong — sending outreach IS engagement. Fixed inside the same commit: `send_letter` and `start_sequence` now both write a `mailed` interaction row at success, best-effort (don't refund on stamp failure since the letter is already on the wire). `'mailed'` isn't in `_FUNNEL_STATUS_EVENTS` so it doesn't override existing 'working' / 'listing_discussion' statuses — purely promotes to engaged_pins for My Leads visibility.

After the prereq, `GET /api/my-leads` gains Step 4.5 that aggregates `letters_sent_v3` per active pin. New per-lead fields: `letters_{sent,delivered,scheduled,returned,failed}_count`, `letter_last_status`, `letter_last_status_at`, `letter_next_scheduled_at`, `letter_next_scheduled_within_week`, `sequence_active`. New top-level `letter_filter_counts` block so the UI can hide zero-hit chips. One round-trip to letters_sent_v3, no N+1.

Frontend MyLeadsPage gains:
- `LetterBadge` component — priority-ordered single badge in the right meta column. Returned > Failed > Delivered > Sent > Scheduled. Color tones via existing CSS tokens (--alert, --success, --accent, --text-tertiary). Hover surfaces full count breakdown via the native title tooltip.
- New "Letter activity:" filter chip row above the existing tag-filter row. Six chips: Returned · Failed · Delivered · Sent · Scheduled this week · Sequence active. Multi-select; AND with existing tag filters. Only renders chips with count > 0 so the row stays honest.

**Feature B — Dedicated /letters page (commit `4b44ea9`)**

New `GET /api/letters/sequences-by-agent` returns every sequence (and standalone single-send wrapped as a 1-letter "sequence") for the calling agent. One round-trip: pull all letters_sent_v3 for agent, all letter_sequences_v3, and all touched parcels — bucket in Python by sequence_id, with `sequence_id=NULL` becoming its own group keyed by the letter id. Per bucket: status counts, latest non-scheduled event, next scheduled date. Top-level `filter_counts` and `totals` for header metrics.

Frontend `LettersPage.jsx` at route `/letters`:
- Header showing totals ("X sequences · Y sent · Z delivered · ...")
- Filter chip row: Has returned · Has failed · Has delivered · Active · Scheduled pending · Completed · Cancelled. Same tone styling as My Leads.
- Sortable table (v1: sorted newest-started first; column-click sort is a follow-up). Columns: Parcel · Owner · Started · Progress · Latest event · Next scheduled · Actions.
- **Six-dot progress indicator** color-coded: green = delivered, gold = in-transit, red = returned/failed, hollow = scheduled.
- Per-row actions: View (navigates to `/zip/{zip}?pin={pin}` opening the dossier) and Cancel (confirm dialog → `POST /letters/cancel-sequence/{id}` → refresh). Cancel button suppressed for standalone single-sends (by the time we have the row, the letter is in transit at Stannp) and for already-completed/cancelled sequences. Status pill shows "Single send" vs "Active" to make the distinction clear.

Nav: new "Letters" link in both desktop and mobile menus, between My Leads and Profile.

**Feature C1 — Daily letter activity email digest (commits `71744bf`, schema `030`)**

`backend/tasks/letter_digest.py` — hourly tick that fires at 07:00 America/Denver. Per agent with letter events with `status_updated_at` in the prior 24h, sends a single email summary. Sections in action-priority order: Delivered (recipient has the letter; follow-up window opens) → Returned (verify address) → Failed (Stannp couldn't print/mail) → Mailed (informational). Each parcel listed with owner + address + city/state + letter index.

Idempotency: `agent_profiles_v3.letter_digest_last_sent_at` (schema 030) stamped after successful send. Each tick compares its date in America/Denver to today's date in the same timezone — if same, skip. Stamp ONLY on send so no-activity days don't prevent a late status_updated_at near 7am from being included next morning. Hourly + idempotency gives forgiveness across Railway restarts and slow ticks crossing the send window.

Activity-only: no email if no events. Subject pluralizes correctly: "SellerSignal — N letter update(s) yesterday."

Disabled-safe: skips silently if RESEND_API_KEY isn't set, if Supabase is unavailable, or if the agent has no email column populated. Loop still runs so an env update flips it on without redeploy. Off-hour ticks log at DEBUG so production logs stay clean.

v1 timezone: hardcoded to America/Denver for every agent. Per-agent preference is a future iteration; tracked in active issues below.

**Schema migration applied this session:**
- `schema/030_letter_digest_timestamp.sql` ✅ applied — adds `letter_digest_last_sent_at TIMESTAMPTZ` to `agent_profiles_v3` with `IF NOT EXISTS` so it's safely re-runnable.

**Lessons / patterns reinforced**

- When a bug is "I can't find this string in the code," the source is probably persisted data, not code. Brand voice content is stored in the database, not the codebase — same shape for any future LLM-generated copy that ships once and gets reused.
- The prereq pattern: a feature spec that looks self-contained ("show letter status badges") can fail without addressing an upstream invariant ("does the lead even appear in the list?"). Always trace the data flow end-to-end before assuming the spec is closed.
- Hourly-tick + idempotency-stamp > daily-tick. The latter is fragile to deploys, missed ticks, and timezone DST transitions. The former gives forgiveness for all three.
- Tone-aware filter chips are a reusable pattern across My Leads and the new /letters page. Worth extracting into a shared component if a third surface needs them.

---

### 2026-05-22 to 2026-06-01 — Gap period (not journaled in detail)

Substantial work landed in this window that wasn't captured in the manifesto at the time. High-level recap so the journal isn't misleading; per-commit detail lives in git log.

- **Stripe territory subscriptions** — $299/mo per ZIP with 90-day commitment, operator bypass, Stripe Customer + Subscription wiring (`stripe_customer_id` migration 025). Renewal-notifier background task (`backend/tasks/renewal_notifier.py`) with T-30/T-7/T-1 email reminders via Resend; idempotent per (territory, window) via `renewal_notified_{30d,7d,1d}_at` columns.
- **Mobile responsiveness** — full pass on briefing, territories, leads, dossier, signup, login pages.
- **Lob → Stannp direct-mail migration** — complete replacement of Lob with Stannp Growth tier ($0.69/letter cost + $48/mo SaaS amortized). Migrations 027 (`letters_provider`), 028 (`letter_scheduled_status`), 029 (`letter_method_stannp`). New `backend/services/stannp_client.py` (HTTP basic auth, multipart PDF upload, typed exceptions, retry-on-5xx). Pricing locked at $1.99 single / $9.99 sequence. Webhook handler at `/api/letters/stannp-webhook` mapping Stannp events (letter.created/printed/dispatched/delivered/cancelled/failed/returned) to row status updates.
- **PDF rendering engine swap (WeasyPrint → xhtml2pdf)** — WeasyPrint required libgobject system libs that Nixpacks couldn't reliably install on Railway. xhtml2pdf is pure-Python, no system deps. Renderer rewritten to use flat HTML + element-only CSS (xhtml2pdf's class-selector support is weaker than assumed). Logo dropped (xhtml2pdf SVG rendering too poor) — planned re-introduction as PNG.
- **Letter scheduler** — new `backend/tasks/letter_scheduler.py` ticks every 6h for scheduled letters past their `stannp_send_date`. Replaces Lob's native `send_date` feature; Stannp doesn't have built-in scheduling.



### 2026-05-21 — Bug sweep: letter templates, dossier framing, map data, Snohomish probate

Jeremy ran a "bug man" walkthrough across the live ZIPs. Eleven distinct issues reduced to six root-cause buckets; all six resolved in one session. 11 commits, 1 schema migration, 2 new admin endpoints, multiple data-side operations. Net visible impact: 98290 went from 0 probate leads to 12; 98020 absentee bucket went from 0 to 100 (cap); 98053/98074 maps now show tightly-bounded dots instead of scattering across Seattle/Bothell/Snoqualmie.

**E. Letter template substitution (commit `d9b8bc0`)**

Dossier's "What to Say" section and the 6-letter modal preview both rendered with literal `[your name]` and `[your brokerage]` strings showing through. `archetypePlaybooks.js → resolveDefaultScripts` filled the lead-specific curly-brace tokens (`{owner_first}`, `{address}`) but not the agent-specific bracket placeholders. Added a second substitution pass for `[your name]` → `profile.full_name` and `[your brokerage]` → `profile.brokerage`. Option-b fallback: if either profile field is empty, the literal placeholder stays visible (signals the agent to fill in their profile rather than silently signing letters with no name). The actual Lob-sent letter uses a different code path (`letter_content.py` → renderer appends agent signature) and was never affected — bug was in-app preview only. Also confirmed `sixLetters_probate_v2.js` / `sixLetters_trust_v2.js` are orphaned (no imports) — separate cleanup candidate.

**A. Obit dossier framing (commit `869d741`)**

98020 lead 1 and Paul S Fletcher (98074) both showed correct "Obituary X months ago" header but the dossier body rendered with divorce-archetype framing ("divorce filed", etc.). `detectArchetype` had no `obituary` case anywhere — not in `preferredSignalType` override, not in default precedence, not in `ARCHETYPES`. When an obit lead's parcel also carried a divorce signal, divorce won by default and the dossier body framed the wrong signal type.

Stop-the-bleeding fix per Jeremy's pick of option C: route obit to the `general` archetype. The lead row header still says "Obituary X ago" via signal_type; the dossier body just stops pretending an estate filing or divorce is in play. Generic "I work with homeowners in {city}" framing instead. Three edits: `archetypePlaybooks.js` adds `preferredSignalType === 'obituary'` override case AND a default-precedence obit check ABOVE divorce (so obit+divorce parcels stop showing divorce framing even without an active bucket filter); `BriefingPage.jsx` extends the bucket→preferredSignalType chain with the obituary case.

Proper fix (own `obituary` archetype with condolence-respectful scripts that don't pretend an estate filing exists) is queued — needs Jeremy's eyes on copy. Tax_foreclosure has the same shape problem and same workaround applies — not in today's bug list but worth knowing.

**B. Map pins broken across three new ZIPs (commits `1233bff`, `37fab3a`, `2301651`)**

Three different symptoms on three ZIPs, three different root causes:

  - **98020 — no dots at all.** Geometry never backfilled because `geometry_backfill.py` `MARKET_CONFIGS` only had `WA_KING`. The Snohomish ingest two days ago landed parcel rows but the geometry backfill module had no way to call Snohomish ArcGIS, so `/api/admin/geometry/98020` silently used the KC URL and no-op'd. Added `WA_SNOHOMISH` market config (URL: `services6.arcgis.com/.../Parcels/FeatureServer/0/query`, pin field: `PARCEL_ID`). Same change unblocks all future Snohomish ZIPs. Also made the admin endpoint auto-resolve `market_key` from `zip_coverage_v3.market_key` so calling `/api/admin/geometry/98020` doesn't silently default to WA_KING again. Then ran the backfill: 100% (1602/1602) in 5 calls of 500.
  - **98053 — dots all over Seattle / Snoqualmie.** Two stacked problems: (a) only 4% geocoded initially (backfill never finished), and (b) of the geocoded ones, 41.6% sat 25+ miles outside the real 98053 boundary — KC source data tags some parcels with ZIP5=98053 whose geometry sits in Seattle, Bothell, Woodinville. Fixed both: ran more backfill passes (climbed to 64.9% before plateauing on stuck PINs — see C below), then shipped a bbox-outlier filter at `/api/map/{zip}` and `/api/map/{zip}/bounds` that drops parcels >5 miles from the ZIP's median centroid. Filter sized to keep legitimate annexes (Sahalee, Cottage Lake, Union Hill for 98053) while catching cross-ZIP leakage. Tightened from initial 10 mi to 5 mi after data showed the 10-mi threshold left too much nearby contamination.
  - **98074 — dots outside Sammamish boundary.** Same shape as 98053 but milder (4.3% off-bbox after wide-bbox filter). Same fix applies — bbox filter handles it.

`schema/024_geocode_skipped.sql` added during this work. The geometry backfill had a poisoned-queue pattern: when KC ArcGIS has no record for a PIN (retired parcel, condo unit, recently subdivided), the fetch returns nothing and the row stays at NULL lat/lng — so the same stuck PIN sits at the top of the queue every call, gets re-tried, fails again. Saw this on 98053 converging to ~8 new geocodes per call because ~492 stuck PINs were blocking the queue. Per the April lesson on poisoned-retry architecture (case_parties_v3 sentinels), DO NOT co-locate failure state with truth data. Added a small `geocode_skipped BOOLEAN NOT NULL DEFAULT FALSE` column with a partial index on `(zip_code) WHERE skipped=FALSE AND (lat IS NULL OR lng IS NULL)`. Geometry backfill now marks not-found PINs as skipped after each batch and filters them out of subsequent runs. Defensive — code falls back to the legacy unfiltered query if the migration hasn't been applied yet, with a one-time warning. After applying: 98053 → 90.9%, 98074 → 91.6%, both at their true ceiling (remaining missing are genuinely not in KC source).

**C.1. 98290 zero probate matches (commits `fcf6900`, `10a3013`, `ff0f168`)**

98290 had 0 probate matches despite 15,394 parcels and 183 Snohomish probate signals harvested. Investigation: `/api/harvest/admin/zip-quality-score/98290` reports `prop_type_eligibility_pct=0%` (eligible=0, total=15436). The matcher's `_dispatch_probate` rejected every 98290 parcel at the prop_type filter before name matching ran.

Initial hypothesis (owner-name corruption — sampled a few weird "Of Snohomish City" strings) was wrong; Q2 SQL showed 98290 owner names are actually slightly cleaner proportionally than 98020 (63% vs 59% in clean First-[Middle]-Last format). The real cause was prop_type: Snohomish County's parcel layer doesn't expose KC-style single-char codes (R/K). The existing `or 'R'` default in `_load_owners_db` only handles falsy values — whatever's stored in 98290's `prop_type` column passes the truthy check but doesn't equal R or K after `upper().strip()`, so the matcher rejects all 15,394 parcels before name matching runs.

Fix: market-aware default in `_load_owners_db`. When `market_key='WA_SNOHOMISH'`, default unrecognized prop_type values to 'R' (the matcher's name + HOA + government filters still gate non-residential candidates downstream). KC parcels with legitimate non-R/K codes (commercial, exempt) flow through unchanged — `_is_eligible_prop_type` filters them correctly. Also added `market_key` to the `parcels_v3` select in `_load_owners_db`.

Truth-test confirmation: 8 matches → 93 matches (98290 specifically 0 → 70). Production matcher needed an unblock — the 191 signals were already marked `matched_at` from a prior run, so `run-matcher-snohomish-real` (which filters by `matched_at IS NULL`) saw 0 in scope. Built `/api/harvest/rematch-reset-scoped` as a targeted alternative to the global `/rematch-reset`: takes `source_type` + `signal_type` query params, resets only matching signals' `matched_at` to NULL. Fixed one own-goal during build — `match_count INTEGER NOT NULL DEFAULT 0` rejected `match_count=NULL`, so the first batch silently failed. Changed to `match_count=0`. After fix: 191 reset → 93 matches written → coverage refresh → 98290 probate **0 → 12** in the Call-Now bucket (70 raw matches; 12 made it through the family_pr_identified + freshness gates). 98020 also gained 5 (19 → 24) — the broken filter was over-rejecting some KC parcels too.

**C.2/C.3. 98053/98074/98020 absentee zero (reingest + refresh-counts)**

98053 had `contact_now_absentee=0`; 98074 had 1; while 98004 baseline had 100 (cap). Root cause: when these ZIPs were onboarded via `seed-from-json` (the bulk-CSV path), the seed file contained `owner_name, address, value, tenure_years` but NOT `owner_state`. The absentee bucket selector at `weekly_selector.py:803-804` requires `owner_state IN _VALID_US_STATES AND owner_state != 'WA'`. Empty/null `owner_state` → excluded → zero count. 98004 was seeded earlier via a path that did include owner_state, hence 100 absentees.

Fix path was already in the codebase: `POST /api/admin/reingest-property-details/{zip}` backfills `owner_city`, `owner_state`, `is_absentee`, `is_out_of_state` from live ArcGIS. Ran for 98053 (8589 upserted), 98074 (10394 upserted), and 98020 with `market_key=WA_SNOHOMISH` (8351 upserted — note 98020 had 1602 in seed; reingest added ~6750 new parcels because live Snohomish ArcGIS has more parcels for SITUSZIP=98020 than the seed captured — side effect worth knowing). Then `POST /api/coverage/refresh-counts?confirm=true&zip_code={zip}` updated bucket counts.

Result: 98020 absentee 0 → 100 (capped). 98053 0 → 2. 98074 1 → 2. The low 98053/98074 numbers verified via SQL: the `owner_state` column had ~25-45 distinct non-WA-looking codes including obvious junk like `'00','EA','T7','WE','WS','A','AO','AP'` (KCTP_STATE field truncations / mis-encodings) that `_VALID_US_STATES` correctly rejects. After the junk filter, 98053/98074 have maybe 100-150 real OOS owners but most get swept into higher-priority buckets (trust=100, llc=89, tenure=100 at cap) which run before absentee in the cascade, leaving ~2. Not a bug — that's the bucket cascade working correctly given the actual demographics (Redmond/Sammamish are local-owner-occupied tech-worker zips).

**D. Tax foreclosure leads showing no street address (commit `5e23b37`)**

98074 had 3 tax_foreclosure leads with empty `address` field; dossier rendered as "owner_name + parcel_number" with no street. Diagnosed via direct query against KC's live ArcGIS: **all 3 PINs returned zero features** — they're stale phantom parcels (in our `parcels_v3` from old seed but no longer in KC's live source, typically retired/subdivided/merged). The reingest-property-details endpoint queries by ZIP and these specific PINs aren't returned anymore. One of the 3 (pin 1593001210) is also contaminated — lat 47.50 lng -121.78 is North Bend / Snoqualmie Valley, not Sammamish.

Per Jeremy's pick of option (1): filter addressless leads from the briefing assembler. Added at `briefings.py:304` right after `parcels_v3` fetch: `parcels = [p for p in parcels_all if (p.get('address') or '').strip()]`. Covers every downstream bucket (call_now, build_now, hold, watch) in one place. Underlying `parcels_v3` rows preserved (in case source data ever returns, or other endpoints legitimately need them). Soft-log emits a drop count for observability.

Other three options remain available as future work: (2) reverse-geocode lat/lng → address via Google Maps; (3) show with explicit "(parcel — no street address)" label; (4) admin endpoint to delete stale phantom parcels from `parcels_v3` based on missing-in-source check. (4) is the cleaner long-term cleanup; today's filter is the pragmatic band-aid.

**F. Map key legend "Build now" → "In pipeline" (commit `4d08e1d`)**

Per manifesto's standing rule about "Building" being jargon. One-line label change in `MapPanel.jsx`. Internal category key (`build_now`) unchanged — only the human-facing legend text.

**Lessons from today**

- The poisoned-retry pattern keeps recurring. Today it was geometry backfill (stuck PINs at top of queue) AND the prop_type filter (rejecting everything with truthy non-R/K values). Both fixed surgically. Worth a separate audit pass: are there other places where "we tried and got nothing" is conflated with "we haven't tried"?
- ZIP onboarding has more side effects than the surface API suggests. Reingest-property-details adds new parcels from the live ArcGIS that the original seed didn't include. Geometry backfill needs per-market wiring. Property-detail backfill happens via a different endpoint than name-backfill. The orchestrator covers the happy path but the recovery paths (re-ingest, re-canonicalize, re-match) each have their own gotchas.
- The matcher's prop_type filter is doing legitimate work for KC (filters out commercial / exempt / vacant) but is over-rejecting on Snohomish. Market-aware defaults are now wired into `_load_owners_db`. This pattern will likely apply to any future county-onboarding work.
- Scoped reset > global reset. The global `/rematch-reset` blocks the curl for ~10 min while clearing 16K+ signals across all KC. The new `/rematch-reset-scoped` clears just the affected slice (e.g., 191 Snohomish probate signals in seconds). Reusable for future targeted re-runs.

**New endpoints added today**

- `POST /api/harvest/rematch-reset-scoped?source_type=X&signal_type=Y&confirm=true` — scoped variant of global rematch-reset. Touches only signals matching `(source_type, signal_type)`. Idempotent. Resets `matched_at` to NULL and `match_count` to 0.

**New schema migration applied today**

- `schema/024_geocode_skipped.sql` — adds `geocode_skipped BOOLEAN NOT NULL DEFAULT FALSE` to `parcels_v3` plus a partial index for the backfill query path.

**Net measurable impact**

```
                      Before        After
98020 map dots          0             1602
98020 absentee bucket   0             100  (capped)
98020 probate bucket    19            24
98053 map bbox          17×19 mi      10×8 mi
98053 absentee bucket   0             2
98074 map cleanup       19×18 mi      10×8 mi
98074 absentee bucket   1             2
98290 probate bucket    0             12   ← the big one
Letter templates        broken        substituted
Obit dossier framing    wrong         correct
Tax_foreclosure (addressless)  shown  filtered
Map legend "Build now"  jargon        "In pipeline"
```

### 2026-05-20 (afternoon) — Frontend auth fix + runtime config refactor

**The bug.** Jeremy hit the "Authentication isn't configured in this environment" sign-in screen. Root cause traced to commit `a8cba28` from Monday morning ("Rebuild frontend/dist for dossier filter-awareness fix") — me, in this Claude container, ran raw `vite build` instead of `npm run build:safe`. The Claude container has backend env vars (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, etc.) but NOT the Vite frontend variants (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`). Vite silently inlined `undefined` for both, supabase-js initialized as `null`, every auth call hit a "not configured" fallback. The committed bundle had been auth-broken since Monday morning. Jeremy ran on his cached localStorage session until the access token finally expired this afternoon, at which point the auto-refresh path hit the null client and rendered the sign-in error.

The `frontend/scripts/build-safe.mjs` script existed specifically to prevent this — its docstring says *"This has shipped to production twice in one day"* — but I bypassed it by calling `vite` directly.

**Immediate fix.** Jeremy provided the anon key. Rebuilt with `npm run build:safe` (which verified the URL + JWT prefix were both inlined before allowing commit). Bundle shipped (commit `127cd27`, bundle `index-C4LSwQjQ.js`, 732KB up from 533KB because the supabase-js client was now actually bundled instead of being null). Sign-in worked again.

**Structural fix (commit `895f935`).** Eliminated the failure class entirely by moving Supabase config from build-time injection to runtime fetch. Architecture:

- New backend endpoint `GET /api/config` (in `backend/api/health.py`) returns `{supabase_url, supabase_anon_key}` from Railway env vars. No auth required — the anon key is a public routing token meant to be embedded in every browser; RLS in Postgres enforces real permissions.
- `frontend/src/lib/supabase.js` rewritten: triggers `fetch('/api/config')` at module load, caches result in `localStorage` under key `sellersignal:supabase_config_v1`, builds the supabase-js client from fetched values. 5-second timeout with graceful fallback if the backend is unreachable. Subsequent page loads init instantly from cache while a background refresh handles rare key rotation.
- `frontend/src/lib/AuthContext.jsx` updated: awaits `getSupabase()` in its bootstrap effect; exposes a new `isConfigured` boolean on the context value.
- Four pages updated (`LoginPage`, `SignupPage`, `ForgotPasswordPage`, `ResetPasswordPage`) to read `useAuth().isConfigured` instead of importing the legacy `supabaseConfigured` const. Banner only shows when `!loading && !isConfigured` (avoids a false-positive flash during the brief init window).
- `frontend/scripts/build-safe.mjs` flipped polarity: was verifying credentials WERE inlined; now verifies they are NOT (catches accidental regression to build-time injection). Also verifies the `/api/config` string is present (proves runtime-fetch code path is wired up).
- `frontend/.env.example` updated to document that VITE_SUPABASE_* env vars are no longer needed at build time.

**Net effect.** Any environment — Claude sandbox, dev machine, CI without secrets — can rebuild the frontend and the resulting bundle works in production as long as the backend has `SUPABASE_URL` + `SUPABASE_ANON_KEY` in Railway env. The build-time injection failure mode is structurally impossible going forward, and the guard would catch any regression.

### 2026-05-19 to 2026-05-20 — Snohomish Phase 1: harvester + 98020/98026 launch

**Monday morning — production fixes from Sunday's expansion:**

- 5 newly-onboarded ZIPs (98034, 98115, 98117, 98029, 98053) all had `parcels_v3.city='Bellevue'` because cmd_seed's city default ran before the resolution table lookup. Dossiers were also showing "PROBATE-DRIVEN SELLER" for divorce-driven leads. Fixed both: cmd_seed now consults `zip_coverage_v3.city → KC_ZIP_TO_CITY → SNO_ZIP_TO_CITY → fallback` (commit `9bf67d6`); dossier's `detectArchetype` accepts a `preferredSignalType` opt so a probate parcel viewed under a divorce filter shows divorce framing (commit `a8cba28`). Re-fired `/admin/seed-from-json` for all 5 ZIPs to apply the city correction.
- Auth was throwing intermittent 401s during background-task storms (rematch + canon both saturating Supabase HTTP/2 stream pool). Added retry-once on `RemoteProtocolError`/`ReadError`/broken-pipe in `user_from_authorization` with 250ms backoff (commit `56a82a4`). The deeper fix — dedicated Supabase client per task — is still in the backlog. Auth retry has been carrying production through the recurring contention all session.

**Monday afternoon — Snohomish discovery + architecture:**

- Two Edmonds agents wanted to subscribe. 98020/98026 are Snohomish County (not King). Only Snohomish ZIP live was 98290 pilot.
- Mapped WA court system architecture (now documented in the "WA court system architecture" section above). Critical finding: only King County has its own custom portal. All 38 other counties use the statewide JIS at `dw.courts.wa.gov`, which is reCAPTCHA-gated and has no date+casetype discovery search. **The unlock for non-KC counties:** county clerks publish daily new-case-filing PDFs at predictable URLs — no captcha, no subscription, no auth. Pattern likely generalizes to Pierce, Thurston, Whatcom, Kitsap, and ~38 other WA counties. Strategic moat for cross-county expansion.
- Confirmed case-type catalog from May 18 sample report (see "WA court system architecture" table).
- Documented Phase 1 vs Phase 2 PR enrichment paths. Day-1 probate filings name only the decedent — PR appears in later "Letters Testamentary" filings. Snohomish probate leads launch in `contact_status='no_pr_yet'` state.
- Updated MANIFESTO with all of the above (commit `e450390`).

**Monday evening — Phase 1 code build:**

- `scripts/build_snohomish_owners.py` — mirrors `build_kc_owners.py`. Pulls the Snohomish County Parcels FeatureServer (single endpoint at `services6.arcgis.com/.../FeatureServer/0`) paginated by `resultRecordCount` and `resultOffset` (commit `a017d56`). 98020 and 98026 seed files generated (1,602 + 2,144 parcels). 98290 pilot seed UNCHANGED at 15,436 PINs — the feature service only returned 4,676 (Phase 2 data coverage improvement; condos/sub-units appear excluded by the layer's geographic filter).
- **Classifier bug caught during seed build:** `classify_owner_type`'s "USA" substring pattern was matching inside names like SUSAN, SARAUSAD, MOUSAVI — 43 false-positive individual→company misclassifications in 98020+98026. Fixed `" USA "` to word-boundary in both builders (commit `a2b1dee`). Regenerated seeds. **Carry-over impact:** KC's 21 existing ZIPs have an estimated ~1.1% records platform-wide misclassified individual→company because of this bug. Listed in active issues as a retroactive re-classify task.
- `backend/harvesters/snohomish_daily_report.py` (commit `edf5f5b`) — the harvester core. `fetch_index()` scrapes the landing page for available report dates. `_pdf_to_text()` tries `pdftotext -layout` then falls back to `pypdf`. `parse_report()` walks the columnar PDF text. Two non-obvious bugs caught during local testing:
  - All-caps party names (e.g., "ALVIAR, CHENG JIANG") were being misread as connection codes by a generic `[A-Z]{2,7}` pattern. Fixed by anchoring on the KNOWN connection-code set from `CONNECTION_TYPE_MAP`.
  - TRS Trust cases have `type_code=TRS` AND parties with `connection_type=TRS` (trustee). Leftmost-match regex was picking the type code's TRS as the conn code, eating the entire row as party text. Fixed with `finditer` + take-rightmost-match.
  Tested locally against the May 18 PDF: 217 party rows → 86 unique cases → 17 Tier 1 signals (10 divorce + 7 probate).
- `backend/tasks/snohomish_daily_autofill.py` + orchestrator HARVESTERS dict entry + admin endpoints + `main.py` lifespan registration + `SNO_ZIP_TO_CITY` expansion + orchestrator dispatch (commit `c0817c8`). 24-hour tick interval (Snohomish publishes once per business day), 7-day default lookback. `admin.py:onboard_zip` auto-detects Snohomish via `SNO_ZIP_TO_CITY` membership: uses `wa-snohomish-{zip}-owners.json` seed path and defaults `market_key=WA_SNOHOMISH`.

**Monday night — Railway GCP outage:**

- Google Cloud incorrectly suspended Railway's production account at 22:20 UTC. Multi-hour outage. Webhook integration with GitHub got rate-limited during recovery; Railway's auto-deploy missed all my commits from `e450390` through `c0817c8`. Production stayed on `56a82a4` (auth retry).
- Initial diagnosis path got it wrong: spent ~20min suspecting code issues / webhook delivery problems before Jeremy's screenshot showed the "Limited Access — Deploys paused" banner. Lesson logged: when Railway has no record of recent commits at all and previous commits deployed normally, suspect platform-side first.

**Tuesday morning — outage recovery + Snohomish go-live:**

- Railway resumed deploys for Pro tier first; hobby-tier remained paused while they drained backlog. Project was on hobby; Jeremy upgraded to Pro to unblock. Pro upgrade pulled all 7 queued commits in one build.
- **Discovered missing `pypdf` dependency in production** via Railway logs: `RuntimeError: Neither pdftotext nor pypdf available for PDF extraction` for every report. Local container had `pdftotext` (from poppler-utils) so the fallback never exercised. Fixed by adding `pypdf>=3.0.0` to `requirements.txt` (commit `f86f2cf`).
- Deploy landed. First Snohomish harvest tick fired. Still harvested 0 signals. **Discovered second bug:** pypdf's default `extract_text()` splits each table cell onto its own line — totally different from `pdftotext -layout`'s column-preserved output. My single-line parser regex matched 0 rows on every PDF. Switched to `extract_text(extraction_mode="layout")` which pypdf 4.x+ supports — output is virtually identical to pdftotext (commit `34097e7`). **Lesson:** any new external tool dependency needs a confirmed-on-Railway check, not just a local one.
- **GitHub revoked the PAT** — committed in MANIFESTO.md, auto-detected by GitHub secret scanning. First replacement was a fine-grained PAT without `Contents: write` permission (rejected with 403). Second was a classic `ghp_...` PAT (worked). Active issue: PAT in MANIFESTO is structurally fragile; needs to be moved to Railway env vars.
- **Snohomish harvester first production run** with `since_days_ago=30`: harvested 322 signals, all new, zero errors. ~11/day countywide.
- **Onboarded 98020 + 98026** via `POST /api/admin/onboard-zip/{zip}`. Both ZIPs reached `state=completed` (98020) / `state=live_canonicalize_pending` (98026) within ~40s for the first 6 steps. Canonicalize ran via the canon_autofill task — 98020 done in one pass; 98026 was deferred by the lock but completed during a subsequent autofill tick (the `state=live_canonicalize_pending` label became stale).
- **The matching snag and the rematch dance:** the initial 322 signals were harvested while only 98290 was canonicalized. The matcher processed them once, found 0 matches in 98290 (Lake Stevens), and set `matched_at=NOW`. After 98020/98026 finished canonicalizing, the new canonical owners existed but the signals weren't queued for rematch. Triggered `POST /api/harvest/rematch?confirm=true`. Endpoint deletes all `raw_signal_matches_v3`, resets `matched_at` to NULL, re-runs matcher. Production briefings showed 0 leads during the delete pass (real concern — agents would see empty briefings if they refreshed). Regeneration completed over the following ~5 min. Final state: 98020 had real contact-now leads, 98026 had contact-now leads, KC ZIPs regenerated to their previous match counts.
- **Phase 1 outcome:** first-ever Tier 1 leads in Edmonds. The full daily-report pipeline works end-to-end. Architecture validated for cross-county replication.

### 2026-05-17 — 5-ZIP expansion + orchestrator redesign + canon autofill

**Morning — seed builder + orchestrator redesign:**

- Added `scripts/build_kc_owners.py` — canonical seed builder, committed to repo (commit `ec5344a`). Was previously living in an ephemeral container; not reproducible from repo. New version has 80% address-coverage gate that refuses to write a broken seed file (catches the May 10 bug shape automatically).
- Fixed stale Haiku cost estimate in orchestrator docstring (commit `0e1a5e7`): was claiming $10-15/ZIP, actually ~$4-9/ZIP at current Haiku 4.5 pricing.
- Added 5 new seed files: 98034 (Kirkland/Juanita), 98115 (Wedgwood/Ravenna), 98117 (Ballard), 98029 (Issaquah/Klahanie), 98053 (Redmond/Education Hill). Plus added these to `KC_ZIP_TO_CITY` and fixed missing 98038 → Maple Valley (commit `b377e5f`).
- **Redesigned the onboarding orchestrator** (commit `0a68aa4` + fix `989056a` + tune `ccd830c`):
  - Canonicalize moved off critical path. New step order: register → seed → classify → band → publish → refresh_counts → canonicalize. ZIPs go live in ~30s instead of 30-60min.
  - Added explicit `publish` step. Previously the orchestrator had no publish step; transitions to `live` were done by an undocumented manual `cmd_publish?force=true` call.
  - Added concurrency lock on canonicalize. Only one ZIP canonicalizes at a time per Railway instance. Others mark themselves `deferred` and exit cleanly.
  - Dropped canonicalize concurrency from 10 to 3 after observing HTTP/2 stream pool saturation at conc=10.
  - New state semantics: `live_canonicalize_pending`, `live_canonicalize_failed`, `failed` (pre-publish only).
- **Onboarded 5 new KC ZIPs to live state** sequentially (parallel-N onboarding fails on the HTTP/2 stream pool; this is a real constraint). Total ZIPs: 21 → 26. Added 63,302 parcels. Contact now leads on new ZIPs: 8 already firing before canonicalize completes.

**Afternoon — manifesto + query path + canon autofill:**

- Created **`MANIFESTO.md`** at repo top-level (commit `79e011d`). The handoff manifesto used in past Claude sessions lived only in the project context and was never committed; future sessions cloning the repo had no canonical document. This file is now the single source of truth.
- **Fixed the `?city=` query-param fallback bug** (commit `e4ca29e`). The onboard-zip endpoint had `city: str = "Bellevue"` as a literal default; any operator who forgot to pass `?city=` (or whose curl was misformatted) silently mis-tagged the ZIP as Bellevue. Changed to `Optional[str] = None` with a runtime lookup against `KC_ZIP_TO_CITY` (then `SNO_ZIP_TO_CITY`). This was how 98034 ended up with city="Bellevue" instead of "Kirkland."
- Added **`/admin/coverage-meta/{zip}`** repair endpoint (same commit). cmd_register is intentionally idempotent (insert-only, never updates), so once a row exists with wrong metadata, no pipeline path can fix it. This new endpoint provides a narrowly-scoped "update display metadata" path that only touches city/state/market_key. Used once to fix 98034's city. Kept in the codebase as a general-purpose repair tool.
- **Built `canonicalize_autofill` background task** (commit `d113ee4`). Completes deferred and partial `owner_canonical_v3` work automatically so multi-ZIP onboarding becomes fully fire-and-forget. Two-tier priority: (1) ZIPs flagged by orchestrator state as `live_canonicalize_pending`/`live_canonicalize_failed`; (2) round-robin sweep across all live ZIPs for maintenance. Uses the same `_CANONICALIZE_LOCK` as the orchestrator. Admin endpoints: `GET/POST /api/harvest/canonicalize-autofill-{status,pause,resume}`. Wired into `main.py` lifespan as the 6th background task.

### 2026-05-16 — KC seed file address-bug fix

The 6 May 10 seed files (98074/98075/98077/98119/98072/98027) had 0% address coverage due to a bug in the ad-hoc build_kc_owners.py used that day. Fix: re-ran ArcGIS ingest on the 6 ZIPs to backfill addresses from `ADDR_FULL`. Addresses jumped to 66-83% (the cap is real KC data gaps — vacant lots, condo common areas, parcels without ADDR_FULL). The seed JSON files in the repo were never regenerated and still have address="" for those PINs — the 2026-05-17 commit of `build_kc_owners.py` makes regeneration possible if ever needed.

### 2026-05-10 — 6 KC ZIPs added

Added 98074, 98075, 98077, 98119, 98072, 98027 via the OLD pipeline (sequential per-ZIP register/ingest/seed/reclassify/reband/publish, then a single canonicalize-all across all 6). Sale-match rates 82-99%, addresses 0% (the bug above, found six days later).

### 2026-05-09 — ZIP onboarding orchestrator built; 98038 onboarded as pilot

Created `backend/tasks/zip_onboarding.py` to replace manual 8-15 endpoint sequencing. First ZIP through the new orchestrator: 98038 (Maple Valley). Orchestrator had no publish step at this point — transition to `live` was a manual cmd_publish call after the orchestrator completed.

### 2026-05-01 to 2026-05-08 — Cross-county pilot

Added 98290 (Snohomish County) as the cross-county test. Required a new `WA_SNOHOMISH` market_key with its own canonicalizer rules. Validated the architecture works outside KC. See `docs/SESSION_END_2026-05-01.md` (older but still accurate for that window).

### 2026-04-30 — Multi-ZIP investigation resolved

The April 29 investigation (only 98004 had Contact now leads; other 10 ZIPs had 0) resolved. Root cause: cumulative effects of the partial-success scraper rate combined with sentinel-poisoning. Resolution path: ran `clear-sentinel-parties` to wipe the 1,092 poisoned rows, then let autofill re-attempt them with the rebuilt `kc_court_participants` scraper. Multiple ZIPs started producing leads within hours.

### 2026-04-26 to 2026-04-28 — Slice C: archetype dossier + Lead Memory

Added archetype-driven dossier (5 archetypes + general fallback), Lead Memory persistence (`schema/011_lead_interactions.sql`), cold-visitor gate.

### 2026-04-24 to 2026-04-26 — Slice B: action-first briefing

Briefing redesign: header oracle line, action list, pipeline, watch list. Eligibility Contract Rule 6 (family_pr_identified required for Contact now probate).

### 2026-04-22 to 2026-04-23 — Harvester layer

KC Superior Court harvester. Phase 1.5: personal representative extraction (the case-parties scraper). Matcher with surname-required gate. Multi-source obituary harvester.

### 2026-04-19 to 2026-04-21 — Genesis

Project bootstrapped from v1 archive. Owner canonicalizer + classifier. ArcGIS ingest. Supabase schema 001-002. Frontend skeleton. First admin endpoints.

---

## Active issues / known cracks (May 20, 2026)

These are tracked here so they don't get lost. None are production blockers.

### 14. Geometry backfill blocks the single worker (event-loop stall during updates)

`backend/ingest/geometry_backfill._bulk_update_coords` writes lat/lng **one PIN at a time** with the synchronous Supabase client, called (un-awaited) from inside the async `backfill_geometry_zip_async` handler. With one uvicorn worker, the event loop is blocked for the entire update phase, so `sellersignal.co` returns connection timeouts *during* each chunk and recovers between (observed 2026-06-10 backfilling 85254 — `health=000` mid-chunk, `200` between). Tolerable for a single ZIP at low beta traffic; **not** acceptable for the remaining 19 AZ ZIPs (~19× the volume) or any future large county.

Fixes available (pick before the next big geocode):
- **(a)** Run `_bulk_update_coords` in a threadpool (`await asyncio.to_thread(...)` / `run_in_executor`) so the event loop keeps serving requests during updates. Smallest change.
- **(b)** True bulk upsert — batch the lat/lng updates into a single PostgREST upsert per N rows instead of per-PIN (also cuts wall-clock from ~0.15 s/PIN to seconds per batch).
- **(c)** Move geometry backfill to a background task (like the autofills) with a status endpoint, so the HTTP call returns immediately.

Also: keep geometry chunks at `?limit=1500`. `limit=3000` outruns the ~5-min client/bash timeout (the server keeps processing and finishes; no data lost since the next call re-fetches remaining null pins, but the client gets no response).

### ~~1. `?city=` query param not flowing through to register~~ **RESOLVED 2026-05-17**

Was: 98034 onboarded with `?city=Kirkland` ended up with `city="Bellevue"` because the endpoint default was a literal "Bellevue" and an earlier curl misformat dropped the query param. The pipeline then no-op'd on re-fire because cmd_register is idempotent.

Fix: endpoint signature changed to `city: Optional[str] = None` with runtime lookup against `KC_ZIP_TO_CITY`/`SNO_ZIP_TO_CITY`. Added `/admin/coverage-meta/{zip}` repair endpoint for the existing-row data fix. 98034's row corrected to Kirkland. Commit `e4ca29e`.

### ~~2. No canonicalize_autofill background task~~ **RESOLVED 2026-05-17**

Was: When 3+ ZIPs were onboarded sequentially, only the first one's canonicalize ran to completion; the others landed in `live_canonicalize_pending` and stayed there indefinitely without manual orchestrator re-fires.

Fix: built `backend/tasks/canonicalize_autofill.py`. Two-tier priority (orchestrator-flagged ZIPs first, then round-robin sweep), uses the same `_CANONICALIZE_LOCK` as the orchestrator. Admin endpoints at `/api/harvest/canonicalize-autofill-{status,pause,resume}`. Multi-ZIP onboarding is now fully fire-and-forget. Commit `d113ee4`.

### ~~3. MANIFESTO.md was previously not in the repo~~ **RESOLVED 2026-05-17**

Fixed by commit `79e011d`. This file is now the source of truth.

### ~~4. cmd_seed default city set to 'Bellevue'~~ **RESOLVED 2026-05-18**

5 newly-onboarded ZIPs (98034, 98115, 98117, 98029, 98053) all had `parcels_v3.city='Bellevue'` because cmd_seed's default ran before the resolution table lookup. Dossiers also displayed "PROBATE-DRIVEN SELLER" on divorce-driven leads. Fixed both: cmd_seed now consults `zip_coverage_v3.city → KC_ZIP_TO_CITY → SNO_ZIP_TO_CITY → fallback` (commit `9bf67d6`); dossier's `detectArchetype` accepts a `preferredSignalType` opt so filter-mismatched probate parcels show divorce framing (commit `a8cba28`).

### ~~5. Snohomish daily-report harvester not built~~ **RESOLVED 2026-05-19/20**

Snohomish County onboarding required a different court-signal pipeline from KC's. Built `scripts/build_snohomish_owners.py`, `backend/harvesters/snohomish_daily_report.py`, `backend/tasks/snohomish_daily_autofill.py`, plus orchestrator dispatch + admin endpoints (commits `a017d56`, `edf5f5b`, `c0817c8`, `f86f2cf`, `34097e7`). 322 signals harvested on first 30-day run. 98020 + 98026 launched. First Tier 1 leads in Edmonds.

### 6. canonicalize_autofill round-robin sweep overhead (~32 min per full cycle)

Per-tick, the autofill task picks one live ZIP and calls `backfill_zip` on it. Even on fully-canonicalized ZIPs, backfill_zip does a global canonical-PIN fetch (~30s on the current ~250k-row table) before discovering there's nothing to do. With 28 live ZIPs that's ~32 min for a full idle sweep. Round-robin also doesn't yield to recently-deferred ZIPs effectively — observed 2026-05-20 when 98026 stayed at canonicalize=deferred while autofill spun on already-completed KC ZIPs. **The canon work still completed** (98026 done within ~10 min via some background path), but the round-robin priority logic appears not to deprioritize ZIPs marked `already_done=N/N` in the autofill state.

Two fixes available:
- **(a)** Cache the global canonical PIN set in autofill state, refresh once per hour. ~30s overhead per hour instead of per ZIP.
- **(b)** Add a `canon_complete_at TIMESTAMPTZ` column to `zip_coverage_v3`. Schema change, but lets the task skip ZIPs entirely if they're confirmed clean.

Neither blocking. (a) is the cheaper option to start with.

### 7. PAT in MANIFESTO.md keeps getting auto-revoked by GitHub

GitHub's secret scanning auto-revoked the PAT twice now (2026-05-19 and 2026-05-20). Sequence each time: PAT committed in MANIFESTO → GitHub scans → revokes silently → next push fails with 401 → operator regenerates.

The PAT is in the doc because past sessions needed a way to push from Claude's sandbox. The right fix is to NOT keep the PAT in repo at all: store it in Railway env vars (visible only to authenticated dashboard users) and have Claude fetch it via an admin endpoint. Pre-fix interim: keep PATs out of MANIFESTO and pass them through chat each session (they're already chat-exposed).

### 8. KC USA-classifier bug — retroactive re-classify needed

`classify_owner_type` was matching "USA" as a substring (not word-boundary) — names like SUSAN, SARAUSAD, MOUSAVI were misclassified individual→company. Found in 98020/98026 seed builds (43 false positives); fix applied to both `build_kc_owners.py` and `build_snohomish_owners.py` (commit `a2b1dee`). **But the 21 existing KC ZIPs were never re-classified** — estimated ~1.1% of parcels platform-wide still mis-classified as company. Selective re-classify pass needed on KC ZIPs, OR a one-time admin endpoint to re-run `classify_owner_type` on existing rows.

### 9. Snohomish probate signals showing as Contact Now (PR status check?)

Snohomish probate filings name only the decedent on day-1 (PR appointed weeks later via Letters Testamentary). The harvester writes role=`decedent` only on these signals. Per the original Eligibility Contract Rule 6 (KC only), probate matches should require `contact_status='family_pr_identified'` to promote to Contact now — otherwise stay in Build now / no_pr_yet wait pattern. Observed 2026-05-20 that 98020/98026 probate matches show in `playbook.call_now`. Either the filter doesn't apply to `source_type=wa_state_courts` (might be only checking case_parties_v3 contact_status), or the rule needs to be extended to cover the Snohomish signal shape. Needs a code read of the briefing selector to confirm.

### 10. /api/harvest/rematch is destructive AND blocks the curl while running synchronously

The rematch endpoint deletes all matches platform-wide, resets matched_at=NULL on all signals, then re-runs matcher inline. With 16K signals this takes ~5-10 min during which: (a) production briefings show 0 leads (delete pass completed, regeneration in progress); (b) the curl that triggered it times out at ~30s; (c) operator has no visibility into progress. This is a known footgun. Two improvements possible:
- Move rematch to a background task (similar to obit_autofill) so the HTTP call returns quickly with a job ID
- OR have rematch reset matched_at first AND THEN regenerate match-by-match, so existing matches stay live until each signal's new matches commit

Until then: rematch should only be triggered during low-traffic windows, with a clear comms plan if it'll be more than 2-3 min.

**Partial mitigation 2026-05-21:** Added `POST /api/harvest/rematch-reset-scoped?source_type=X&signal_type=Y&confirm=true` for targeted re-runs that don't disturb other signal classes. Used today to re-process the 191 Snohomish probate signals after the prop_type fix without touching KC. Doesn't solve the underlying "rematch is sync + destructive" problem for the global case, but removes the need to use the global endpoint for many real-world scoped fixes.

### ~~11. Pre-existing background-task contention on Supabase HTTP/2 stream pool~~ **RESOLVED 2026-07-22**

Root cause was NOT contention per se: `postgrest==0.17.2` hardcodes `http2=True`, so all API handlers and all background tasks shared ONE multiplexed HTTP/2 connection. A single bad connection failed every in-flight and subsequent request. Fixed by pinning the PostgREST transport to pooled HTTP/1.1 in `backend/api/db.py` (`_force_http1_pool()`, commit `fad8edc`). Verified 104/104 territories healthy with canonicalize_autofill running. The auth retry-on-RemoteProtocolError (`56a82a4`) and other contention workarounds can stay as belt-and-braces but should no longer fire. Original text below for reference:


scopi-autofill hits `'code': '57014', 'message': 'canceling statement due to statement timeout'` periodically (`_fetch_pending_pins` query). canonicalize_autofill hits `RemoteProtocolError: Server disconnected` periodically on its ticks. Both back off and retry; not blocking. The auth retry shipped 2026-05-19 (commit `56a82a4`) protects user sign-ins from this storm.

Deeper fix in the backlog: dedicated Supabase client per background task instead of all sharing the same default httpx connection pool. Single change but touches every task's import path.

### 12. Stale documentation worth a separate pass

- `docs/STATUS.md` — frozen at April 18, 2026 (5 commits). Says nothing about the harvester layer, orchestrator, or any of the 21 ZIPs added after.
- `docs/ZIP_BUILD_GUIDE.md` — describes obsolete pre-orchestrator CLI flow with SerpAPI investigation. Replaced by this manifesto's "canonical onboarding pipeline" section.
- `scripts/onboard_kc_zips.sh` — same obsolete CLI flow.
- `docs/SESSION_END_2026-05-01.md` — historical session journal. Accurate for that window but doesn't reflect anything after.

These can be deleted or marked deprecated in a separate cleanup pass.

### ~~13. Frontend Supabase config was inlined at build time~~ **RESOLVED 2026-05-20**

Was: `frontend/src/lib/supabase.js` read `import.meta.env.VITE_SUPABASE_*` at module load. Vite inlined those values into the JS bundle at `vite build` time. A rebuild in any environment that lacked those env vars (e.g., Claude container with only backend env vars) produced an auth-broken bundle that initialized supabase=null. Users only noticed once their cached localStorage session expired and the auto-refresh path surfaced the broken init. The `build:safe` guard existed to catch this but was bypass-able by calling `vite build` directly. Incident on 2026-05-20.

Fix: backend now exposes `GET /api/config` returning `{supabase_url, supabase_anon_key}` from Railway env vars. Frontend fetches at runtime on module load, caches result in `localStorage` under `sellersignal:supabase_config_v1`. `build:safe` polarity flipped — was verifying credentials WERE inlined; now verifies they are NOT (catches accidental regression to build-time injection). Any environment can rebuild the frontend without env vars. Commits `127cd27` (immediate fix) and `895f935` (structural refactor). Architecture documented in the 2026-05-20 afternoon build journal entry above.

### 14. Letter digest hardcoded to America/Denver — no per-agent timezone preference

The `letter_digest.py` task fires at 07:00 America/Denver for every agent, regardless of where the agent actually is. Jeremy's in Bozeman MT so this is right for him; the first WA beta agents will receive their digest at 05:00 or 06:00 Pacific (depending on DST alignment), which is earlier than ideal.

Acceptable for v1 because: (a) digest content doesn't go stale within a few hours so early delivery isn't actively bad, (b) the WA agents aren't running sequences yet, so the volume is zero for now. Fix: add a `timezone TEXT` column to `agent_profiles_v3` with default `'America/Denver'`, expose it on the profile form, and have the digest task read per-agent before deciding "is it 7am for this agent." Small change. Tracked here so it doesn't get lost when the first WA agent starts sending letters.

### 15. Backfill SQL for pre-fix letter activity not yet run

The 2026-06-02 prereq fix (`send_letter` and `start_sequence` write a `mailed` interaction row on success) only affects letters sent AFTER the commit landed. Existing test sequences (Burch / Lane / Christenson on Jeremy's profile, sent during the Stannp end-to-end test session) don't have `lead_interactions_v3` rows, so they don't auto-appear in My Leads even though the new letter badge logic would happily render them. A one-time backfill INSERT — for every `letters_sent_v3` row without a matching `lead_interactions_v3` row, insert one with `event_type='mailed'` — would close the loop. Not blocking; the agent can manually click "Mark mailed" in the dossier as a workaround, or simply view those sequences on the new `/letters` page (which doesn't depend on the interaction log).

### 16. Letters page sort is fixed to "started desc"

The MVP `/letters` page sorts by `started_at` descending. No column-header click for re-sort by latest event / next scheduled / owner name. Acceptable for low volume; revisit when an agent has >50 sequences and wants to triage by "what just happened" vs "what's about to happen". Small addition (~20 min) when needed.

---

## On the horizon (post-this-session priorities)

In Jeremy's stated order:

1. **Pre-launch checklist (load-bearing for go-live)**:
   - Order Stannp physical sample pack from dashboard — paper-quality validation
   - Re-introduce agency logo on letter PDFs as PNG (was SVG, xhtml2pdf can't render cleanly)
   - Flip `STANNP_MODE` from `test` → `live` in Railway env
   - Stripe test → live: create $299/mo live Price, new live webhook, update `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_TERRITORY_PRICE_ID` in Railway
   - Verify `RESEND_API_KEY` is set in Railway (otherwise renewal_notifier + letter_digest both silently no-op)
   - Backfill SQL for pre-fix letter activity (see active issue #15) — one-time cleanup so existing test sequences show in My Leads
   - Boot beta agents at go-live (one-time SQL: drop agent_territories_v3 rows + clear assigned_zip)
2. **5 next KC ZIPs** beyond the current 26. Good candidates that pair with existing live clusters: 98008 (Bellevue east, completes the Bellevue 04/05/06/07 cluster), 98144 (Mt Baker/Leschi Seattle, luxury waterfront), 98109 (Queen Anne South/SLU, pairs with 98119), 98011 (Bothell south, pairs with 98034 Kirkland north), 98028 (Kenmore, pairs with 98072 Woodinville). Should be re-evaluated against current claim demand before committing.
3. **Multi-county strategy** — replicate the canonical pipeline against another county's assessor bulk data. Demand-driven expansion using the same orchestrator pattern. "Expediency plus accuracy is a moat" (Jeremy, 2026-05-17).
4. **Beta growth path** — direct outreach to seed initial users, then Meta ads + Google search.

Deferred but on the longer-term roadmap:

- Per-agent timezone for letter digest (see active issue #14)
- canonicalize_autofill round-robin optimization (cache global canonical PIN set in task state) — see Active Issues #6
- Letters page column-header sorting (see active issue #16)
- C2 (in-app notification bell) — when letter volume justifies real-time pings
- C3 (Slack/CRM webhook for letter events) — when there's a CRM target to wire to
- Real skip-trace integration
- Email outreach integration (Clay/Instantly-style)
- Demo mode (`?demo=true`) for Zoom pitches
- First-visit walkthrough overlay
- Beta feedback tab to Supabase
- Info icons / tooltips
- Market sizzle one-pagers
- ~5-10% missing Street View photo patching
- briefings_v3 persistence (cache survives Railway recycles via Supabase)
- Friendlier Deep Signal error display
- Delete `frontend/src/components/ParcelDossier.jsx` (old 2,352-line) and `PlaybookList.jsx`
- Prompt caching on the canonicalizer (90% input cost reduction; not done because canon is already fast enough)
- Anthropic Batch API for canonicalize (50% discount, 24h turnaround; not done because canon is on critical-enough path that real-time matters)

---

## Don't-do (without explicit confirmation)

- `POST /api/harvest/clear-sentinel-parties` (destructive — 1,092+ rows)
- `POST /api/harvest/rematch?confirm=true` (destructive AND blocks briefings for ~5-10 min during regeneration — see active issue #10)
- Any backfill/admin endpoint that writes to production without prior confirmation
- Propose new architectures while a live investigation is open
- Reframe issues as "98004 working / others not" — Jeremy has rejected this framing in past sessions
- Invent code paths that don't match the proven production path
- Fire multiple onboard-zip calls in parallel (proven to fail on Supabase HTTP/2 stream pool — orchestrator's `_CANONICALIZE_LOCK` mitigates but doesn't eliminate)
- Change canonicalize concurrency without measurement and a redeploy plan (98034's canon dies on the redeploy)
- Commit PATs (or any secret) in MANIFESTO or any tracked file — GitHub secret scanning will auto-revoke. See active issue #7.
- Push an external-dependency change (new Python lib, new system tool) without verifying it works on Railway's environment. Local dev container ≠ production. See `pypdf` vs `pdftotext` learning (2026-05-20).
- Run raw `vite build` to produce a committed bundle. Always use `npm run build:safe` — its guard verifies the bundle uses runtime config fetch and contains no inlined Supabase JWTs. Since the 2026-05-20 refactor (active issue #13) the build no longer needs `VITE_SUPABASE_*` env vars at all; build:safe will catch any accidental regression to build-time injection.

---

## Final note

This document is the canonical state of SellerSignal V3 as of 2026-05-20. Update it whenever:

- A ZIP is added, removed, or changes status
- The canonical pipeline changes
- An "Active issues" item is resolved or a new one surfaces
- Architecture, schema, or key access changes
- A session ends with build journal entries worth preserving

The repo has 160+ commits across many sessions. Without this document, every future Claude has to reconstruct state from chat scrollback and stale docs. Keeping this current is the single biggest leverage point for session-to-session continuity.
