-- 033_parent_pin.sql  (2026-07-26)
--
-- Condo-unit → complex linkage for the building-pin map UX.
--
-- KC condo units exist only in the bulk assessor extract
-- (EXTR_CondoUnit2.csv), not in the county ArcGIS parcel layer. The
-- complex ("common area") parcel DOES exist in ArcGIS as PIN =
-- Major + '0000' with the full building footprint. parent_pin stores
-- that complex PIN on each unit row so:
--   * the map can render one pin per building with a unit count
--   * a tap can list all sibling units (WHERE parent_pin = X)
--   * the dossier/map can serve the complex's lot polygon as the
--     unit's property lines
--
-- Applied via Supabase dashboard SQL editor. Backfill code
-- (admin backfill-condos endpoint) is defensive: it works without
-- this column (skips parent_pin writes with a warning).

ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS parent_pin TEXT;

-- Sibling-unit lookups and building-pin aggregation.
CREATE INDEX IF NOT EXISTS idx_parcels_v3_parent_pin
    ON parcels_v3 (parent_pin)
    WHERE parent_pin IS NOT NULL;
