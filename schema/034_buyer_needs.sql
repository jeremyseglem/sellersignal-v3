-- 034: Marketplace demand side (dark launch) — buyer needs + match runs.
--
-- Access model: these tables are reachable ONLY through the backend service
-- role. RLS is enabled with NO policies, so anon/authenticated Supabase
-- clients cannot read or write anything. The API layer adds its own gate
-- (admin key or MARKETPLACE_ALLOWLIST) on top.
--
-- Apply via Supabase SQL Editor (see docs/SCHEMA_APPLY.md).

CREATE TABLE IF NOT EXISTS buyer_needs_v3 (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by      TEXT NOT NULL,                  -- email of the creator (allowlist identity or 'admin')
    client_ref      TEXT,                           -- creator's private label for the buyer; never crosses sides
    status          TEXT NOT NULL DEFAULT 'active', -- active | paused | expired | fulfilled
    zips            TEXT[] NOT NULL,
    streets         TEXT[],                         -- optional street filters, matched case-insensitively against address
    price_min       BIGINT,
    price_max       BIGINT,
    prop_types      TEXT[],                         -- e.g. {R,K}; NULL/empty = any
    beds_min        INT,
    baths_min       NUMERIC,
    year_built_min  INT,
    year_built_max  INT,
    sqft_min        INT,
    acres_min       NUMERIC,
    acres_max       NUMERIC,
    soft_notes      TEXT,                           -- Tier-3 free text; shown as context, never machine-matched
    attestation     BOOLEAN NOT NULL DEFAULT FALSE, -- real-client attestation
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyer_needs_status
    ON buyer_needs_v3 (status);

CREATE TABLE IF NOT EXISTS need_match_runs_v3 (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    need_id     UUID NOT NULL REFERENCES buyer_needs_v3(id) ON DELETE CASCADE,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    candidates  INT NOT NULL DEFAULT 0,             -- parcels considered across all zips
    matched     INT NOT NULL DEFAULT 0,             -- parcels surviving hard filters
    report      JSONB                               -- per-zip / per-tier summary + field-coverage stats
);

CREATE INDEX IF NOT EXISTS idx_need_match_runs_need
    ON need_match_runs_v3 (need_id, run_at DESC);

CREATE TABLE IF NOT EXISTS need_matches_v3 (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES need_match_runs_v3(id) ON DELETE CASCADE,
    need_id     UUID NOT NULL,
    pin         TEXT NOT NULL,
    zip_code    TEXT NOT NULL,
    score       NUMERIC NOT NULL DEFAULT 0,         -- confirmed-passed / specified criteria
    tier        TEXT NOT NULL DEFAULT 'C',          -- A = court signal | B = structural archetype | C = other
    matched_on  TEXT[],                             -- criteria confirmed passed
    unknown_on  TEXT[],                             -- criteria unverifiable (field null in this market)
    detail      JSONB,                              -- parcel context snapshot at match time
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_need_matches_run
    ON need_matches_v3 (run_id);
CREATE INDEX IF NOT EXISTS idx_need_matches_need
    ON need_matches_v3 (need_id, created_at DESC);

-- Lock the tables: RLS on, zero policies. Only the service role (backend)
-- can touch these rows.
ALTER TABLE buyer_needs_v3     ENABLE ROW LEVEL SECURITY;
ALTER TABLE need_match_runs_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE need_matches_v3    ENABLE ROW LEVEL SECURITY;
