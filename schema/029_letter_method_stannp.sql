-- ============================================================================
-- 029_letter_method_stannp.sql — allow 'stannp_mail' as a method value
--
-- The letters_sent_v3.method CHECK constraint from migration 023 only allowed
-- ('lob_mail', 'pdf_download'). The Stannp migration writes method='stannp_mail'
-- which trips the constraint. Discovered during the first sequence-start
-- end-to-end test on 2026-06-01.
--
-- Keeps lob_mail in the allowed set for legacy rows.
-- ============================================================================

ALTER TABLE letters_sent_v3
    DROP CONSTRAINT IF EXISTS letters_sent_v3_method_check;

ALTER TABLE letters_sent_v3
    ADD CONSTRAINT letters_sent_v3_method_check
    CHECK (method IN ('lob_mail', 'stannp_mail', 'pdf_download'));
