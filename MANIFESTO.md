# SellerSignal V3 — Manifesto

**Last updated:** 2026-05-17 (post 5-ZIP expansion, orchestrator redesign, canonicalize autofill task, query-path fix)
**Status:** Living document. Update on every session that changes architecture, ZIPs, or canonical paths.
**Source of truth:** This file. Anything in `docs/STATUS.md`, `docs/ZIP_BUILD_GUIDE.md`, or `docs/SESSION_END_*.md` may be stale — defer to this document when they disagree.

---

## Standing rules (Jeremy's)

These apply to every Claude session. Non-negotiable.

1. Never build without explicit confirmation.
2. Never assume; never invent data. Reference this manifesto and the build journal before proposing anything.
3. Direct answers, no hedging, no emojis. When wrong, own it without spiraling.
4. "Building" is jargon — use plain English ("in pipeline", "on watch list").
5. Don't drift from the working code path. The 26 live ZIPs are the standard; match against them.
6. Skip-trace and Lob letter sending are NOT wired for beta (placeholder buttons).
7. Brian is co-founder for product validation discussions.

---

## What SellerSignal is

An AI-powered intelligence platform for luxury real estate agents in defined ZIP territories. It surfaces motivated sellers using a categorical pressure model on public-record investigation signals (probates, divorces, tax foreclosures, obituaries) joined to parcel data.

**Differentiator:** identifies the decision-maker by name — the personal representative on a probate (a living adult child or spouse), not the deceased homeowner. Agent gets a Call Now lead with the actual person to call.

**Beta model:** $299/month per ZIP territory, exclusive (one agent per ZIP), invite-only first-to-claim.

**Geographic scope:** **26 King County, Washington ZIPs** seeded as of 2026-05-17 (was 21 yesterday). Bozeman MT (Jeremy's actual market) is on the post-launch roadmap.

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

### Live measurements (snapshot 2026-05-17)
```
total live ZIPs:    26
total parcels:      268,132
total Call Now:     1,389
total Build Now:    sum of build_now_total across briefings (~3000+ per ZIP)
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

**Eligibility contract Rule 6 (added April 2026):** A probate match is only promoted to Call Now when `contact_status == 'family_pr_identified'`. Probate matches without an identified family PR stay in Build Now.

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
                    Required for Call Now precision; not for Build Now.
```

**End states the orchestrator can land in:**
- `completed` — all 7 steps succeeded
- `live_canonicalize_pending` — steps 1-6 succeeded, step 7 deferred (another ZIP's canon was holding the lock). ZIP is fully live; canon needs re-trigger to run.
- `live_canonicalize_failed` — steps 1-6 succeeded, step 7 raised. ZIP is live; canon can be retried out-of-band.
- `failed` — pre-publish step failed; ZIP is NOT live.

**Operational rules learned the hard way (May 17, 2026):**
- **Fire one ZIP at a time.** Parallel-N onboarding exhausts the Supabase HTTP/2 stream pool and produces random failures at register/seed/classify/band. Wait until a ZIP reaches live state before firing the next.
- **Retry transient classify failures.** `ConnectionTerminated`/`Server disconnected` errors hit random pipeline steps. The orchestrator's 3-attempt `_retry` handles most, but occasionally a step exhausts retries — re-fire the whole orchestrator (idempotent, picks up where it left off).
- **Canonicalize takes ~2 hours per ZIP at conc=3.** It's the long pole. ZIPs are usable for Build Now immediately after step 6; Call Now precision improves as canon completes.

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
- **Background tasks:** Six asyncio tasks in `backend/tasks/`:
  - `autofill.py` — case-parties scraper
  - `obit_autofill.py` — multi-source obit harvester
  - `treasury_autofill.py` — tax-foreclosure harvester
  - `rematch_autofill.py` — drains unmatched-signals queue
  - `snohomish_tenure_autofill.py` — SCOPI per-parcel detail page scraper (idle by default)
  - `canonicalize_autofill.py` — completes deferred / partial owner_canonical_v3 work
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

11 SQL migration files applied sequentially to the Supabase project.

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

---

## Build journal (most recent at top)

### 2026-05-17 — 5-ZIP expansion + orchestrator redesign + canon autofill (this session)

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
- **Onboarded 5 new KC ZIPs to live state** sequentially (parallel-N onboarding fails on the HTTP/2 stream pool; this is a real constraint). Total ZIPs: 21 → 26. Added 63,302 parcels. Call Now leads on new ZIPs: 8 already firing before canonicalize completes.

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

The April 29 investigation (only 98004 had Call Now leads; other 10 ZIPs had 0) resolved. Root cause: cumulative effects of the partial-success scraper rate combined with sentinel-poisoning. Resolution path: ran `clear-sentinel-parties` to wipe the 1,092 poisoned rows, then let autofill re-attempt them with the rebuilt `kc_court_participants` scraper. Multiple ZIPs started producing leads within hours.

### 2026-04-26 to 2026-04-28 — Slice C: archetype dossier + Lead Memory

Added archetype-driven dossier (5 archetypes + general fallback), Lead Memory persistence (`schema/011_lead_interactions.sql`), cold-visitor gate.

### 2026-04-24 to 2026-04-26 — Slice B: action-first briefing

Briefing redesign: header oracle line, action list, pipeline, watch list. Eligibility Contract Rule 6 (family_pr_identified required for Call Now probate).

### 2026-04-22 to 2026-04-23 — Harvester layer

KC Superior Court harvester. Phase 1.5: personal representative extraction (the case-parties scraper). Matcher with surname-required gate. Multi-source obituary harvester.

### 2026-04-19 to 2026-04-21 — Genesis

Project bootstrapped from v1 archive. Owner canonicalizer + classifier. ArcGIS ingest. Supabase schema 001-002. Frontend skeleton. First admin endpoints.

---

## Active issues / known cracks (May 17, 2026)

These are tracked here so they don't get lost. None are production blockers.

### ~~1. `?city=` query param not flowing through to register~~ **RESOLVED 2026-05-17**

Was: 98034 onboarded with `?city=Kirkland` ended up with `city="Bellevue"` because the endpoint default was a literal "Bellevue" and an earlier curl misformat dropped the query param. The pipeline then no-op'd on re-fire because cmd_register is idempotent.

Fix: endpoint signature changed to `city: Optional[str] = None` with runtime lookup against `KC_ZIP_TO_CITY`/`SNO_ZIP_TO_CITY`. Added `/admin/coverage-meta/{zip}` repair endpoint for the existing-row data fix. 98034's row corrected to Kirkland. Commit `e4ca29e`.

### ~~2. No canonicalize_autofill background task~~ **RESOLVED 2026-05-17**

Was: When 3+ ZIPs were onboarded sequentially, only the first one's canonicalize ran to completion; the others landed in `live_canonicalize_pending` and stayed there indefinitely without manual orchestrator re-fires.

Fix: built `backend/tasks/canonicalize_autofill.py`. Two-tier priority (orchestrator-flagged ZIPs first, then round-robin sweep), uses the same `_CANONICALIZE_LOCK` as the orchestrator. Admin endpoints at `/api/harvest/canonicalize-autofill-{status,pause,resume}`. Multi-ZIP onboarding is now fully fire-and-forget. Commit `d113ee4`.

### 3. MANIFESTO.md was previously not in the repo

The handoff manifesto used in past Claude sessions lived in the project context only, not the repo. Future sessions cloning the repo had no canonical document. **Fixed by commit `79e011d`** — this file is now the source of truth. `docs/STATUS.md` is severely stale (last updated April 18) and should not be relied on.

### 4. Stale documentation worth a separate pass

- `docs/STATUS.md` — frozen at April 18, 2026 (5 commits). Says nothing about the harvester layer, orchestrator, or any of the 21 ZIPs added after.
- `docs/ZIP_BUILD_GUIDE.md` — describes obsolete pre-orchestrator CLI flow with SerpAPI investigation. Replaced by this manifesto's "canonical onboarding pipeline" section.
- `scripts/onboard_kc_zips.sh` — same obsolete CLI flow.
- `docs/SESSION_END_2026-05-01.md` — historical session journal. Accurate for that window but doesn't reflect anything after.

These can be deleted or marked deprecated in a separate cleanup pass.

### 5. canonicalize_autofill round-robin sweep overhead (~32 min per full cycle)

Per-tick, the autofill task picks one live ZIP and calls `backfill_zip` on it. Even on fully-canonicalized ZIPs, backfill_zip does a global canonical-PIN fetch (~30s on the current ~250k-row table) before discovering there's nothing to do. With 26 live ZIPs that's ~32 min for a full idle sweep. Not a problem at current scale; at multi-county scale (hundreds of ZIPs) this becomes wasteful.

Two fixes available:
- **(a)** Cache the global canonical PIN set in autofill state, refresh once per hour. ~30s overhead per hour instead of per ZIP.
- **(b)** Add a `canon_complete_at TIMESTAMPTZ` column to `zip_coverage_v3`. Schema change, but lets the task skip ZIPs entirely if they're confirmed clean.

Neither blocking. (a) is the cheaper option to start with.

---

## On the horizon (post-this-session priorities)

In Jeremy's stated order:

1. **5 next KC ZIPs** beyond the current 26. Good candidates that pair with existing live clusters: 98008 (Bellevue east, completes the Bellevue 04/05/06/07 cluster), 98144 (Mt Baker/Leschi Seattle, luxury waterfront), 98109 (Queen Anne South/SLU, pairs with 98119), 98011 (Bothell south, pairs with 98034 Kirkland north), 98028 (Kenmore, pairs with 98072 Woodinville). Should be re-evaluated against current claim demand before committing.
2. **Multi-county strategy** — replicate the canonical pipeline against another county's assessor bulk data. Demand-driven expansion using the same orchestrator pattern. "Expediency plus accuracy is a moat" (Jeremy, 2026-05-17).
3. **Beta growth path** — direct outreach to seed initial users, then Meta ads + Google search.

Deferred but on the longer-term roadmap:

- canonicalize_autofill round-robin optimization (cache global canonical PIN set in task state) — see Active Issues #5
- Mobile responsiveness rebuild from desktop-only inline-styled components
- Real Lob letter integration (currently preview-only)
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
- Any backfill/admin endpoint that writes to production without prior confirmation
- Propose new architectures while a live investigation is open
- Reframe issues as "98004 working / others not" — Jeremy has rejected this framing in past sessions
- Invent code paths that don't match the proven production path
- Fire multiple onboard-zip calls in parallel (proven to fail on Supabase HTTP/2 stream pool)
- Change canonicalize concurrency without measurement and a redeploy plan (98034's canon dies on the redeploy)

---

## Final note

This document is the canonical state of SellerSignal V3 as of 2026-05-17. Update it whenever:

- A ZIP is added, removed, or changes status
- The canonical pipeline changes
- An "Active issues" item is resolved or a new one surfaces
- Architecture, schema, or key access changes
- A session ends with build journal entries worth preserving

The repo has 160+ commits across many sessions. Without this document, every future Claude has to reconstruct state from chat scrollback and stale docs. Keeping this current is the single biggest leverage point for session-to-session continuity.
