# SellerSignal v3 — Build Status

Last updated: April 18, 2026 (end of initial session, 5 commits)

## Core architectural principles — MUST PRESERVE

1. **No additive scoring.** Pressure is categorical (0/1/2/3), never continuous.
2. **No LLM-delegated decisions.** Claude generates narrative copy from verified
   facts only. Decisions come from explicit pressure rules in code.
3. **Trust tiers over confidence numbers.** Every signal is high/medium/low.
4. **Hard pressure requires court verification.** NOD, trustee sale,
   court-verified probate/divorce, verified obituary. News mentions = medium.
5. **Forbidden signals.** Never score `previously_listed` alone as pressure —
   it fires on ~82% of luxury parcels. Only `extended_dom` or `price_history`
   at high trust count as real listing activity.
6. **One action per lead.** Pressure-scored `recommend_action` returns exactly
   one category with exactly one tone.
7. **Tone matches cause.** Foreclosure = urgent. Probate / divorce / obituary
   = sensitive. Copy differs accordingly.
8. **ZIP-first architecture.** Every piece of data, every API call, every
   subscription is scoped to a ZIP. `zip_coverage_v3` is the source of truth
   for which ZIPs exist in the product. ZIPs are built one at a time through
   a re-runnable lifecycle.
9. **Narrative, never decisions, for Claude.** Any code path calling Anthropic
   must be scoped to "generate narrative text from already-verified facts" —
   never "decide what to do with this parcel."

---

## What's DONE

### Commit 1 — Initial scaffold
- Directory structure (`backend/`, `frontend/`, `schema/`, `docs/`)
- README, .env.example, .gitignore, Procfile, requirements.txt, runtime.txt
- Ported 40+ sandbox Python modules into `backend/` subdirs
- FastAPI entry point (`backend/main.py`) with CORS, lifespan hooks, error handling
- Schema 001: parcels_v3, investigations_v3, briefings_v3, outcomes_v3,
  serpapi_budget_v3, agent_territories_v3 with RLS

### Commit 2 — Decision engine + initial API wiring
- `backend/scoring/why_not_selling.py` — zero-API forensic generator,
  12 archetypes, deterministic classification from structural features
- `backend/investigation/persistence.py` — Supabase cache + budget
  (replaces flat-file)
- Wired: GET /api/parcels/:pin, /api/parcels/:pin/why,
  /api/map/:zip, /api/map/:zip/bounds, /api/map/streetview/:pin,
  /api/briefings/:zip, /api/briefings/:zip/summary, /api/briefings/:zip/history

### Commit 3 — ZIP coverage layer
- Schema 002: `zip_coverage_v3` table with lifecycle (in_development /
  live / paused / archived), per-stage completion stamps, RLS,
  `live_zips_v3` view, 98004 seeded as first in_development ZIP
- `backend/api/zip_gate.py` — `require_live_zip` FastAPI dependency with
  60-sec in-memory cache
- `backend/api/coverage.py` — GET /api/coverage public list + /:zip detail
- All ZIP-scoped endpoints gated (briefings, map, parcels)
- `backend/ingest/zip_builder.py` — CLI with subcommands: status, register,
  ingest, geocode, classify, band, investigate, publish, pause
- `docs/ZIP_BUILD_GUIDE.md` — end-to-end 98004 walkthrough

### Commit 4 — ZIP build pipeline fully wired
- `backend/ingest/arcgis.py` — async King County paginated fetch with
  httpx, 14-field parse, geometry→lat/lng, batched upsert, extensible
  MARKET_CONFIGS dict
- `backend/scoring/banding_v3.py` — Band 0-4 with 4 hard-disqualifier
  regex banks, archetype→band map, caps
- `backend/selection/zip_investigation.py` — ZIP-scoped Option A
  orchestrator with budget gates, dry-run estimator, persistence writes
- CLI `ingest`, `band`, `investigate` commands now fully implemented
  (were placeholders)
- Investigation module `cache_get/put/invalidate` delegate to persistence.py
  when Supabase is configured (flat-file fallback for dev)
- POST /api/investigations/run (dry-run or real, budget-gated)
- GET /api/investigations/budget
- POST /api/investigations/parcel/:pin/deep
- GET /api/playbook/:zip (JSON), /api/playbook/:zip/pdf (PDF via ReportLab)

### Commit 5 (this push) — Frontend scaffold + schema apply docs
- `frontend/` scaffolded with Vite + React 18 + react-leaflet
- `frontend/src/styles/tokens.css` — Estate aesthetic design tokens
  (ivory #F5F0EB, gold #8B6914, warm brown #2C2418, sage/red/gold tones;
  Playfair Display / Source Serif 4 / Inter typography)
- `frontend/src/api/client.js` — thin fetch wrapper, modules for
  coverage, briefings, map, parcels, investigations, playbook, health
- `frontend/src/pages/CoveragePage.jsx` — landing list of live ZIPs
- `frontend/src/pages/BriefingPage.jsx` — unified map+playbook single view
- `frontend/src/components/PlaybookList.jsx` — left panel, CALL NOW /
  BUILD NOW / STRATEGIC HOLDS with tone-colored headers
- `frontend/src/components/MapPanel.jsx` — Leaflet map with
  category-colored pins, click-to-select, fly-to animation
- `frontend/src/components/ParcelDossier.jsx` — slide-in panel on pin
  click: Street View, recommended action, why-not-selling read, evidence
- `frontend/README.md` — run instructions, structure, design token guide
- `docs/SCHEMA_APPLY.md` — step-by-step Supabase migration guide with
  5 verification queries + rollback procedure

---

## What's NOT DONE — next session priorities

### Priority 1: Wake up the stack
- [ ] Apply schema migrations to Supabase (run SQL from schema/001 and
      schema/002 in SQL Editor — see docs/SCHEMA_APPLY.md)
- [ ] Verify via `python -m backend.ingest.zip_builder status 98004`
      (should show 98004 in_development with all stages unchecked)

### Priority 2: Run the 98004 build end-to-end
- [ ] `python -m backend.ingest.zip_builder ingest 98004` — real ArcGIS fetch
- [ ] `python -m backend.ingest.zip_builder classify 98004` — archetype assignment
- [ ] `python -m backend.ingest.zip_builder band 98004` — band assignment
- [ ] `python -m backend.ingest.zip_builder investigate 98004 --dry-run` —
      see projected cost (~$10)
- [ ] `python -m backend.ingest.zip_builder investigate 98004` — real run
- [ ] `python -m backend.ingest.zip_builder publish 98004` — flip to live

### Priority 3: Frontend wiring
- [ ] `cd frontend && npm install`
- [ ] `npm run dev` — visit http://localhost:5173
- [ ] Verify coverage page shows 98004, click through, see map + playbook
- [ ] Style refinements as needed

### Priority 4: Deploy to Railway
- [ ] Create new Railway project → point at github.com/jeremyseglem/sellersignal-v3
- [ ] Copy env vars from sellersignal-archive Railway project
      (SUPABASE_URL, SUPABASE_SERVICE_KEY, SERPAPI_KEY, ANTHROPIC_API_KEY,
       STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET)
- [ ] Add: GOOGLE_MAPS_API_KEY, GOOGLE_STREET_VIEW_API_KEY (new)
- [ ] Configure build: `pip install -r requirements.txt && cd frontend && npm install && npm run build`
- [ ] Configure start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
      (already in Procfile)
- [ ] DNS cutover: point sellersignal.co from old Railway to new

### Priority 5: Dossier bundle (deferred)
- [ ] GET /api/playbook/:zip/dossiers.zip — wire to
      backend/rendering/dossier_compiler.py (currently returns 501)

---

## Known issues & watch-outs

1. **SerpAPI key rotation pending.** Key was exposed in conversation.
   Rotate at serpapi.com/dashboard before any live run.

2. **GitHub PAT was in conversation too.** Rotate after session close.

3. **Sandbox flat-file caches exist in `/home/claude/sellersignal_v2/out/`
   but are not reachable from the new repo.** Not an issue — the
   `persistence.py` module reads from Supabase in production. Flat-file
   fallback is only for local dev without Supabase.

4. **PROPERTY_OVERRIDES hardcoded in weekly_selector.py.** Should move to
   a `parcel_overrides_v3` table for editability. Deferred — not
   blocking.

5. **The three markets beyond WA_KING (Maricopa, Miami-Dade, etc.) need
   their MARKET_CONFIGS added in backend/ingest/arcgis.py** before
   those markets can ingest. Templates are documented in the file's
   docstring.

6. **Google Maps API keys not yet set.** Street View endpoint returns
   503 without them. Non-blocking for build — the map itself uses
   Leaflet+CartoDB which is free.

7. **Frontend hasn't been tested against a live backend yet.** All code
   parses clean and the API contract matches, but first-run may surface
   small integration bugs. Expected — that's what next session validates.

---

## File-level map

### backend/

**investigation/**
- `__init__.py` (900 lines) — BudgetGuard, screen/deep queries, signal
  extraction, pressure-scored recommend_action with urgent/sensitive tone
- `persistence.py` (290 lines) — Supabase-backed cache + budget state

**scoring/**
- `why_not_selling.py` (400 lines) — zero-API archetype classifier
- `banding_v3.py` (230 lines) — Band 0-4 assignment with hard disqualifiers
- `signal_registry.py`, `rationality_index.py`, `banding.py`,
  `rebuild_band_assignments.py` (from sandbox — legacy, may be removed)

**selection/**
- `zip_investigation.py` (200 lines) — Option A orchestrator per ZIP
- `weekly_selector.py` (from sandbox — legacy, may be consolidated)
- `run_investigation.py` (from sandbox — superseded by zip_investigation)
- `outcomes.py` — from sandbox

**ingest/**
- `arcgis.py` (270 lines) — direct paginated fetch from King County
- `zip_builder.py` (480 lines) — CLI lifecycle tool
- Plus 13 legacy sandbox modules (pipeline, lead_builder, etc.)

**api/**
- `main.py` — FastAPI app entry (routing, CORS, lifespan, frontend serve)
- `db.py` — Supabase client singleton
- `zip_gate.py` — require_live_zip dependency
- `health.py`, `coverage.py`, `briefings.py`, `parcels.py`, `map_data.py`,
  `investigations.py`, `playbook.py`

**rendering/**
- `render_playbook.py`, `dossier_compiler.py`, `briefing_render.py`,
  `generate_estate_briefing.py`, `generate_tracking_sheet.py`

**research/**
- Backtest + calibration scripts (sandbox)

### frontend/
- `package.json`, `vite.config.js`, `index.html`
- `src/main.jsx`, `src/App.jsx`
- `src/api/client.js`
- `src/pages/CoveragePage.jsx`, `src/pages/BriefingPage.jsx`
- `src/components/PlaybookList.jsx`, `src/components/MapPanel.jsx`,
  `src/components/ParcelDossier.jsx`
- `src/styles/tokens.css`

### schema/
- `001_initial_v3_schema.sql` — 6 core tables with RLS
- `002_zip_coverage.sql` — coverage table + live_zips_v3 view + 98004 seed

### docs/
- `STATUS.md` (this file)
- `ZIP_BUILD_GUIDE.md` — ZIP lifecycle operator guide
- `SCHEMA_APPLY.md` — schema migration apply procedure

---

## Next session prompt

Share with next Claude:
1. Link: github.com/jeremyseglem/sellersignal-v3
2. Fresh GitHub PAT (if prior one was rotated — if not, prior one works)
3. Confirm SerpAPI key was rotated or provide a new one for Railway
4. Say: "read docs/STATUS.md and continue from 'Priority 1'"

The next session's first tangible outcome is the 98004 build completing
and 98004 being visible + usable in the web UI. Everything needed to
reach that outcome is written and committed.
