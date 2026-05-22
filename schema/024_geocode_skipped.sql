-- Migration 024 — geocode_skipped flag on parcels_v3
--
-- Problem: the geometry backfill module re-fetches the same "stuck"
-- PINs every call. _fetch_pins_missing_geometry pulls parcels where
-- lat IS NULL or lng IS NULL, sorted by PIN ascending. If KC ArcGIS
-- has no record for a PIN (retired parcel, condo unit, recently
-- subdivided), the fetch returns nothing for it and its lat/lng stay
-- NULL — so it appears at the top of the missing list AGAIN on the
-- next call, gets re-tried, fails again. This made the 98053 backfill
-- converge to ~8 new geocodes per call after the first few batches,
-- because ~492 stuck PINs sat at the top of the queue blocking
-- progress.
--
-- Lesson learned previously (case_parties_v3 poisoned-retry, April):
-- DO NOT co-locate failure state with truth data. Don't write a
-- sentinel into lat/lng to mark "we tried and failed" — keep failure
-- state in a separate column (or table) so the truth column means
-- exactly one thing.
--
-- Fix: a small boolean column on parcels_v3. Default FALSE. The
-- geometry backfill sets it to TRUE for PINs ArcGIS returned no
-- record for, and skips TRUE rows on subsequent runs. Reversible
-- (set back to FALSE if the source data updates).
--
-- This is additive — no existing column is modified. Existing rows
-- get FALSE on backfill. Safe to apply at any time without
-- coordinating code deployment, though the geometry_backfill code
-- change that reads/writes this column ships in the same release.

ALTER TABLE parcels_v3
  ADD COLUMN IF NOT EXISTS geocode_skipped BOOLEAN NOT NULL DEFAULT FALSE;

-- Index for the backfill query path. The backfill filter is
-- `WHERE zip_code = $1 AND (lat IS NULL OR lng IS NULL) AND
--        geocode_skipped = FALSE`. A partial index on the FALSE
-- rows keeps the index small (most rows over time will end up
-- either geocoded successfully — covered by a different access
-- pattern — or skipped, both of which won't match the predicate).
CREATE INDEX IF NOT EXISTS parcels_v3_geocode_pending_idx
  ON parcels_v3 (zip_code)
  WHERE geocode_skipped = FALSE AND (lat IS NULL OR lng IS NULL);

COMMENT ON COLUMN parcels_v3.geocode_skipped IS
  'TRUE if a geometry backfill attempt could not find this PIN in the '
  'source ArcGIS. Skipped on subsequent backfill runs to avoid the '
  'poisoned-queue pattern. Reset to FALSE manually if the PIN reappears '
  'in the source (rare).';
