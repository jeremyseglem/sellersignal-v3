-- 032_lot_polygons.sql  (2026-07-22)
--
-- Persist parcel lot-polygon geometry.
--
-- WHY: /api/map/{zip}/lot-polygons fetched lot geometry LIVE from county
-- ArcGIS on every cache miss — 150 pins per request, paging the whole ZIP.
-- Measured: 06883 21s / 3.0MB, 98004 21s / 5.4MB, 85255 55s / 13.1MB (one
-- run timed out at 60s). The only cache was in-process, so it evaporated on
-- every Railway redeploy and the next visitor paid the full crawl again.
-- That is the dominant cost in "Google Earth takes a ton of time to load",
-- because the V4 Earth layer waits on this fabric.
--
-- AFTER: geometry is fetched from the county once, stored here, and served
-- from Postgres on every subsequent request.
--
-- The endpoint degrades gracefully if this migration hasn't been applied:
-- it falls back to the live ArcGIS path (same behavior as before), logs
-- once, and simply doesn't persist. Same defensive pattern as
-- 024_geocode_skipped.

CREATE TABLE IF NOT EXISTS lot_polygons_v3 (
    zip_code    TEXT        NOT NULL,
    pin         TEXT        NOT NULL,
    geom        JSONB       NOT NULL,
    market_key  TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (zip_code, pin)
);

-- The only read pattern: every polygon for one ZIP.
CREATE INDEX IF NOT EXISTS idx_lot_polygons_v3_zip
    ON lot_polygons_v3 (zip_code);

COMMENT ON TABLE lot_polygons_v3 IS
    'Cached county ArcGIS lot geometry, keyed by (zip_code, pin). '
    'Written by /api/map/{zip}/lot-polygons on a miss and by '
    '/api/admin/lot-polygons-warm/{zip}. Safe to TRUNCATE — it '
    'rebuilds itself from the county sources on demand.';
