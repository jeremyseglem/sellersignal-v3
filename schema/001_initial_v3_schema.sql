-- ============================================================================
-- SellerSignal v3 — Clean Schema
-- ============================================================================
-- Clean rebuild. No carrying over v1 tables or their contaminated scoring data.
-- Use the existing `parcels` table for raw ingestion data (addresses, owner
-- names, values) — that data is clean, just the scoring built on top of it
-- was the problem.
--
-- All v3 tables are suffixed `_v3` so they can coexist with legacy v1/v2
-- tables in the same Supabase project during the transition period.
-- After v3 is stable and v1 is fully decommissioned, rename v3 tables to
-- drop the suffix.
-- ============================================================================

BEGIN;


-- ============================================================================
-- parcels_v3 — Raw parcel data (address, owner, value)
-- ============================================================================
-- NOTE: If re-using the existing v1 `parcels` table, skip this block. It has
-- the same raw data and v3 can read from it without modification. Only create
-- this table if doing a full data re-ingest.
--
-- This is a superset of v1 parcels — includes lat/lng for the map, and a
-- `data_freshness_at` timestamp so we can tell how stale the underlying
-- assessor data is.
-- ============================================================================
CREATE TABLE IF NOT EXISTS parcels_v3 (
    pin              TEXT PRIMARY KEY,
    zip_code         TEXT NOT NULL,
    market_key       TEXT NOT NULL,
    address          TEXT,
    city             TEXT,
    state            TEXT,

    -- Owner information
    owner_name_raw   TEXT,
    owner_name       TEXT,    -- normalized display name (Title Case for individuals)
    owner_type       TEXT,    -- individual | trust | llc | estate | heirs | ranch | unknown
    owner_address    TEXT,
    owner_city       TEXT,
    owner_state      TEXT,
    owner_zip        TEXT,

    -- Geography
    lat              NUMERIC(10, 7),
    lng              NUMERIC(10, 7),

    -- Property details
    total_value      BIGINT,
    land_value       BIGINT,
    building_value   BIGINT,
    sqft             INTEGER,
    year_built       INTEGER,
    acres            NUMERIC(10, 3),
    prop_type        TEXT,

    -- Transaction history
    last_transfer_date    DATE,
    last_transfer_price   BIGINT,
    tenure_years          NUMERIC(5, 1),

    -- Derived flags
    is_absentee      BOOLEAN DEFAULT FALSE,
    is_out_of_state  BOOLEAN DEFAULT FALSE,
    is_vacant_land   BOOLEAN DEFAULT FALSE,

    -- v3 classification (null = not yet banded)
    band             NUMERIC(2, 1),         -- 0, 1, 2, 2.5, 3, 4
    signal_family    TEXT,                  -- financial_stress | trust_aging | etc.

    -- Metadata
    data_freshness_at TIMESTAMPTZ,          -- when source ArcGIS layer was last edited
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parcels_v3_zip      ON parcels_v3(zip_code);
CREATE INDEX IF NOT EXISTS idx_parcels_v3_band     ON parcels_v3(zip_code, band) WHERE band IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_parcels_v3_family   ON parcels_v3(zip_code, signal_family);
CREATE INDEX IF NOT EXISTS idx_parcels_v3_location ON parcels_v3(lat, lng) WHERE lat IS NOT NULL;


-- ============================================================================
-- investigations_v3 — Signal inventory from SerpAPI (with trust tiers)
-- ============================================================================
-- One row per parcel per investigation. Upserts on (pin) — the most recent
-- investigation is the authoritative one. Historical investigations are
-- kept in investigations_v3_history via a trigger below.
-- ============================================================================
CREATE TABLE IF NOT EXISTS investigations_v3 (
    pin              TEXT PRIMARY KEY REFERENCES parcels_v3(pin) ON DELETE CASCADE,
    zip_code         TEXT NOT NULL,
    mode             TEXT NOT NULL,         -- 'screen' | 'deep'

    -- Signal inventory — JSONB array of signals
    -- Each signal: { type, category, trust: 'high'|'medium'|'low', detail, source_url? }
    signals          JSONB NOT NULL DEFAULT '[]'::jsonb,
    signal_count     INTEGER NOT NULL DEFAULT 0,

    -- Roll-up flags (computed from signals on insert)
    has_life_event     BOOLEAN NOT NULL DEFAULT FALSE,
    has_financial      BOOLEAN NOT NULL DEFAULT FALSE,
    has_blocker        BOOLEAN NOT NULL DEFAULT FALSE,
    identity_resolved  BOOLEAN NOT NULL DEFAULT FALSE,
    trust_summary      JSONB NOT NULL DEFAULT '{"high":0,"medium":0,"low":0}'::jsonb,

    -- Decision output (pressure-scored recommend_action)
    action_category    TEXT NOT NULL DEFAULT 'hold',   -- call_now | build_now | hold | avoid
    action_tone        TEXT,                           -- urgent | sensitive | relational | neutral
    action_pressure    INTEGER NOT NULL DEFAULT 0,     -- 0 | 1 | 2 | 3
    action_reason      TEXT,
    action_next_step   TEXT,

    -- Run metadata
    searches_used      INTEGER NOT NULL DEFAULT 0,
    cost_usd           NUMERIC(8, 4) NOT NULL DEFAULT 0,
    investigated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ NOT NULL             -- 90-day TTL for screen, 90 for deep
);

CREATE INDEX IF NOT EXISTS idx_investigations_v3_zip    ON investigations_v3(zip_code);
CREATE INDEX IF NOT EXISTS idx_investigations_v3_action ON investigations_v3(zip_code, action_category);
CREATE INDEX IF NOT EXISTS idx_investigations_v3_expiry ON investigations_v3(expires_at);


-- ============================================================================
-- briefings_v3 — Weekly playbook snapshots
-- ============================================================================
-- One row per ZIP per week. Provides the historical record of what was on
-- each playbook, so we can track outcomes ("did the 4451 91st Ave NE probate
-- lead actually sell within 6 months?") and tune the pressure model over
-- time with real outcome data.
-- ============================================================================
CREATE TABLE IF NOT EXISTS briefings_v3 (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zip_code         TEXT NOT NULL,
    week_of          DATE NOT NULL,           -- Monday of the briefing week

    -- Playbook content (denormalized snapshot — immutable once published)
    call_now         JSONB NOT NULL DEFAULT '[]'::jsonb,
    build_now        JSONB NOT NULL DEFAULT '[]'::jsonb,
    strategic_holds  JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Metrics at time of publish
    total_parcels       INTEGER,
    investigated_count  INTEGER,
    cost_usd            NUMERIC(8, 2),

    published_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(zip_code, week_of)
);

CREATE INDEX IF NOT EXISTS idx_briefings_v3_zip_week ON briefings_v3(zip_code, week_of DESC);


-- ============================================================================
-- outcomes_v3 — Did the lead actually sell? (for model tuning)
-- ============================================================================
CREATE TABLE IF NOT EXISTS outcomes_v3 (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pin              TEXT NOT NULL REFERENCES parcels_v3(pin) ON DELETE CASCADE,
    briefing_id      UUID REFERENCES briefings_v3(id) ON DELETE SET NULL,

    action_taken     TEXT,                    -- called | mailed | knocked | ignored
    outcome          TEXT,                    -- listed | sold | no_response | not_interested | pending
    outcome_date     DATE,
    outcome_price    BIGINT,
    notes            TEXT,

    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outcomes_v3_pin      ON outcomes_v3(pin);
CREATE INDEX IF NOT EXISTS idx_outcomes_v3_briefing ON outcomes_v3(briefing_id);


-- ============================================================================
-- serpapi_budget_v3 — Monthly search budget state
-- ============================================================================
CREATE TABLE IF NOT EXISTS serpapi_budget_v3 (
    month_key         TEXT PRIMARY KEY,       -- '2026-04' format
    searches_used     INTEGER NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(8, 2) NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================================
-- agent_territories_v3 — Which agent owns which ZIP (subscription)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_territories_v3 (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id            UUID NOT NULL,         -- Supabase auth user id
    zip_code            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',  -- active | cancelled | paused
    stripe_subscription_id TEXT,

    activated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at        TIMESTAMPTZ,

    UNIQUE(zip_code, status) DEFERRABLE INITIALLY IMMEDIATE  -- one active agent per ZIP
);

CREATE INDEX IF NOT EXISTS idx_territories_v3_agent  ON agent_territories_v3(agent_id);
CREATE INDEX IF NOT EXISTS idx_territories_v3_active ON agent_territories_v3(zip_code) WHERE status='active';


-- ============================================================================
-- Row-Level Security (RLS)
-- ============================================================================
-- Territory gating: agents can only read data for ZIPs they own.
-- Service role (backend) bypasses RLS.
-- ============================================================================

ALTER TABLE parcels_v3        ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigations_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefings_v3      ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes_v3       ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_territories_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE serpapi_budget_v3 ENABLE ROW LEVEL SECURITY;

-- Agents can read parcels in their active territories
CREATE POLICY agents_read_own_parcels ON parcels_v3
  FOR SELECT
  USING (
    zip_code IN (
      SELECT zip_code FROM agent_territories_v3
      WHERE agent_id = auth.uid() AND status = 'active'
    )
  );

-- Agents can read investigations in their active territories
CREATE POLICY agents_read_own_investigations ON investigations_v3
  FOR SELECT
  USING (
    zip_code IN (
      SELECT zip_code FROM agent_territories_v3
      WHERE agent_id = auth.uid() AND status = 'active'
    )
  );

-- Agents can read their briefings
CREATE POLICY agents_read_own_briefings ON briefings_v3
  FOR SELECT
  USING (
    zip_code IN (
      SELECT zip_code FROM agent_territories_v3
      WHERE agent_id = auth.uid() AND status = 'active'
    )
  );

-- Agents can read/write their own outcomes
CREATE POLICY agents_rw_own_outcomes ON outcomes_v3
  FOR ALL
  USING (
    pin IN (
      SELECT p.pin FROM parcels_v3 p
      JOIN agent_territories_v3 t ON t.zip_code = p.zip_code
      WHERE t.agent_id = auth.uid() AND t.status = 'active'
    )
  );

-- Agents can read their own territory records
CREATE POLICY agents_read_own_territories ON agent_territories_v3
  FOR SELECT
  USING (agent_id = auth.uid());

-- serpapi_budget_v3: service-role only.
-- RLS is enabled with no policies, which means anon/authenticated keys
-- get zero access. The backend uses the service_role key, which bypasses
-- RLS entirely. This is the correct locked-down posture for an internal
-- budget/spend tracker that should never be exposed to frontend clients.


COMMIT;

-- ============================================================================
-- Post-deploy verification
-- ============================================================================
-- Run these after applying the schema to confirm everything's in order:
--
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public' AND table_name LIKE '%_v3';
--
--   -- Should return: parcels_v3, investigations_v3, briefings_v3, outcomes_v3,
--   --                serpapi_budget_v3, agent_territories_v3
-- ============================================================================
