-- 040: composite index for per-ZIP, pin-ordered reads of parcels_v3.
--
-- Why (2026-10-29): `WHERE zip_code = X ORDER BY pin LIMIT n` times out
-- (Postgres 57014, statement timeout) on some ZIPs — e.g. 27613 Raleigh,
-- 15,043 parcels — even at LIMIT 100, because the planner walks the pin
-- primary key across the whole table instead of using idx_parcels_v3_zip.
-- Hit by the monthly fabric snapshot (GH runs 40863194589, 40864094717)
-- and by GET /api/admin/export-fabric/27613?table=parcels (HTTP 500 at
-- limit 1000 and 300), which the analyst and engine architect depend on.
--
-- Run in the Supabase SQL editor. CONCURRENTLY avoids locking writes; it
-- must run on its own (not inside a transaction). If the editor refuses
-- CONCURRENTLY, drop that word — the plain build takes a short write lock.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_parcels_v3_zip_pin
    ON parcels_v3 (zip_code, pin);
