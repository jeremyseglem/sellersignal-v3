-- ============================================================================
-- 026_renewal_notifications.sql — track which renewal reminders have been sent
--
-- The renewal notifier background task ticks daily and emails agents whose
-- subscription cancel_at is approaching at T-30, T-7, T-1 days. To avoid
-- duplicate sends we record the send time per window on the territory row.
--
-- Three nullable timestamp columns (one per window) keeps the schema cheap
-- and the query trivial:
--   SELECT … FROM agent_territories_v3
--   WHERE status = 'active'
--     AND renewal_notified_30d_at IS NULL
--     AND days_until_cancel BETWEEN 28 AND 31;  -- (computed in app)
--
-- Tightening intervals (28-31 instead of exactly 30) gives the task a
-- forgiveness window in case it skips a day for any reason. Each window
-- is fired exactly once per territory — once renewal_notified_*_at is
-- set, no more sends for that window. If the agent renews and the
-- subscription's cancel_at moves out by another 90 days, the columns
-- get reset to NULL so the next cycle's reminders can fire.
--
-- Rationale for storing on agent_territories_v3 (not a separate
-- notifications_v3 table): one row per active subscription period, with
-- the relevant subscription_id already attached. Fewer joins, simpler
-- task code.
-- ============================================================================

ALTER TABLE agent_territories_v3
    ADD COLUMN IF NOT EXISTS renewal_notified_30d_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS renewal_notified_7d_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS renewal_notified_1d_at  TIMESTAMPTZ;

-- Index for the task's per-tick query: find active territories that
-- haven't been notified for at least one window. Partial index keeps
-- the index size small (only active rows).
CREATE INDEX IF NOT EXISTS idx_territories_v3_renewal_lookup
    ON agent_territories_v3(stripe_subscription_id)
    WHERE status = 'active' AND stripe_subscription_id IS NOT NULL;
