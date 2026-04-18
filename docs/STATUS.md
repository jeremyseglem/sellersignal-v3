# SellerSignal v3 — Build Status

Last updated: April 18, 2026 (fourth push of initial session — ZIP builder fully wired)

## Core architectural principles (MUST PRESERVE)

1. **No additive scoring.** Pressure is categorical (0/1/2/3), not continuous.
2. **No LLM-delegated decisions.** Claude generates narrative copy from verified
   facts only. Decisions come from explicit pressure rules in code.
3. **Trust tiers over confidence numbers.** Every signal is high/medium/low.
4. **Hard pressure requires court verification.** NOD, trustee sale,
   court-verified probate/divorce, verified obituary. News mentions = medium.
5. **Forbidden signals.** Never score `previously_listed` alone as pressure.
6. **One action per lead.** Pressure-scored `recommend_action` returns exactly
   one category with exactly one tone.
7. **Tone matches cause.** Foreclosure = urgent. Probate/divorce/obituary =
   sensitive.
8. **ZIP-first architecture.** Every piece of data, every API call, every
   subscription is scoped to a ZIP. `zip_coverage_v3` is the source of truth
   for which ZIPs exist in the product. ZIPs are built one at a time through
   a re-runnable lifecycle.

## What's DONE

### Repository scaffolding
- [x] Clean directory structure (`backend/`, `frontend/`, `schema/`, `docs/`)
- [x] README.md, .env.example, .gitignore, Procfile, requirements.txt, runtime.txt

### Backend code (ported from sandbox)
- [x] `backend/investigation/__init__.py` — pressure-scored investigation engine
- [x] `backend/scoring/` — signal_registry, rationality_index, banding
- [x] `backend/selection/` — weekly_selector, run_investigation
- [x] `backend/rendering/` — render_playbook, dossier_compiler, estate briefing
- [x] `backend/ingest/` — 13 modules for parcel ingestion + enrichment
- [x] `backend/research/` — backtest + calibration scripts

### NEW in this push (ZIP-build pipeline fully wired — fourth push)
- [x] **`backend/ingest/arcgis.py`** — King County ArcGIS direct fetch
  - Async paginated fetch with `httpx`
  - Parses 14 fields per parcel into parcels_v3 schema
  - Computes lat/lng from point or polygon geometry
  - Derives owner_type, is_absentee, is_out_of_state from raw fields
  - Upserts in batches of 1000
  - MARKET_CONFIGS dict — add other markets (Maricopa, Miami-Dade, etc.)
    by registering their ArcGIS endpoints + field mappings here
- [x] **`backend/scoring/banding_v3.py`** — Band 0-4 assignment
  - 4 hard-disqualifier regex banks (institutional, tax agent, REO, brokerage)
  - Archetype-to-band mapping (12 archetypes → 6 bands)
  - Oversized-value, recent-buyer, commercial hard caps
  - Batch upsert
- [x] **`backend/selection/zip_investigation.py`** — ZIP-scoped investigation
  - Selects Option A scope (8 B3 + 12 B2.5 + 10×3 tier-balanced B2)
  - Dry-run cost estimate via persistence.estimate_run_cost
  - Real run with budget gates + mid-run re-check
  - Writes results via persistence.cache_put → investigations_v3
  - Stamps first_investigation_at + updates counts on coverage
- [x] **CLI commands fully wired**
  - `ingest` → backend/ingest/arcgis.py
  - `band` → backend/scoring/banding_v3.py
  - `investigate` → backend/selection/zip_investigation.py
  - All three support `--dry-run` style safety where relevant
- [x] **Investigation module cache delegation**
  - cache_get/cache_put/cache_invalidate now delegate to persistence.py
    when Supabase is configured
  - Fall back to flat-file when Supabase unavailable (dev mode)
  - No code changes required elsewhere — same function signatures
- [x] **`/api/investigations/*` endpoints fully wired**
  - POST /api/investigations/run (dry-run or real, with budget gates)
  - GET /api/investigations/budget (current month state)
  - POST /api/investigations/parcel/:pin/deep (on-demand single-parcel)
- [x] **`/api/playbook/*` endpoints fully wired**
  - GET /api/playbook/:zip (JSON version)
  - GET /api/playbook/:zip/pdf (Estate-aesthetic PDF via render_playbook.py)
  - GET /api/playbook/:zip/dossiers.zip (501, next session)
- [x] **`schema/002_zip_coverage.sql`** — new table `zip_coverage_v3`
  - Lifecycle tracking: `in_development` → `live` → `paused` → `archived`
  - Per-stage completion timestamps (ingested_at, classified_at, etc.)
  - Denormalized counts (parcel_count, investigated_count, current_call_now_count)
  - RLS: authenticated users see only `live`/`paused`, service role sees all
  - View `live_zips_v3` for convenience
  - Seeded 98004 as first in_development ZIP
- [x] **`backend/api/zip_gate.py`** — FastAPI dependency enforcing coverage
  - `require_live_zip` — 404 unless status='live'
  - `require_any_coverage` — allows any status (admin/internal)
  - 60-second in-memory cache per ZIP to avoid DB pressure
  - `invalidate_zip_cache()` for manual busting after status changes
  - Fail-open in dev mode when Supabase unavailable
- [x] **`backend/api/coverage.py`** — public coverage API
  - GET /api/coverage returns live ZIPs (+ in_development if requested)
  - GET /api/coverage/:zip returns lifecycle detail for one ZIP
- [x] **ZIP gate applied to all ZIP-scoped endpoints**
  - briefings.py: gated on all 3 routes via Depends(require_live_zip)
  - map_data.py: gated on `/{zip}` and `/{zip}/bounds`
  - parcels.py: gated implicitly via `_assert_parcel_zip_is_live` after fetch
- [x] **`backend/ingest/zip_builder.py`** — CLI lifecycle tool
  - Subcommands: status, register, ingest, geocode, classify, band, investigate, publish, pause
  - `classify` and `publish` are fully implemented
  - `register`, `status`, `pause` are fully implemented
  - `ingest`, `geocode`, `band`, `investigate` are placeholders (next session)
  - `publish` includes safety checks (can be bypassed with --force)
- [x] **`docs/ZIP_BUILD_GUIDE.md`** — operator documentation
  - Full walkthrough of building 98004 end-to-end
  - Verification checklist
  - Recovery procedures when things go wrong

### API wiring (endpoints now backed by real logic)
- [x] `backend/api/health.py` — /api/health + /api/status (COMPLETE, was already wired)
- [x] `backend/api/parcels.py` — WIRED
  - GET /api/parcels/:pin returns parcel + investigation + why_not_selling fallback
  - GET /api/parcels/:pin/why returns zero-API forensic read
- [x] `backend/api/map_data.py` — WIRED
  - GET /api/map/:zip returns heatmap-ready payload with category + pressure
  - GET /api/map/:zip/bounds computes bounding box for map centering
  - GET /api/map/streetview/:pin returns signed Google Street View URL
- [x] `backend/api/briefings.py` — WIRED
  - GET /api/briefings/:zip generates weekly playbook with slot reservations
  - 5 CALL NOW (slots 1-2 reserved for Band 3 financial_stress) + 3 BUILD NOW + 2 STRATEGIC HOLDS
  - Blocker filter applied at source
  - GET /api/briefings/:zip/summary compact version
  - GET /api/briefings/:zip/history past snapshots

### Schema
- [x] `schema/001_initial_v3_schema.sql` — 6 tables with RLS:
      parcels_v3, investigations_v3, briefings_v3, outcomes_v3,
      serpapi_budget_v3, agent_territories_v3

## What's NOT DONE (next session priorities)

### Backend — Priority 1
- [ ] `backend/api/investigations.py` — wire to `run_investigation.py` orchestrator
      (currently scaffolded only)
- [ ] `backend/api/playbook.py` — wire to `rendering/render_playbook.py` and
      `rendering/dossier_compiler.py` (currently scaffolded only)
- [ ] Update investigation module to call `persistence.cache_get/put` instead
      of flat-file (currently still uses out/investigation/cache/ paths)
- [ ] Update run_investigation orchestrator to use persistence.BudgetGuard methods

### Frontend — Priority 2
- [ ] Vite + React + Leaflet scaffolding
- [ ] Estate aesthetic carryover (Playfair Display, gold/ivory, from archive)
- [ ] Unified map+briefing layout:
  - Left panel: CALL NOW / BUILD NOW / STRATEGIC HOLDS tabs + search
  - Main area: map with heat tiles + pins
  - Overlay: property card (Street View + dossier or why-not-selling)

### Deploy — Priority 3
- [ ] New Railway project pointed at sellersignal-v3
- [ ] Copy env vars from archive project
- [ ] Apply schema SQL to Supabase (non-destructive — all `_v3` suffixed)
- [ ] Port 98004 data from legacy `parcels` table to `parcels_v3`
- [ ] End-to-end smoke test

## Known issues / watch-outs

1. **Investigation module still uses flat-file paths internally.** The
   `persistence.py` module is written but not yet called from
   `backend/investigation/__init__.py`. Next step: replace `cache_get`,
   `cache_put`, `cache_invalidate` calls inside the investigation module
   with imports from persistence module.

2. **SerpAPI key rotation pending.** Key was exposed multiple times in
   conversation. User committed to rotation. Confirm before any live runs.

3. **GitHub PAT in conversation.** Scoped to sellersignal-archive AND
   sellersignal-v3 now, with Contents R/W. Rotate after session ends.

4. **PROPERTY_OVERRIDES hardcoded in weekly_selector.py.** Should move to
   `parcel_overrides_v3` table for editability. Deferred.

5. **Anthropic API usage — narrative only, NEVER decisions.** Any code path
   calling Claude must be scoped to "generate text from verified facts" —
   never "decide what to do with this parcel."

## File-level map (what each module does)

### backend/investigation/__init__.py (847 lines) — CORE
- BudgetGuard class (being superseded by persistence.py)
- SerpAPI wrapper with mock mode for testing
- build_screen_queries / build_deep_queries
- extract_all_signals (regex extraction keyed to owner + address)
- **recommend_action — pressure-scored decision layer with urgent/sensitive tone**
- cache_get/put/invalidate flat-file ops (being superseded by persistence.py)

### backend/investigation/persistence.py (NEW, 290 lines)
- Drop-in Supabase replacement for cache + budget state
- Preserves the exact function signatures of the flat-file version
- Handles missing Supabase gracefully (returns None / defaults)

### backend/scoring/why_not_selling.py (NEW, 400 lines)
- 12 archetypes: trust_young, trust_mature, trust_aging, llc_investor_early,
  llc_investor_mature, llc_long_hold, individual_settled,
  individual_long_tenure, individual_recent, absentee_active,
  absentee_dormant, estate_heirs, unknown
- Deterministic classifier — owner_type + tenure + flags determine archetype
- Per-archetype templates: why_not, what_could_change, transition_window
- Base-rate priors from King County historical backtest

### backend/scoring/signal_registry.py (380 lines) — from sandbox
- 10 signal families with per-family scoring rules and copy templates

### backend/scoring/rationality_index.py (281 lines) — from sandbox
- Distinguishes "seller failed" from "market mistimed" for expired listings

### backend/scoring/banding.py (232 lines) + rebuild_band_assignments.py (304 lines)
- Assigns parcels to bands based on signals + value + tenure

### backend/selection/weekly_selector.py (525 lines) — from sandbox
- 5 CALL NOW + 3 BUILD NOW + 2 STRATEGIC HOLDS selection
- Slot reservations, blocker filter, action-oriented copy templates
- NOTE: The wired /api/briefings/:zip endpoint reimplements selection logic
  inline rather than calling this module. This is because the in-memory
  selector uses the flat-file inventory shape; the API uses Supabase reads.
  Consolidate next session.

### backend/selection/run_investigation.py (394 lines) — from sandbox
- Orchestrator for investigation runs with budget guards

### backend/api/briefings.py (NEW, wired)
- Weekly playbook generation from Supabase reads
- Selection logic inline (see note above — consolidate with weekly_selector)

### backend/api/parcels.py (NEW, wired)
- Per-parcel dossier with investigation + why_not_selling fallback

### backend/api/map_data.py (NEW, wired)
- Heatmap parcel payload + bounding box + signed Street View URLs

## Next session prompts

Share with next Claude:
1. This file
2. Link: github.com/jeremyseglem/sellersignal-v3
3. Fresh GitHub PAT (rotated)
4. Say "read docs/STATUS.md and continue from 'What's NOT DONE'"

Priority order:
1. Replace flat-file calls in `backend/investigation/__init__.py` with
   `backend/investigation/persistence.py` imports
2. Wire `backend/api/investigations.py` and `backend/api/playbook.py`
3. Consolidate selection logic (API briefings vs weekly_selector module)
4. Frontend scaffolding (Vite + React + Leaflet)
5. Railway deploy prep
