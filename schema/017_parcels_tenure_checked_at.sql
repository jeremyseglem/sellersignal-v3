-- ============================================================================
-- 017_parcels_tenure_checked_at.sql — track when SCOPI tenure scrape ran
--
-- Powers the Snohomish SCOPI tenure autofill. The bulk Snohomish Sales
-- Excel only goes back 5 years; ~74% of 98290 parcels have no sale in
-- that window. The SCOPI per-parcel detail page exposes full sales
-- history (back decades) — so we scrape it for parcels missing tenure.
--
-- The autofill needs a way to skip parcels it has already inspected,
-- regardless of whether the scrape returned sales (write last_transfer_
-- date) or returned no sales (no transfer date to write). Without this
-- column, the autofill would re-scrape no-sale parcels forever.
--
-- This is a "checked-at" timestamp, not a sentinel value. It lets the
-- query be:
--   WHERE market_key = 'WA_SNOHOMISH'
--     AND last_transfer_date IS NULL
--     AND tenure_checked_at IS NULL
--
-- After a successful scrape (with or without sales found), the autofill
-- stamps tenure_checked_at = now(). To force a re-scrape of all
-- parcels in a market (e.g. after a meaningful SCOPI schema change),
-- run: UPDATE parcels_v3 SET tenure_checked_at = NULL WHERE market_key
-- = 'WA_SNOHOMISH';
-- ============================================================================

ALTER TABLE parcels_v3
  ADD COLUMN IF NOT EXISTS tenure_checked_at timestamptz;

COMMENT ON COLUMN parcels_v3.tenure_checked_at IS
  'When this parcel was last inspected by an external tenure source '
  '(currently SCOPI for WA_SNOHOMISH). NULL = never inspected. '
  'Set to now() after a successful scrape regardless of whether sales '
  'were found. Used by snohomish_tenure_autofill to avoid re-scraping.';

-- Partial index for the autofill query path — tiny, only indexes
-- the parcels actually awaiting inspection.
CREATE INDEX IF NOT EXISTS parcels_v3_tenure_pending_idx
  ON parcels_v3 (market_key, zip_code)
  WHERE tenure_checked_at IS NULL AND last_transfer_date IS NULL;
