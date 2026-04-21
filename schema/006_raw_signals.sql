-- ═══════════════════════════════════════════════════════════════════════
-- raw_signals_v3
-- ═══════════════════════════════════════════════════════════════════════
-- Landing table for every filing/record harvested from primary sources.
-- One row per court case / obituary / UCC-1 / SOS filing / listing event.
-- The matcher reads from here, resolves party_names against
-- owner_canonical_v3, and writes high-confidence matches into the
-- existing investigations_v3 flow so the scoring engine processes them
-- naturally.
--
-- This replaces SerpAPI's role as the PRIMARY signal discovery layer.
-- SerpAPI stays as a narrow fallback for Deep Signal validation only.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS raw_signals_v3 (
    id                 BIGSERIAL PRIMARY KEY,

    -- Where it came from
    source_type        TEXT NOT NULL,
    -- ENUM values (enforced at harvester level, not DB level, for flexibility):
    --   'wa_state_courts'     KC Superior / WA state court filings
    --   'kc_recorder'         KC Recorder deeds/NODs/lis pendens
    --   'obituary_rss'        Newspaper + funeral home obituary feeds
    --   'legacy_com'          Legacy.com obituary aggregator
    --   'wa_sos'              WA Secretary of State corporate filings
    --   'zillow_sitemap'      Zillow listing history via sitemap
    --   'kc_assessor'         KC Assessor deed transfers
    --   'nyc_acris_ucc'       NYC ACRIS UCC filings (coop-ready)
    --   'serpapi_fallback'    SerpAPI result (deprioritized, only when no other hit)

    signal_type        TEXT NOT NULL,
    -- ENUM values:
    --   'probate', 'divorce', 'nod', 'trustee_sale', 'lis_pendens',
    --   'quit_claim', 'deed_transfer', 'obituary', 'death_certificate',
    --   'llc_officer_change', 'llc_dissolution', 'listing_new',
    --   'listing_delisted', 'listing_status_change', 'foreclosure_auction',
    --   'ucc1_coop', 'ucc3_coop', 'rptt_coop'

    trust_level        TEXT NOT NULL DEFAULT 'medium',
    -- 'high'   = court_record, legal_filing, obituary_rss (strict match alone -> call_now)
    -- 'medium' = listing_site, state_filing (needs corroboration for call_now)
    -- 'low'    = web_match, surname_only (candidate pool, waits for corroboration)

    -- Who + when
    party_names        JSONB NOT NULL,
    -- Array of {raw, normalized, role} objects.
    -- role = 'decedent' | 'petitioner' | 'respondent' | 'grantor' | 'grantee' | etc
    -- Example:
    --   [{"raw": "SMITH, JOHN Q", "normalized": {"first":"John","last":"Smith","middle":"Q"}, "role":"decedent"}]

    event_date         DATE,
    -- The filing date / death date / listing change date
    -- Normalize timezone at harvest time. Null only if truly unknown.

    -- Where (if known)
    jurisdiction       TEXT,
    -- 'WA_KING', 'WA_STATE', 'NY_MANHATTAN', etc.
    -- Follows the canonical form STATE_COUNTY or STATE_STATE for statewide sources.

    property_hint      JSONB,
    -- Optional. Captured when the source identifies a property directly
    -- (e.g. deed records, probate inventories mentioning real property).
    -- {address, city, state, zip, parcel_id, unit, block, lot, etc}
    -- Null for most court filings (probate filings rarely list properties).

    -- Provenance
    document_ref       TEXT,
    -- Case number, instrument number, URL, obituary ID, etc.
    -- Should be unique within (source_type, document_ref) -- dedup key.

    raw_data           JSONB,
    -- Original scraped payload for audit/reprocessing.
    -- Keeps us honest: if the matcher produces bad results we can re-run
    -- without re-scraping.

    -- Matcher state
    matched_at         TIMESTAMPTZ,
    -- Null = not yet processed by matcher
    -- Non-null = matcher has seen this row (may have 0, 1, or N matches)

    match_count        INTEGER NOT NULL DEFAULT 0,
    -- How many parcels this signal was matched to
    -- 0 = processed but no parcels matched
    -- 1 = clean match (most common)
    -- 2+ = ambiguous (same name in multiple parcels - flag for review)

    -- Lifecycle
    harvested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Dedup constraint: same source + same document ref = same row
    CONSTRAINT raw_signals_v3_unique_doc UNIQUE (source_type, document_ref)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_raw_signals_party_names
    ON raw_signals_v3 USING GIN (party_names);

CREATE INDEX IF NOT EXISTS idx_raw_signals_event_date
    ON raw_signals_v3 (event_date DESC);

CREATE INDEX IF NOT EXISTS idx_raw_signals_jurisdiction
    ON raw_signals_v3 (jurisdiction);

CREATE INDEX IF NOT EXISTS idx_raw_signals_unmatched
    ON raw_signals_v3 (harvested_at DESC)
    WHERE matched_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_raw_signals_source_type
    ON raw_signals_v3 (source_type, signal_type);

-- Auto-touch updated_at on any update
CREATE OR REPLACE FUNCTION raw_signals_v3_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS raw_signals_v3_touch ON raw_signals_v3;
CREATE TRIGGER raw_signals_v3_touch
BEFORE UPDATE ON raw_signals_v3
FOR EACH ROW
EXECUTE FUNCTION raw_signals_v3_touch();


-- ═══════════════════════════════════════════════════════════════════════
-- raw_signal_matches_v3
-- ═══════════════════════════════════════════════════════════════════════
-- Join table: one row per (raw_signal, parcel) match. Links harvested
-- signals to the parcels they apply to. Populated by the matcher.
--
-- A single raw_signal can match multiple parcels (e.g. probate of a person
-- who owned 3 parcels). Each of those relationships is a row here.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS raw_signal_matches_v3 (
    id                 BIGSERIAL PRIMARY KEY,
    raw_signal_id      BIGINT NOT NULL REFERENCES raw_signals_v3(id) ON DELETE CASCADE,
    pin                TEXT NOT NULL,

    match_strength     TEXT NOT NULL,
    -- 'strict'      first + last + (middle OR suffix) match
    -- 'surname'     surname + role-inferred match only (LOW confidence)
    -- 'llc_exact'   LLC name exact match in canonical form
    -- 'trust_name'  trust name match

    match_method       TEXT NOT NULL,
    -- 'canonicalizer_strict', 'surname_fallback', 'entity_exact', etc

    matched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT raw_signal_match_unique UNIQUE (raw_signal_id, pin)
);

CREATE INDEX IF NOT EXISTS idx_raw_signal_matches_pin
    ON raw_signal_matches_v3 (pin);

CREATE INDEX IF NOT EXISTS idx_raw_signal_matches_strength
    ON raw_signal_matches_v3 (match_strength);


-- ═══════════════════════════════════════════════════════════════════════
-- NOTES
-- ═══════════════════════════════════════════════════════════════════════
-- 1) This is a LANDING table design. Harvesters write here without
--    checking if the signal matches a parcel. The matcher runs async
--    afterward and produces the raw_signal_matches_v3 rows.
--
-- 2) Matched signals feed the existing investigations_v3 flow. The
--    scoring engine doesn't need to know about raw_signals_v3 -- it
--    just sees new signals in investigations_v3 and scores them.
--
-- 3) When a raw_signal matches N parcels, N rows get written to
--    investigations_v3 (one per matched parcel). Scoring is per-parcel
--    regardless of source.
--
-- 4) The unique constraint on (source_type, document_ref) prevents
--    re-harvesting the same record. If a harvester runs twice, the
--    ON CONFLICT DO UPDATE lets us refresh raw_data without duplicating.
