-- ============================================================================
-- 028_letter_scheduled_status.sql — letter scheduling state for Stannp
--
-- Stannp doesn't accept a send_date parameter the way Lob does. To preserve
-- the existing product behavior (sequence schedules letters at offsets of
-- 0/30/60/90/135/180 days), we hold scheduled letters in our own database
-- and a background task (backend/tasks/letter_scheduler.py) ticks daily,
-- finds rows past their stannp_send_date, and calls Stannp's create_letter
-- on each.
--
-- Two changes:
--   1. Add 'scheduled' to the letters_sent_v3 status enum
--   2. Add rendered_html — at sequence creation we render and snapshot the
--      HTML for all 6 letters. The scheduler reads the snapshot at send
--      time and converts to PDF. Locks the letter content at the moment
--      the agent paid, even if the underlying parcel/probate data changes
--      over the 6-month sequence window.
-- ============================================================================

-- Add 'scheduled' to the status enum.
ALTER TABLE letters_sent_v3
    DROP CONSTRAINT IF EXISTS letters_sent_v3_status_check;

ALTER TABLE letters_sent_v3
    ADD CONSTRAINT letters_sent_v3_status_check
    CHECK (status IN (
        'scheduled',                -- new: waiting for stannp_send_date
        'created',                  -- provider accepted the request
        'processed_for_delivery',
        'mailed',
        'in_transit',
        'in_local_area',
        'delivered',
        're-routed',
        'returned_to_sender',
        'cancelled',
        'failed',
        'pdf_rendered'
    ));

-- Snapshot column. NULL for PDF-download letters and legacy rows.
ALTER TABLE letters_sent_v3
    ADD COLUMN IF NOT EXISTS rendered_html TEXT;

-- Retry tracking for the scheduler. Each failed send_one() attempt bumps
-- fail_count. When fail_count reaches LETTER_SCHEDULER_MAX_RETRIES the
-- scheduler marks status='failed' and stops retrying. last_failed_at is
-- updated on every failed attempt for observability.
ALTER TABLE letters_sent_v3
    ADD COLUMN IF NOT EXISTS fail_count     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ;

-- Partial index for the scheduler's tick query — only the rows it cares
-- about. WHERE clause matches scheduler's SELECT criteria exactly.
CREATE INDEX IF NOT EXISTS idx_letters_sent_v3_scheduled_due
    ON letters_sent_v3(stannp_send_date)
    WHERE status = 'scheduled'
      AND stannp_letter_id IS NULL;
