-- ============================================================================
-- 009_last_arms_length.sql
-- ============================================================================
-- Derives each parcel's most recent arms-length transaction from
-- sales_history_v3. "Arms-length" is defined at ingest time by the
-- eReal Property parser's classifier (see
-- backend/harvesters/ereal_property_parser._classify_arms_length):
--   - Quit Claim deeds             -> False
--   - Trustee deeds                -> False
--   - Reason Gift/Estate/Divorce/Trust -> False
--   - Statutory Warranty + reason None -> True
--
-- Problem this solves:
--
--   parcels_v3.last_transfer_price = 0 on many parcels whose last
--   recorded transfer was a $0 trust move or quit-claim. The Tina Han
--   parcel (3394100120) is the canonical example: last transfer is a
--   2015 trust quit-claim at $0, but the actual last arms-length sale
--   was $810K in 2013. HIGH EQUITY calculations on parcels_v3.last_
--   transfer_price alone miss these — the view fixes that.
--
-- Callers should prefer last_arms_length_price over last_transfer_price
-- when both are available, and fall back to last_transfer_price
-- (from parcels_v3) when no arms-length row exists in sales_history_v3.
-- ============================================================================

CREATE OR REPLACE VIEW parcel_last_arms_length_v3 AS
SELECT DISTINCT ON (pin)
    pin,
    sale_date      AS last_arms_length_date,
    sale_price     AS last_arms_length_price,
    buyer_name     AS last_arms_length_buyer,
    seller_name    AS last_arms_length_seller,
    recording_number
FROM sales_history_v3
WHERE is_arms_length = TRUE
  AND sale_price IS NOT NULL
  AND sale_price > 0
ORDER BY pin, sale_date DESC;

-- Note: views don't need indexes — the underlying table has
-- idx_sales_arms_length and idx_sales_date that cover the filter+sort.
