-- ============================================================================
-- 008_ereal_property.sql — Sales history from KC eReal Property portal
-- ============================================================================
-- The King County Assessor's eReal Property portal
-- (blue.kingcounty.com/Assessor/eRealProperty/Detail.aspx?ParcelNbr=XXX)
-- publishes per-parcel detail pages with owner name, building details,
-- and full sales history. This migration adds:
--
--   1. sales_history_v3 — one row per recorded transfer. Parcels can
--      have 0, 1, or many. Sales are not guaranteed unique on recording
--      number because the assessor occasionally republishes; the key is
--      (pin, recording_number).
--
--   2. parcel_ereal_meta_v3 — a sidecar with per-parcel provenance: when
--      we last successfully fetched the detail page, how many sales we
--      parsed, and any error. Separate from parcels_v3 so we can batch-
--      check freshness without loading the full parcel row.
--
-- Owner name, year_built, sqft come back into parcels_v3 directly via
-- the eReal harvester upsert — those columns exist in the 001_initial
-- schema but were never populated. This migration doesn't change
-- parcels_v3.
-- ============================================================================

CREATE TABLE IF NOT EXISTS sales_history_v3 (
    pin                 TEXT NOT NULL REFERENCES parcels_v3(pin) ON DELETE CASCADE,
    recording_number    TEXT NOT NULL,         -- KC recorder document ID
    excise_number       TEXT,                  -- KC excise tax identifier
    sale_date           DATE,
    sale_price          BIGINT,
    seller_name         TEXT,
    buyer_name          TEXT,
    instrument          TEXT,                  -- 'Statutory Warranty Deed', 'Quit Claim', etc.
    sale_reason         TEXT,                  -- 'None', 'Gift', 'Estate', 'Divorce', etc.
    -- Derived helpers
    is_arms_length      BOOLEAN,               -- nullable; set by classifier at ingest
    source_fetched_at   TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (pin, recording_number)
);

CREATE INDEX IF NOT EXISTS idx_sales_pin        ON sales_history_v3(pin);
CREATE INDEX IF NOT EXISTS idx_sales_date       ON sales_history_v3(pin, sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_sales_reason     ON sales_history_v3(sale_reason) WHERE sale_reason IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sales_arms_length ON sales_history_v3(is_arms_length) WHERE is_arms_length = FALSE;


CREATE TABLE IF NOT EXISTS parcel_ereal_meta_v3 (
    pin                 TEXT PRIMARY KEY REFERENCES parcels_v3(pin) ON DELETE CASCADE,
    fetched_at          TIMESTAMPTZ,           -- last successful fetch
    last_attempt_at     TIMESTAMPTZ,           -- last attempt (success or fail)
    last_error          TEXT,                  -- brief error message; NULL on success
    consecutive_errors  INTEGER DEFAULT 0,
    http_status         INTEGER,               -- most recent HTTP status
    body_length         INTEGER,               -- most recent response body size
    sales_count         INTEGER,               -- sales parsed from this fetch
    -- Parser version so we can re-run when logic changes without
    -- re-fetching if body didn't change.
    parser_version      TEXT
);

CREATE INDEX IF NOT EXISTS idx_ereal_meta_fetched
    ON parcel_ereal_meta_v3(fetched_at);
CREATE INDEX IF NOT EXISTS idx_ereal_meta_needs_fetch
    ON parcel_ereal_meta_v3(pin) WHERE fetched_at IS NULL;
