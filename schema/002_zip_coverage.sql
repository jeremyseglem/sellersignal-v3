-- ============================================================================
-- SellerSignal v3 — Migration 002: ZIP Coverage
-- ============================================================================
-- Adds zip_coverage_v3 — the source of truth for which ZIPs SellerSignal
-- supports right now. Separate from agent_territories_v3, which tracks
-- sales/subscriptions. A ZIP must be 'live' in coverage before any
-- agent can subscribe to it.
--
-- ZIP build lifecycle:
--   in_development  — ingest + classification + investigation in progress
--   live            — ready for agent subscriptions, briefings generate
--   paused          — temporarily hidden (data issue, investigation budget pause)
--   archived        — deprecated, do not re-enable without data refresh
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS zip_coverage_v3 (
    zip_code            TEXT PRIMARY KEY,
    market_key          TEXT NOT NULL,         -- WA_KING, FL_MD, AZ_MARICOPA, etc.
    city                TEXT,
    state               TEXT,

    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'in_development',
                        -- in_development | live | paused | archived

    -- Build progress tracking (null = step not yet completed)
    parcels_ingested_at       TIMESTAMPTZ,
    parcels_geocoded_at       TIMESTAMPTZ,
    archetypes_classified_at  TIMESTAMPTZ,
    bands_assigned_at         TIMESTAMPTZ,
    first_investigation_at    TIMESTAMPTZ,
    went_live_at              TIMESTAMPTZ,

    -- Counts (denormalized for fast status checks, refreshed by builder)
    parcel_count              INTEGER NOT NULL DEFAULT 0,
    investigated_count        INTEGER NOT NULL DEFAULT 0,
    current_call_now_count    INTEGER NOT NULL DEFAULT 0,

    -- Data provenance
    source_arcgis_url         TEXT,
    last_arcgis_edit_at       TIMESTAMPTZ,
    last_refresh_at           TIMESTAMPTZ,

    -- Notes (operator-visible)
    admin_notes               TEXT,

    -- Standard timestamps
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT zip_coverage_v3_status_valid CHECK (
        status IN ('in_development', 'live', 'paused', 'archived')
    )
);

CREATE INDEX IF NOT EXISTS idx_zip_coverage_v3_status
    ON zip_coverage_v3(status);

CREATE INDEX IF NOT EXISTS idx_zip_coverage_v3_market
    ON zip_coverage_v3(market_key);


-- ============================================================================
-- Seed the first ZIP: 98004 (Bellevue, WA)
-- ============================================================================
-- Marked 'in_development' — will flip to 'live' once the build lifecycle
-- completes in the next session. This is the reference ZIP we use to
-- validate the build machinery before opening coverage to more territories.
-- ============================================================================

INSERT INTO zip_coverage_v3 (zip_code, market_key, city, state, status, source_arcgis_url)
VALUES (
    '98004',
    'WA_KING',
    'Bellevue',
    'WA',
    'in_development',
    'https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0'
)
ON CONFLICT (zip_code) DO NOTHING;


-- ============================================================================
-- RLS — anyone authenticated can read live coverage, service role bypasses
-- ============================================================================

ALTER TABLE zip_coverage_v3 ENABLE ROW LEVEL SECURITY;

-- Authenticated users can see live + paused ZIPs (for display)
-- In-development + archived are service-role only
CREATE POLICY authenticated_read_visible_zips ON zip_coverage_v3
    FOR SELECT
    USING (status IN ('live', 'paused'));

COMMIT;


-- ============================================================================
-- Helper view: live ZIPs only (convenience for the frontend)
-- ============================================================================

CREATE OR REPLACE VIEW live_zips_v3 AS
SELECT zip_code, market_key, city, state,
       parcel_count, current_call_now_count, went_live_at
FROM zip_coverage_v3
WHERE status = 'live'
ORDER BY went_live_at DESC;


-- ============================================================================
-- Post-deploy verification
-- ============================================================================
-- After applying:
--   SELECT zip_code, status, parcel_count FROM zip_coverage_v3;
--   -- Expect: one row, 98004, in_development, 0
-- ============================================================================
