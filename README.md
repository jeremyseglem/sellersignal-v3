# SellerSignal v3

Clean-build rebuild of SellerSignal.

The v1 codebase (now archived at `sellersignal-archive`) carried accumulated
architectural problems: additive scoring with hand-guessed weights, LLM-delegated
inference with hallucinated outputs, threshold-based tier assignment that produced
"interesting but not obvious" recommendations. v3 replaces the engine entirely.

## What v3 is

A pressure-scored decision layer for luxury real-estate prospecting. For every
parcel in a covered ZIP, v3 produces:

1. **A structured signal inventory** — what's actually true about the parcel and
   owner, sourced from public records and web search with explicit trust tiers.
2. **A pressure score (0-3)** — is there forced timing (NOD, trustee sale,
   court-verified probate/divorce), directional pressure (expired listing,
   medium-trust financial mentions, retirement), or context only?
3. **A recommended action** — `call_now` / `build_now` / `hold` / `avoid`, with
   a matched tone (`urgent` / `sensitive` / `relational` / `neutral`) and a
   specific next step.
4. **A weekly operator playbook** — the 10 moves that matter this week, sliced
   into CALL NOW / BUILD NOW / STRATEGIC HOLDS.

## What v3 is NOT

- Not an additive-score-plus-threshold model. Pressure is categorical.
- Not an LLM-delegated inference pipeline. Claude is used for copy generation
  from verified facts only, never for decision-making.
- Not a monolithic Node server. FastAPI backend, React frontend, clean split.

## Stack

- **Backend**: Python 3.11, FastAPI, uvicorn, Supabase (Postgres), SerpAPI,
  Anthropic SDK (for narrative generation only, not decision-making)
- **Frontend**: React + Vite + Leaflet (merged map+briefing single-page app)
- **Hosting**: Railway (new project, separate from archive)
- **Auth**: Supabase Auth
- **Payments**: Stripe (carried over from v1 — not product logic)

## Directory structure

```
backend/
  investigation/     # SerpAPI-driven signal extraction with trust tiers
  scoring/           # Pressure model, signal registry, rationality filter
  selection/         # Weekly playbook selector (5+3+2 with slot reservations)
  rendering/         # PDF/HTML output for briefings and dossiers
  ingest/            # Parcel data ingestion from ArcGIS / ATTOM
  api/               # FastAPI routes
  main.py            # FastAPI app entry

frontend/            # React+Vite SPA (next session)
schema/              # Supabase migrations
docs/                # Architecture notes, handoff docs
```

## Development status

See `docs/STATUS.md` for current build progress and next steps.

## Running locally

See `docs/DEVELOPMENT.md` (to be written next session).
