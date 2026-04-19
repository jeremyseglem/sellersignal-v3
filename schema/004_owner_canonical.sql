-- ============================================================================
-- SellerSignal v3 — Migration 004: Owner Canonical
-- ============================================================================
-- Sidecar table storing structured parses of parcels_v3.owner_name.
--
-- Rationale: raw Assessor owner strings are heterogeneous (~13 different
-- shapes including "First Last", "Last First", "Last First+Spouse-trust",
-- "<name> Family Trust+Ttees", pure LLCs, companies with people embedded).
-- A single-pass token match produces false positives (e.g. "ROBERT LEE
-- HARRIS" decedent matched "Robert Lee Steil" owner as pressure=3 CALL NOW).
--
-- Parsing is done via Claude Haiku 4.5 at ingest time and cached here.
-- Re-parse only when parcels_v3.owner_name changes for a PIN.
--
-- Legal filings matcher joins against this table (not parcels_v3 directly)
-- to compute STRONG (surname + given match) vs SURNAME_ONLY (surname only)
-- match tiers.
-- ============================================================================

BEGIN;


-- ============================================================================
-- owner_canonical_v3 — parsed owner names
-- ============================================================================
CREATE TABLE IF NOT EXISTS owner_canonical_v3 (
    pin             TEXT PRIMARY KEY REFERENCES parcels_v3(pin) ON DELETE CASCADE,

    -- Primary owner (first human listed, if any)
    surname_primary TEXT,                   -- "" for pure entities
    given_primary   TEXT,                   -- first given name
    given_all       TEXT[] DEFAULT '{}',    -- all given-name tokens for primary

    -- All surnames appearing in the string (primary + all co-owners)
    -- Indexed for surname-based lookup during legal-filings matching
    surnames_all    TEXT[] DEFAULT '{}',

    -- Entity classification
    entity_type     TEXT NOT NULL,          -- individual | trust | llc | company | unknown
    entity_name     TEXT,                   -- trust name / LLC name if any

    -- Co-owners as JSONB: [{"surname": "AUSLANDER", "given": ["MARY"]}, ...]
    co_owners       JSONB DEFAULT '[]'::jsonb,

    -- Parser metadata
    confidence      REAL NOT NULL DEFAULT 1.0,   -- 0.0-1.0 parser self-report
    raw_name        TEXT NOT NULL,                -- the owner_name we parsed
    model           TEXT NOT NULL,                -- 'claude-haiku-4-5-20251001' | 'rules-v1'

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT owner_canonical_v3_entity_valid
        CHECK (entity_type IN ('individual', 'trust', 'llc', 'company', 'unknown'))
);

-- Single-surname lookup (primary match path)
CREATE INDEX IF NOT EXISTS idx_owner_canonical_v3_surname
    ON owner_canonical_v3(surname_primary) WHERE surname_primary <> '';

-- Array-contains lookup for `decedent_surname = ANY(surnames_all)`
-- GIN index required for efficient array membership queries
CREATE INDEX IF NOT EXISTS idx_owner_canonical_v3_surnames_gin
    ON owner_canonical_v3 USING gin (surnames_all);

-- Re-parse detection: find rows where parcels_v3.owner_name changed
CREATE INDEX IF NOT EXISTS idx_owner_canonical_v3_raw
    ON owner_canonical_v3(raw_name);

-- Low-confidence queue for manual review
CREATE INDEX IF NOT EXISTS idx_owner_canonical_v3_low_conf
    ON owner_canonical_v3(confidence) WHERE confidence < 0.7;


-- ============================================================================
-- RLS — service-role only
-- ============================================================================
ALTER TABLE owner_canonical_v3 ENABLE ROW LEVEL SECURITY;
-- service_role bypasses RLS; no anon access.

COMMIT;


-- ============================================================================
-- Post-deploy verification
-- ============================================================================
-- After applying:
--   SELECT COUNT(*) FROM owner_canonical_v3;          -- 0
--   \d owner_canonical_v3                             -- schema check
--
-- Backfill command (run separately after deploy):
--   python -m backend.ingest.backfill_owner_canonical 98004 --dry-run
--   python -m backend.ingest.backfill_owner_canonical 98004
-- ============================================================================
