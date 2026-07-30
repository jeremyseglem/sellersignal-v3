-- 035: Structure + amenity enrichment columns on parcels_v3.
--
-- Feeds the marketplace demand engine's Tier-2 criteria (beds, baths,
-- year built, stories, renovation, waterfront, views). Columns are
-- market-agnostic; the KC bulk-extract enricher populates them first,
-- other markets follow with their own adapters. NULL = unknown (the
-- engine rank-doesn't-reject on NULL), so no defaults.

ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS bedrooms          INT;
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS bathrooms         NUMERIC(4,2);
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS stories           NUMERIC(4,1);
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS year_renovated    INT;
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS waterfront        BOOLEAN;
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS waterfront_footage INT;
ALTER TABLE parcels_v3 ADD COLUMN IF NOT EXISTS view_rating       SMALLINT;
