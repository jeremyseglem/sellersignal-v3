-- ============================================================================
-- 027_letters_provider.sql — provider-agnostic letter tracking
--
-- Adds a 'provider' column to letters_sent_v3 plus Stannp-specific tracking
-- columns. Keeps the existing lob_* columns intact for two reasons:
--   1. Legacy rows from Lob test sends keep their reference data
--   2. Rollback: if Stannp doesn't work out, code can revert to Lob without
--      a schema change
--
-- The MAIL_PROVIDER env var on the backend controls which provider new sends
-- use. Reading code prefers stannp_letter_id when provider='stannp', falls
-- back to lob_letter_id otherwise. Code is dual-pathed during the migration
-- window; after we've fully cut over and Lob is decommissioned, the lob_*
-- columns can be dropped in a future migration.
-- ============================================================================

ALTER TABLE letters_sent_v3
    ADD COLUMN IF NOT EXISTS provider           TEXT,
    ADD COLUMN IF NOT EXISTS stannp_letter_id   TEXT,
    ADD COLUMN IF NOT EXISTS stannp_mode        TEXT,
    ADD COLUMN IF NOT EXISTS stannp_send_date          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stannp_expected_delivery  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stannp_tracking_url       TEXT;

-- Backfill: rows that have a lob_letter_id were sent via Lob.
UPDATE letters_sent_v3
   SET provider = 'lob'
 WHERE provider IS NULL
   AND lob_letter_id IS NOT NULL;

-- Anything left with NULL provider is a PDF-download row (no provider).
-- Leave those as NULL rather than guessing.

-- Partial index for Stannp webhook lookups — only the rows we'll actually
-- look up by stannp_letter_id (live Stannp sends).
CREATE INDEX IF NOT EXISTS idx_letters_sent_v3_stannp_letter_id
    ON letters_sent_v3(stannp_letter_id)
    WHERE stannp_letter_id IS NOT NULL;
