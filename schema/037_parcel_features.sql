-- 037: Open-vocabulary parcel features + need feature filters.
--
-- One JSONB column instead of a migration per attribute. Vocabulary v1
-- (KC amenity sweep + style): golf_adjacent, greenbelt_adjacent,
-- traffic_noise (1-3), power_lines, historic_site, sewer
-- ('public'|'septic'), water ('public'|'well'), flood_plain, wfnt_bank
-- (1-4), wfnt_access_rights, views ({lake_wa:1-4, lake_samm, rainier,
-- olympics, cascades, skyline, sound, territorial, lake_river_creek,
-- other}), garage_sqft, deck_sqft, fireplaces, brick_stone,
-- daylight_basement, bldg_grade (KC 1-13), condition, top_floor,
-- end_unit, floor, parking_garage, style (string).
-- Absent key = unknown; the engine rank-doesn't-reject on unknown,
-- except negative filters (e.g. power_lines=false) where absent = pass
-- because counties flag these affirmatively.

ALTER TABLE parcels_v3     ADD COLUMN IF NOT EXISTS features        JSONB;
ALTER TABLE buyer_needs_v3 ADD COLUMN IF NOT EXISTS feature_filters JSONB;

CREATE INDEX IF NOT EXISTS idx_parcels_v3_features
    ON parcels_v3 USING GIN (features) WHERE features IS NOT NULL;
