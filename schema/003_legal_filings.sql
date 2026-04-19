-- ============================================================================
-- SellerSignal v3 — Migration 003: Legal Filings
-- ============================================================================
-- Stores raw filings from manual CSV exports:
--   - KC Superior Court Family Law (dissolution filings)
--   - KC Recorder LandmarkWeb (NOD, Lis Pendens, Trustee Sale)
--
-- Source of truth is the uploaded CSV. Each upload adds rows; duplicates
-- (same case_number or recording_number) are deduped on insert.
--
-- Matches to parcels are stored separately so we can re-run matching
-- when ownership data changes without losing the underlying filing data.
-- ============================================================================

BEGIN;


-- ============================================================================
-- legal_filings_v3 — The raw legal filing records
-- ============================================================================
CREATE TABLE IF NOT EXISTS legal_filings_v3 (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core fields
    filing_kind        TEXT NOT NULL,         -- 'divorce' | 'recorder'
    filing_subtype     TEXT,                  -- 'dissolution_with_children'
                                              -- | 'notice_of_default'
                                              -- | 'trustee_sale' | 'lis_pendens'
    filing_date        DATE NOT NULL,
    case_or_rec_number TEXT NOT NULL,

    -- Party names (normalized strings as they appeared on filing)
    petitioner_name    TEXT,                  -- divorce cases
    respondent_name    TEXT,                  -- divorce cases
    grantor_names      TEXT[],                -- recorder docs (property owner being noticed)
    grantee_names      TEXT[],                -- recorder docs (lender / plaintiff)

    -- Direct parcel link when the filing includes it (recorder docs only)
    parcel_id_on_filing TEXT,

    -- Jurisdiction
    county             TEXT NOT NULL DEFAULT 'King',
    state              TEXT NOT NULL DEFAULT 'WA',
    market_key         TEXT NOT NULL DEFAULT 'WA_KING',

    -- Provenance
    source_csv_name    TEXT,                  -- filename of the upload
    uploaded_by        TEXT,                  -- admin identifier
    uploaded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Full raw row from CSV for debugging
    raw_row            JSONB,

    -- Indexing
    CONSTRAINT legal_filings_v3_kind_valid
        CHECK (filing_kind IN ('divorce', 'recorder'))
);

-- Dedup: same case number + same kind = same filing regardless of upload
CREATE UNIQUE INDEX IF NOT EXISTS idx_legal_filings_v3_uniq
    ON legal_filings_v3(filing_kind, case_or_rec_number);

CREATE INDEX IF NOT EXISTS idx_legal_filings_v3_date
    ON legal_filings_v3(filing_date DESC);

CREATE INDEX IF NOT EXISTS idx_legal_filings_v3_kind
    ON legal_filings_v3(filing_kind, filing_subtype);


-- ============================================================================
-- legal_filing_matches_v3 — Filing ↔ Parcel junction
-- ============================================================================
-- When a filing is ingested, we run the matcher against parcels_v3 and
-- write any matches here. Re-running matching is idempotent: we delete
-- prior rows for (filing_id) and re-insert.
-- ============================================================================
CREATE TABLE IF NOT EXISTS legal_filing_matches_v3 (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id          UUID NOT NULL REFERENCES legal_filings_v3(id) ON DELETE CASCADE,
    pin                TEXT NOT NULL REFERENCES parcels_v3(pin) ON DELETE CASCADE,
    zip_code           TEXT NOT NULL,

    match_path         TEXT NOT NULL,         -- 'direct_pin' | 'name_both' | 'name_one'
    match_strength     TEXT NOT NULL,         -- 'strong' | 'weak'

    -- Derived signal family (written to parcels_v3.signal_family when applied)
    derived_signal_family  TEXT NOT NULL,     -- 'financial_stress' | 'divorce_unwinding'

    -- Urgency tier (from recorder doc urgency_tier property)
    urgency_tier       TEXT,                  -- 'act_this_week' | 'active_window'

    -- When this match was computed
    matched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Whether the signal has been applied to parcels_v3.signal_family
    -- (set to TRUE when apply_filings runs re-banding for the affected pins)
    applied_to_parcel  BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT legal_filing_matches_v3_path_valid
        CHECK (match_path IN ('direct_pin', 'name_both', 'name_one')),
    CONSTRAINT legal_filing_matches_v3_strength_valid
        CHECK (match_strength IN ('strong', 'weak'))
);

CREATE INDEX IF NOT EXISTS idx_legal_filing_matches_v3_pin
    ON legal_filing_matches_v3(pin);
CREATE INDEX IF NOT EXISTS idx_legal_filing_matches_v3_zip
    ON legal_filing_matches_v3(zip_code);
CREATE INDEX IF NOT EXISTS idx_legal_filing_matches_v3_filing
    ON legal_filing_matches_v3(filing_id);


-- ============================================================================
-- RLS — service-role only
-- ============================================================================
-- Legal filings contain PII that isn't ready for public consumption.
-- Lock down to service role; frontend consumes derived `parcels_v3.signal_family`
-- and `investigations_v3.action_*` fields instead.
-- ============================================================================

ALTER TABLE legal_filings_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_filing_matches_v3 ENABLE ROW LEVEL SECURITY;

-- No policies created — service_role bypasses RLS, anon has no access.

COMMIT;


-- ============================================================================
-- Post-deploy verification
-- ============================================================================
-- After applying:
--   SELECT COUNT(*) FROM legal_filings_v3;          -- 0
--   SELECT COUNT(*) FROM legal_filing_matches_v3;   -- 0
--   \d legal_filings_v3                             -- schema check
-- ============================================================================
