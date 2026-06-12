# SellerSignal V3 — Manifesto

**Last updated:** 2026-06-11 (Dallas County TX live — 3rd state. Recorder harvester via headless browser clears Cloudflare; 75205/75225/75230 onboarded; 61 live ZIPs)
**Status:** Living document. Update on every session that changes architecture, ZIPs, or canonical paths.
**Source of truth:** This file. Anything in `docs/STATUS.md`, `docs/ZIP_BUILD_GUIDE.md`, or `docs/SESSION_END_*.md` may be stale — defer to this document when they disagree.

---

## Standing rules (Jeremy's)

These apply to every Claude session. Non-negotiable.

1. Never build without explicit confirmation.
2. Never assume; never invent data. Reference this manifesto and the build journal before proposing anything.
3. Direct answers, no hedging, no emojis. When wrong, own it without spiraling.
4. "Building" is jargon — use plain English ("in pipeline", "on watch list").
5. Don't drift from the working code path. The 61 live ZIPs across 4 markets (WA_KING, AZ_MARICOPA, WA_SNOHOMISH, TX_DALLAS) are the standard; match against them.
6. Skip-trace and Lob letter sending are NOT wired for beta (placeholder buttons).
7. Brian is co-founder for product validation discussions.

---

## What SellerSignal is

An AI-powered intelligence platform for luxury real estate agents in defined ZIP territories. It surfaces motivated sellers using a categorical pressure model on public-record investigation signals (probates, divorces, tax foreclosures, obituaries) joined to parcel data.

**Differentiator:** identifies the decision-maker by name — the personal representative on a probate (a living adult child or spouse), not the deceased homeowner. Agent gets a Contact now lead with the actual person to call.

**Beta model:** $299/month per ZIP territory, exclusive (one agent per ZIP), invite-only first-to-claim.

**Geographic scope:** **61 live ZIPs across 4 markets** as of 2026-06-11: King County WA (32), Maricopa County AZ (20), Snohomish County WA (6), Dallas County TX (3). Bozeman MT (Jeremy's actual market) is on the post-launch roadmap.

### Current 26 live ZIPs

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

### Live measurements (snapshot 2026-06-11)
```
total live ZIPs:    61
  WA_KING:      32   (King County, WA — the original market)
  AZ_MARICOPA:  20   (Scottsdale/Phoenix area; Recorder OCR harvester, Phase 2)
  WA_SNOHOMISH:  6   (Edmonds + Lake Stevens; daily-report harvester)
  TX_DALLAS:     3   (Park Cities + Preston Hollow — NEW 2026-06-11)
                       75205 Highland Park (7,057 parcels, median $2.20M)
                       75225 University Park (7,796 parcels, median $2.18M)
                       75230 Preston Hollow  (10,112 parcels, median $1.13M)
Dallas signal source: tx_dallas_recorder (Affidavit of Heirship = primary TX
  death->title instrument; ~2% of daily recordings; first live write 80 signals
  for 05/25–06/01 window). Matching queued behind the WA drain (rematch_autofill
  scopes to the OLDEST unmatched signal's market; Dallas signals are newest so
  they match once the WA backlog clears — no intervention needed).

NOTE: an earlier snapshot in this file said "29 live" — stale. 61 is correct
  (verified against GET /api/coverage?include_in_development=true 2026-06-11).
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

### 11. Pre-existing background-task contention on Supabase HTTP/2 stream pool

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
