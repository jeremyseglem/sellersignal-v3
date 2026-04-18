# ZIP Build Guide

How to add a new ZIP to SellerSignal, from nothing to live.

## Prerequisites

- Supabase credentials set (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`)
- SerpAPI key set for investigation stage (`SERPAPI_KEY`)
- ArcGIS source URL for the market (King County, Maricopa, etc.)

## The lifecycle

Every ZIP passes through seven stages. Each is a separate, re-runnable
CLI command. None destroy prior data — re-running is safe.

```
  register → ingest → geocode → classify → band → investigate → publish
```

Status transitions in `zip_coverage_v3.status`:
- After `register`: `in_development`
- After `publish`: `live`
- Can be paused with `pause` (returns to `in_development`-like hidden state)

## Commands (from repo root)

All commands take `zip_code` as their first arg. All are idempotent.

### 1. `register` — add the ZIP to coverage

```bash
python -m backend.ingest.zip_builder register 98004 \
    --market WA_KING \
    --city Bellevue \
    --state WA \
    --source-url "https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0"
```

This adds a row to `zip_coverage_v3` with status `in_development`.
Safe to re-run — becomes a no-op if ZIP is already registered.

### 2. `ingest` — pull parcels from ArcGIS

```bash
python -m backend.ingest.zip_builder ingest 98004
```

Paginates through the ArcGIS source, parses fields per market, upserts
into `parcels_v3` keyed on pin. Expected runtime: 30-120 seconds per
thousand parcels.

On completion, stamps `parcels_ingested_at` and updates `parcel_count`.

**Status: NOT YET IMPLEMENTED** — placeholder CLI exists, port
sandbox King County ingest logic next session.

### 3. `geocode` — fill missing lat/lng

```bash
python -m backend.ingest.zip_builder geocode 98004
```

Most ArcGIS sources include geometry natively. This step is only needed
for edge cases. Uses Google Maps Geocoding API (requires
`GOOGLE_MAPS_API_KEY`).

Stamps `parcels_geocoded_at`.

**Status: NOT YET IMPLEMENTED** — likely not needed for WA_KING.

### 4. `classify` — assign archetypes

```bash
python -m backend.ingest.zip_builder classify 98004
```

Runs `why_not_selling.classify_archetype` on every parcel. Zero API cost.
Writes archetype into `parcels_v3.signal_family`.

Stamps `archetypes_classified_at`.

**Status: IMPLEMENTED.** Safe to run.

### 5. `band` — assign Band 0-4

```bash
python -m backend.ingest.zip_builder band 98004
```

Applies banding logic: commercial/REO → Band 0, recent buyers → Band 0,
trust_aging → Band 2, financial_stress → Band 3, etc.

Stamps `bands_assigned_at`.

**Status: NOT YET IMPLEMENTED** — port from sandbox `apply_banding.py`.

### 6. `investigate` — run Option A SerpAPI investigation

First, always dry-run:

```bash
python -m backend.ingest.zip_builder investigate 98004 --dry-run
```

This shows the cost estimate without spending any SerpAPI credits.
Expected: ~$9 for a fresh ZIP (50 parcels screened + 15 deep).

Then for real:

```bash
python -m backend.ingest.zip_builder investigate 98004
```

Populates `investigations_v3` with signal inventory + pressure-scored
recommendations.

Stamps `first_investigation_at` and updates `investigated_count`.

**Status: NOT YET WIRED TO CLI.** Underlying investigation engine
works (tested live on 98004 earlier); needs CLI wiring next session.

### 7. `publish` — flip status to live

```bash
python -m backend.ingest.zip_builder publish 98004
```

Safety checks:
- All prior stages must have completed (stamps present)
- `parcel_count > 0`
- `investigated_count > 0`

Use `--force` to override safety checks. Not recommended.

Stamps `went_live_at` and sets `status = 'live'`. After this, agents can
subscribe to the ZIP and the API endpoints will serve briefings.

**Status: IMPLEMENTED.** Safe to run.

## Utility commands

### `status` — show build progress

```bash
python -m backend.ingest.zip_builder status 98004
```

Prints a checklist of which stages have completed.

### `pause` — hide a live ZIP

```bash
python -m backend.ingest.zip_builder pause 98004 --note "data refresh in progress"
```

Flips status to `paused`. API returns 404 for the ZIP. Existing
subscriptions stay intact — this is for emergency hiding, not cancellation.

## Building 98004 end-to-end

The first real build will look like:

```bash
# 1. Register (instant)
python -m backend.ingest.zip_builder register 98004 --market WA_KING --city Bellevue --state WA

# 2. Ingest (1-2 minutes, ~6500 parcels expected for 98004)
python -m backend.ingest.zip_builder ingest 98004

# 3. Classify (instant — no API calls)
python -m backend.ingest.zip_builder classify 98004

# 4. Band (instant — no API calls)
python -m backend.ingest.zip_builder band 98004

# 5. Dry-run investigation to see projected cost
python -m backend.ingest.zip_builder investigate 98004 --dry-run

# 6. Real investigation (~30-60s, ~$9 of SerpAPI)
python -m backend.ingest.zip_builder investigate 98004

# 7. Validate by hitting the API
curl http://localhost:8000/api/briefings/98004

# 8. Publish
python -m backend.ingest.zip_builder publish 98004
```

## Verification checklist

After `publish`:
- [ ] `GET /api/coverage` returns 98004 in the list
- [ ] `GET /api/briefings/98004` returns a populated playbook (5/3/2)
- [ ] `GET /api/map/98004` returns parcels with lat/lng
- [ ] `GET /api/parcels/<pin>` returns dossier for a known Band 3 pin
- [ ] `GET /api/parcels/<pin>/why` returns forensic read for a non-action pin
- [ ] Clicking a pin in the frontend (next session) loads Street View

## If something goes wrong

**Ingest failed partway.** Re-run `ingest` — it's idempotent, upserts
on pin. Existing parcels get refreshed, missing ones added.

**Classify produced weird archetypes.** Check `why_not_selling.py`
archetype priority rules. Re-run `classify` — new rules override old
archetypes.

**Investigation spent more than expected.** Check `serpapi_budget_v3`
for the current month's usage. Verify `MAX_SEARCHES_PER_RUN` env var
is set correctly (default 800).

**ZIP went live but briefing is empty.** Check `investigated_count` is
non-zero. Check `zip_coverage_v3.status = 'live'`. Check `parcels_v3`
has rows for this ZIP. Use `status` command to see where you are.

**Need to rebuild from scratch.** Don't delete the coverage row. Instead:
```bash
# Just re-run the stages — they all upsert
python -m backend.ingest.zip_builder ingest 98004
python -m backend.ingest.zip_builder classify 98004
# etc.
```

If you really need to clear everything for a ZIP:
```sql
DELETE FROM investigations_v3 WHERE zip_code = '98004';
DELETE FROM parcels_v3 WHERE zip_code = '98004';
UPDATE zip_coverage_v3 SET
    status = 'in_development',
    parcels_ingested_at = NULL,
    archetypes_classified_at = NULL,
    bands_assigned_at = NULL,
    first_investigation_at = NULL,
    went_live_at = NULL,
    parcel_count = 0,
    investigated_count = 0,
    current_call_now_count = 0
WHERE zip_code = '98004';
```

Never delete the `zip_coverage_v3` row itself — RLS and foreign-key
cascades could break cleanly.
