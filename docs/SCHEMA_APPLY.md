# Schema Apply Guide

How to apply the v3 schema to Supabase.

## Before you start

- [ ] You have Supabase project access (dashboard owner or service-role key)
- [ ] You've backed up any v1/v2 data you want to preserve (these migrations
      are non-destructive — everything uses `_v3` suffix — but belt and
      suspenders)
- [ ] `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set in your local env
      (for post-migration verification via `backend/`)

## Apply order (run in sequence)

1. **`001_initial_v3_schema.sql`** — creates parcels_v3, investigations_v3,
   briefings_v3, outcomes_v3, serpapi_budget_v3, agent_territories_v3
   with RLS policies
2. **`002_zip_coverage.sql`** — creates zip_coverage_v3 + seeds 98004 as
   in_development

## Applying via Supabase SQL Editor (recommended)

1. Open your Supabase project dashboard
2. Navigate to **SQL Editor** in the left sidebar
3. Click **+ New query**
4. Paste the full contents of `schema/001_initial_v3_schema.sql`
5. Click **Run**
6. Confirm success — should see `Success. No rows returned.`
7. Repeat steps 3–6 for `schema/002_zip_coverage.sql`

## Verification queries

After applying both migrations, run these in the SQL Editor to verify:

### 1. All tables exist
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE '%_v3'
ORDER BY table_name;
```

Expected output:
```
agent_territories_v3
briefings_v3
investigations_v3
outcomes_v3
parcels_v3
serpapi_budget_v3
zip_coverage_v3
```

### 2. ZIP 98004 is seeded
```sql
SELECT zip_code, market_key, city, state, status
FROM zip_coverage_v3;
```

Expected:
```
98004 | WA_KING | Bellevue | WA | in_development
```

### 3. RLS is enabled
```sql
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public' AND tablename LIKE '%_v3';
```

All rows should show `rowsecurity = t` (true).

### 4. Indexes are created
```sql
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public' AND tablename LIKE '%_v3'
ORDER BY tablename, indexname;
```

Expected indexes (non-exhaustive — primary keys are also present):
- `idx_parcels_v3_zip`, `idx_parcels_v3_band`, `idx_parcels_v3_location`
- `idx_investigations_v3_zip`, `idx_investigations_v3_action`,
  `idx_investigations_v3_expiry`
- `idx_briefings_v3_zip_week`
- `idx_outcomes_v3_pin`, `idx_outcomes_v3_briefing`
- `idx_territories_v3_agent`, `idx_territories_v3_active`
- `idx_zip_coverage_v3_status`, `idx_zip_coverage_v3_market`

### 5. Live-zip view works
```sql
SELECT * FROM live_zips_v3;
```

Should return 0 rows (nothing live yet until 98004 is published).

## Post-migration smoke test via backend

From the repo root, with env vars set:

```bash
python3 -m backend.ingest.zip_builder status 98004
```

Expected output (condensed):
```
═══ ZIP 98004 — Bellevue, WA (WA_KING) ═══
  Status:              in_development
  Parcels ingested:    0
  Investigated:        0
  Current CALL NOW:    0

  Build progress:
    [✓] Registered                  2026-04-18T15:30:00
    [ ] Parcels ingested            —
    [ ] Parcels geocoded            —
    [ ] Archetypes classified       —
    [ ] Bands assigned              —
    [ ] First investigation         —
    [ ] Went live                   —
```

If you see this, the schema is applied correctly and the CLI can talk to
Supabase. You're ready to run the actual build.

## Rollback

The v3 migrations are non-destructive — they never touch existing v1/v2
tables. If you need to undo them entirely:

```sql
BEGIN;
DROP VIEW IF EXISTS live_zips_v3;
DROP TABLE IF EXISTS outcomes_v3 CASCADE;
DROP TABLE IF EXISTS agent_territories_v3 CASCADE;
DROP TABLE IF EXISTS briefings_v3 CASCADE;
DROP TABLE IF EXISTS investigations_v3 CASCADE;
DROP TABLE IF EXISTS serpapi_budget_v3 CASCADE;
DROP TABLE IF EXISTS zip_coverage_v3 CASCADE;
DROP TABLE IF EXISTS parcels_v3 CASCADE;
COMMIT;
```

This is clean — v1 tables (parcels, investigation_cache, deep_signals,
etc.) are completely untouched.

## Applying future migrations

The pattern going forward: every new migration gets a sequential number
and a clear description:

```
schema/003_add_agent_profiles.sql
schema/004_add_outcome_tracking.sql
```

Always apply in order. Never skip a number. Always include a `BEGIN/COMMIT`
block so partial failures don't leave the database in a broken state.
