# SellerSignal v3 — Build Status

Last updated: April 18, 2026

## Core architectural principles (MUST PRESERVE)

1. **No additive scoring.** Pressure is categorical (0/1/2/3), not continuous.
   Never add "points" together. Never use hand-tuned weight multipliers.
2. **No LLM-delegated decisions.** Claude is used for narrative copy generation
   from verified facts only. Decisions (call_now / build_now / hold / avoid)
   come from explicit pressure rules in code, not from an LLM's inference.
3. **Trust tiers over confidence numbers.** Every signal is high / medium / low,
   not a float. Decisions gate on trust tier explicitly.
4. **Hard pressure requires court verification.** NOD, trustee sale, court-verified
   probate, court-verified divorce, verified obituary. News mentions are
   medium-trust, not hard pressure.
5. **Forbidden signals.** Never score `previously_listed` alone as pressure — it
   fires on ~82% of luxury parcels (ambient noise). Only score `extended_dom`
   or `price_history` high-trust as recent listing activity.
6. **One action per lead.** Pressure-scored `recommend_action` returns exactly
   one category with exactly one tone. No blended "somewhere between build_now
   and call_now" outputs.
7. **Tone matches cause.** Foreclosure = urgent. Probate/divorce/obituary =
   sensitive. Copy differs accordingly.

## What's DONE this session

### Repository scaffolding
- [x] Clean directory structure (`backend/`, `frontend/`, `schema/`, `docs/`)
- [x] README.md documenting architecture
- [x] .env.example with all required env vars
- [x] .gitignore (secrets, node_modules, pycache, generated output)
- [x] requirements.txt (FastAPI + uvicorn + supabase-py + anthropic + stripe + reportlab)
- [x] Procfile for Railway (uvicorn entrypoint)
- [x] runtime.txt (Python 3.11)

### Backend code ported from sandbox
- [x] `backend/investigation/` — the pressure-scored investigation module (847 lines)
  - Includes BudgetGuard, cache_get/put/invalidate, recommend_action with tone
- [x] `backend/scoring/` — signal_registry, rationality_index, banding, rebuild_band_assignments
- [x] `backend/selection/` — weekly_selector, run_investigation (orchestrator), outcomes
- [x] `backend/rendering/` — render_playbook, dossier_compiler, briefing_render, generate_estate_briefing, generate_tracking_sheet
- [x] `backend/ingest/` — 13 files for parcel ingestion + enrichment
- [x] `backend/research/` — 6 backtest + calibration files
- [x] `backend/generate_weekly.py` — weekly job orchestrator

### API scaffolding
- [x] `backend/main.py` — FastAPI app entry with CORS, lifespan hooks, route mounting
- [x] `backend/api/db.py` — Supabase client singleton
- [x] `backend/api/health.py` — /api/health + /api/status endpoints (COMPLETE)
- [x] `backend/api/briefings.py` — scaffolded (NOT WIRED)
- [x] `backend/api/parcels.py` — scaffolded with /:pin/why zero-API endpoint (NOT WIRED)
- [x] `backend/api/investigations.py` — scaffolded with budget endpoint (NOT WIRED)
- [x] `backend/api/playbook.py` — scaffolded for PDF generation (NOT WIRED)
- [x] `backend/api/map_data.py` — scaffolded with Street View URL endpoint (NOT WIRED)

### Schema
- [x] `schema/001_initial_v3_schema.sql` — 6 tables with RLS policies:
  - parcels_v3, investigations_v3, briefings_v3, outcomes_v3,
    serpapi_budget_v3, agent_territories_v3

## What's NOT DONE (next session priorities)

### Backend wiring (Priority 1)
- [ ] Wire `backend/api/briefings.py` to `backend/selection/weekly_selector.py`
- [ ] Wire `backend/api/parcels.py` to Supabase reads + the zero-API
      "why not selling" template generator (which doesn't exist yet — needs to be built)
- [ ] Wire `backend/api/investigations.py` to `backend/selection/run_investigation.py`
- [ ] Wire `backend/api/playbook.py` to `backend/rendering/render_playbook.py`
      and `backend/rendering/dossier_compiler.py`
- [ ] Wire `backend/api/map_data.py` to Supabase reads of parcels_v3
- [ ] Swap cache and budget state from flat-file (`out/investigation/cache/`,
      `out/investigation/budget_state.json`) to Supabase tables
      (investigations_v3 + serpapi_budget_v3)

### "Why not selling" generator (Priority 1)
- [ ] NEW module: `backend/scoring/why_not_selling.py`
  - Template-based generator from (owner_type, tenure_yrs, value, band, signal_family)
  - Produces: "why they're not selling yet", "what could change this",
    "estimated transition window"
  - Zero API cost per lookup — runs on structural features only
  - Runs as a data enrichment pass on all parcels in inventory, writes to
    parcels_v3.why_not_selling_text column (needs schema addition)

### Frontend (Priority 2 — next session)
- [ ] Vite + React + Leaflet scaffolding
- [ ] Estate aesthetic: carry over from archived sellersignal-briefing.html:
  - Typography: Playfair Display (headers), Source Serif 4 (body), Inter (UI)
  - Colors: --bg #F5F0EB (ivory), --accent #8B6914 (gold),
    --text #2C2418, --score-high #5A7247, --score-low #9E4B3C
- [ ] Unified map+briefing layout:
  - Left panel (380px): CALL NOW / BUILD NOW / STRATEGIC HOLDS tabs + search
  - Main area: Leaflet map with heat tiles + pins
  - Overlay: property card on pin click (Street View + dossier)
- [ ] Click handlers:
  - Click CALL NOW lead → map flies to pin, opens dossier
  - Click pin (on action list) → opens dossier
  - Click pin (off action list) → shows "why not selling" template
- [ ] Google Maps tiles (not Leaflet OSM) for production aesthetic
- [ ] Google Street View integration for property photos

### Deploy (Priority 3 — next session)
- [ ] Create new Railway project pointed at sellersignal-v3 repo
- [ ] Copy env vars from sellersignal-archive Railway project
- [ ] Apply schema to Supabase (manually via SQL Editor, NOT destructive —
      all v3 tables have `_v3` suffix and coexist with v1 tables)
- [ ] Port one ZIP's data from old `parcels` table → new `parcels_v3` table
      (start with 98004 since we have live investigation data there already)
- [ ] Smoke test end-to-end: ingest → investigate → generate briefing → render PDF
- [ ] DNS cutover: point sellersignal.co from old Railway to new Railway

## Known issues / watch-outs

1. **Sandbox code uses flat-file cache** (`out/investigation/cache/*.json`).
   Won't work on Railway (container filesystem is ephemeral). Must port to
   Supabase reads/writes against `investigations_v3` table before first deploy.

2. **Flat-file budget state** (`out/investigation/budget_state.json`) has
   the same issue. Must port to `serpapi_budget_v3` table.

3. **SerpAPI key mgmt.** The key was exposed twice in conversation history
   (chat with Claude on Apr 18). User committed to rotation. Confirm rotation
   before any live runs.

4. **GitHub PAT** was also exposed in conversation. Scoped to `sellersignal`
   (now `sellersignal-archive`) with read/write. New repo `sellersignal-v3`
   needs the PAT updated to include that repo's permissions when we push.

5. **Render_playbook.py** currently hardcodes PROPERTY_OVERRIDES for specific
   famous parcels. These hand-crafted overrides should be preserved as a
   feature (agents love them) but moved to a database table
   `parcel_overrides_v3` so they're editable without code deploys.

6. **Anthropic API usage.** Used for copy generation only. NEVER for
   decision-making. Any code path that calls Claude must be scoped to
   "generate narrative text from already-verified facts" — never "decide
   what to do with this parcel."

## File-level map: what each module does

### backend/investigation/__init__.py (847 lines) — THE CORE
- BudgetGuard class: per-run + monthly caps, rollover, estimate_run_cost dry-check
- SerpAPI wrapper with Mock mode for testing
- build_screen_queries / build_deep_queries
- _infer_source_type + score_signal_trust (high/medium/low per source)
- extract_all_signals: regex extraction keyed to owner name + property address
- recommend_action: pressure-scored decision layer (urgent/sensitive tone)
- cache_get/cache_put/cache_invalidate with 90-day TTL

### backend/scoring/signal_registry.py (380 lines)
- 10 registered signal families: financial_stress, failed_sale_attempt,
  investor_disposition, trust_aging, silent_transition, dormant_absentee,
  family_event_cluster, divorce_unwinding (pipeline built, awaiting court CSV),
  retirement_transition, death_inheritance
- Per-family scoring rules and copy templates

### backend/scoring/rationality_index.py (281 lines)
- Rationality filter for failed_sale_attempt: distinguishes "seller failed"
  from "market mistimed" based on DOM + price history + relist patterns

### backend/scoring/banding.py (232 lines) + rebuild_band_assignments.py (304 lines)
- Assigns parcels to Band 0-4 based on signals + value + tenure
- Rebuild script for re-banding after new signal ingestion

### backend/selection/weekly_selector.py (525 lines)
- Selects 5 CALL NOW + 3 BUILD NOW + 2 STRATEGIC HOLDS
- Slot reservation for Band 3 financial_stress (trustee sale, NOD)
- Investigation-promoted and investigation-demoted flows
- resolve_copy with investigation override mechanism
- Action-oriented copy templates (replaces passive templates)

### backend/selection/run_investigation.py (394 lines)
- Option A orchestrator: 8 B3 + 12 B2.5 + 30 B2 tier-balanced
- Auto-deep for financial_stress, failed_sale_attempt, family_event_cluster
- Dry-run estimate with budget approval
- Mid-run budget re-check before deep pass
- Hard finalist cap (15 default)

### backend/rendering/render_playbook.py (216 lines)
- ReportLab-based PDF renderer for 1-page weekly playbook
- Estate aesthetic: Playfair Display, gold accents, ivory background

### backend/rendering/dossier_compiler.py (211 lines)
- Multi-page dossier compiler for full forensic reads per lead

## Next session prompts

When continuing, provide Claude with:
1. This file
2. The archived sellersignal-v2 zip (staged at `/mnt/user-data/outputs/sandbox-final.zip`
   in the previous session's outputs — user has downloaded)
3. GitHub PAT (updated to include sellersignal-v3 access)
4. New SerpAPI key (rotated since last session)

First command to run: `git clone https://<PAT>@github.com/jeremyseglem/sellersignal-v3.git`

Then read: docs/STATUS.md (this file) to orient.

Then prioritize:
1. Write `backend/scoring/why_not_selling.py`
2. Swap flat-file cache to Supabase reads
3. Wire the 5 scaffolded API endpoints to their real backing modules
