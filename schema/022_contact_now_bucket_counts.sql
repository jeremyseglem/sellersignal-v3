-- ════════════════════════════════════════════════════════════════════
-- 022 — Per-bucket Contact Now counts on zip_coverage_v3
-- ════════════════════════════════════════════════════════════════════
--
-- Adds six per-bucket count columns to zip_coverage_v3 so the
-- Territories page can show the breakdown:
--   "98004 — 355 contact now · Probate 28 · Trust 43 · LLC 67 …"
--
-- These mirror the six buckets defined in weekly_selector
-- .count_contact_now_eligible_per_bucket. Counts are PRE-CAP — i.e.
-- the total eligible pool per bucket, not just the top 100 we render
-- in the briefing.
--
-- Populated by two paths (both already update current_call_now_count):
--   1. Drive-by writeback in backend/api/briefings.py — every fresh
--      briefing build writes these alongside current_call_now_count.
--   2. Manual refresh in backend/api/coverage.py refresh-counts
--      endpoint — force-refresh for ZIPs nobody has opened recently.
--
-- current_call_now_count is preserved during transition. It maps to
-- contact_now_probate (legacy "call now" was probate-only via Rule 6).
-- Code that reads current_call_now_count keeps working unchanged.
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE zip_coverage_v3
    ADD COLUMN IF NOT EXISTS contact_now_probate   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contact_now_divorce   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contact_now_trust     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contact_now_llc       INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contact_now_absentee  INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contact_now_tenure    INTEGER NOT NULL DEFAULT 0;

-- Seed: current_call_now_count is probate-only today, so initialize
-- contact_now_probate from it. The other five buckets start at 0
-- and get their first real value the next time any briefing builds.
UPDATE zip_coverage_v3
   SET contact_now_probate = COALESCE(current_call_now_count, 0)
 WHERE contact_now_probate = 0
   AND COALESCE(current_call_now_count, 0) > 0;

COMMENT ON COLUMN zip_coverage_v3.contact_now_probate
    IS 'Eligible probate leads (Rule 6: family PR identified). Pre-cap.';
COMMENT ON COLUMN zip_coverage_v3.contact_now_divorce
    IS 'Eligible divorce-signal leads. Pre-cap.';
COMMENT ON COLUMN zip_coverage_v3.contact_now_trust
    IS 'Trust-owned parcels, tenure >= 10 years. Pre-cap.';
COMMENT ON COLUMN zip_coverage_v3.contact_now_llc
    IS 'LLC-owned parcels, tenure >= 7 years. Pre-cap.';
COMMENT ON COLUMN zip_coverage_v3.contact_now_absentee
    IS 'Out-of-state owners (owner_state != WA). Pre-cap.';
COMMENT ON COLUMN zip_coverage_v3.contact_now_tenure
    IS 'Individual-owned parcels, tenure >= 15 years. Pre-cap.';
