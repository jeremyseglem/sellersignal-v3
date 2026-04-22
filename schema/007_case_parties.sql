-- ═══════════════════════════════════════════════════════════════════════
-- case_parties_v3
-- ═══════════════════════════════════════════════════════════════════════
-- Enrichment layer for court-case signals: the Participants tab of each
-- KC Superior Court case lists every human/entity involved and their
-- role (Petitioner, Personal Representative, Deceased, Attorney, Guardian,
-- etc.). That data isn't in the search-results row — you have to drill
-- into the detail page's Participants tab to get it.
--
-- We harvest it separately (one extra GET per case) and store here so:
--   1. The matcher can surface the ACTUAL decision-maker in the briefing
--      (Personal Representative, not the deceased)
--   2. Agents can classify leads at a glance:
--        - "family_pr"     → workable, route contact to named family member
--        - "corporate_pr"  → unworkable, corporate trustee handles sale
--        - "attorney_pr"   → unworkable, attorney gates the process
--        - "none"          → petitioner not yet named
--   3. Out-of-ZIP heir analysis becomes possible (compare PR mailing
--      address to property ZIP)
--
-- One row per (case_number, party). A case typically has 2-5 parties.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS case_parties_v3 (
    id                 BIGSERIAL PRIMARY KEY,

    -- Case identity
    case_number        TEXT NOT NULL,
    -- e.g. "25-4-07651-0" — matches raw_signals_v3.document_ref for probate/divorce

    source_type        TEXT NOT NULL DEFAULT 'kc_superior_court',
    -- Matches raw_signals_v3.source_type — scoped so case_number collisions
    -- across jurisdictions don't conflict

    -- Role and name
    role               TEXT NOT NULL,
    -- Normalized role values:
    --   'personal_representative'  (includes "Petitioner / Personal Representative")
    --   'petitioner'               (distinct petitioner, not yet PR)
    --   'respondent'               (divorce cases)
    --   'deceased'                 (decedent in probate)
    --   'guardian'                 (guardianship cases)
    --   'ward'                     (guardianship subject)
    --   'attorney'                 (represented-by, captured for audit, not surfaced)
    --   'other'                    (catch-all — GAL, trustee, etc.)

    raw_role           TEXT,
    -- Original role string as scraped (e.g. "Petitioner / Personal Representative")

    name_raw           TEXT NOT NULL,
    -- "LEITHE, JUDITH P" — exactly as displayed

    name_last          TEXT,
    name_first         TEXT,
    name_middle        TEXT,
    -- Parsed components. Null if name didn't parse cleanly.

    represented_by     TEXT,
    -- The attorney name from the "Represented By" column, if any.
    -- Stored for audit/provenance but NEVER surfaced as a contact target.

    -- PR classification (computed at insert time, re-runnable)
    pr_classification  TEXT,
    -- Only populated when role = 'personal_representative':
    --   'family'     — individual human name, surname likely matches decedent
    --   'corporate'  — matches /TRUST|BANK|FIDUCIARY|TRUSTEE|SERVICES/ patterns
    --   'attorney'   — matches /LAW|LLC|PLLC|ESQ|ATTORNEY/ patterns
    --   'unknown'    — doesn't fit family/corporate/attorney classifier
    -- For non-PR roles, this is NULL.

    -- Provenance
    scraped_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_html_hash      TEXT,
    -- Hash of the participants-tab HTML for dedup/change-detection

    -- Unique constraint: one row per (case, role, name) combination.
    -- If a case has two Petitioners (unusual but possible), each gets its own row.
    UNIQUE(case_number, source_type, role, name_raw)
);

-- Index for fast lookup when enriching matches
CREATE INDEX IF NOT EXISTS idx_case_parties_case_number
    ON case_parties_v3 (case_number, source_type);

-- Index for finding all PRs (for analysis / pitch-metric queries)
CREATE INDEX IF NOT EXISTS idx_case_parties_pr
    ON case_parties_v3 (role, pr_classification)
    WHERE role = 'personal_representative';

COMMENT ON TABLE case_parties_v3 IS
    'Participants of each court case, extracted from the KC Superior '
    'Court Participants tab. Populated by a separate enrichment harvester '
    'run after the primary search-results harvester stores the case in '
    'raw_signals_v3. Attorneys are captured but never routed to; family '
    'Personal Representatives are the primary contact target.';
