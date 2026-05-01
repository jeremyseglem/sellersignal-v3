-- ═══════════════════════════════════════════════════════════════════════
-- match_review columns on raw_signal_matches_v3
-- ═══════════════════════════════════════════════════════════════════════
-- Shadow-mode calibration layer for the matcher.
--
-- The live name_match() gate (in backend/ingest/legal_filings.py) is
-- intentionally soft — it accepts any 2-token overlap so that valid
-- matches with different formatting (e.g. trust-titled owners, hyphenated
-- middle names) still survive. That softness leaves some questionable
-- matches in the wild — cases where token-overlap fires but identity
-- can't actually be confirmed (different middle names, single-token
-- overlap on common surnames, etc).
--
-- This migration adds three nullable columns that record what a STRICTER
-- gate would say about each match, without affecting which matches show
-- up in the UI. The audit endpoint (backend/api/admin.py:audit-match-review)
-- populates these columns; the briefings selector ignores them. Result:
-- we get a flagged-match dataset for human review WITHOUT removing any
-- leads from production overnight.
--
-- Future workflow: review the flagged matches via the read endpoint,
-- decide which patterns to promote to the live gate, repeat.
--
-- Columns:
--   match_review_status   — one of:
--                             'likely_valid'           (passes shadow gate too)
--                             'needs_review'           (token-only overlap, ambiguous)
--                             'likely_false_positive'  (clear evidence of mismatch)
--                             NULL                     (not yet evaluated)
--
--   match_review_reason   — short tag explaining the verdict, e.g.:
--                             'particle_only'           — only THI/VAN-class shared
--                             'middle_initial_disagree' — Michael S vs Michael R
--                             'middle_full_disagree'    — Bradford vs Patrick
--                             'first_name_diff'         — different first names
--                             'cleared'                 — survived all checks
--                             NULL                      — not yet evaluated
--
--   match_confidence_score — 0.0 to 1.0:
--                             1.0 = exact full-name agreement
--                             0.7-0.9 = strong agreement with minor formatting differences
--                             0.4-0.6 = ambiguous (token-only, no middle to disambiguate)
--                             0.0-0.3 = explicit conflict (different middles, etc.)
--                             NULL = not yet evaluated
--
-- All three columns are NULLable. Existing rows remain NULL until the
-- audit endpoint runs against them. Briefings code does NOT read these
-- columns — they exist for the calibration / review workflow only.
-- ═══════════════════════════════════════════════════════════════════════

ALTER TABLE raw_signal_matches_v3
    ADD COLUMN IF NOT EXISTS match_review_status   TEXT,
    ADD COLUMN IF NOT EXISTS match_review_reason   TEXT,
    ADD COLUMN IF NOT EXISTS match_confidence_score REAL;

-- Index to support the read-side review queue endpoint, which sorts by
-- status (filter to non-NULL flagged rows) then by impact.
CREATE INDEX IF NOT EXISTS idx_raw_signal_matches_v3_review_status
    ON raw_signal_matches_v3 (match_review_status)
    WHERE match_review_status IS NOT NULL;
