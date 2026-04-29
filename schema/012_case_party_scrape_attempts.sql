-- ═══════════════════════════════════════════════════════════════════════
-- case_party_scrape_attempts
-- ═══════════════════════════════════════════════════════════════════════
-- Tracks each attempt to scrape the Participants tab for a court case,
-- separating "we tried and failed" from "the case has no participants."
--
-- Before this table existed, both outcomes were stored in case_parties_v3
-- as sentinel rows (raw_role='(no participants found)'). That conflated
-- transient portal failures with genuine empty results: once a sentinel
-- existed, the dedup check skipped the case forever, even if the failure
-- was a temporary KC portal hiccup.
--
-- Now: case_parties_v3 holds ONLY real party data. case_party_scrape_attempts
-- holds attempt history and retry state. The selection logic combines the
-- two to decide whether to retry a case.
--
-- Retry eligibility (computed in backend.api.harvest._is_eligible_for_scrape):
--   status='success'         → never retry (we have real data already)
--   status='genuinely_empty' → never retry (scraper confirmed empty)
--   any other status         → retry once age >= backoff(attempt_count):
--     attempt 1 fail → 1h
--     attempt 2 fail → 6h
--     attempt 3 fail → 24h
--     attempt 4+ fail → 7d
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS case_party_scrape_attempts (
    id                BIGSERIAL PRIMARY KEY,

    case_number       TEXT NOT NULL,
    source_type       TEXT NOT NULL DEFAULT 'kc_superior_court',

    -- Outcome of the most recent attempt:
    --   'success'          — parties were found and stored in case_parties_v3
    --   'genuinely_empty'  — participants table loaded, but had no rows
    --   'shell_page'       — portal returned 28KB shell, never authorized
    --   'network_error'    — request exception after retries
    --   'other'            — anything else (e.g. parse exception, DB error)
    status            TEXT NOT NULL,

    -- First 500 chars of the error message / context, for debugging
    error_detail      TEXT,

    -- Total attempts (counting this one)
    attempt_count     INT NOT NULL DEFAULT 1,

    first_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One row per case+source. Updates increment attempt_count and refresh
    -- last_attempt_at; first_attempt_at is preserved.
    UNIQUE(case_number, source_type)
);

-- Index for the common eligibility query: "find cases with status X where
-- last_attempt_at < some_threshold"
CREATE INDEX IF NOT EXISTS idx_scrape_attempts_status_time
    ON case_party_scrape_attempts (status, last_attempt_at);

-- Index for case_number lookups (selection-pipeline join)
CREATE INDEX IF NOT EXISTS idx_scrape_attempts_case_number
    ON case_party_scrape_attempts (case_number, source_type);

COMMENT ON TABLE case_party_scrape_attempts IS
    'Attempt history and retry state for the Participants-tab scraper. '
    'Separates "tried and failed" from "no data exists" so transient '
    'portal failures do not become permanent suppressions of leads.';
