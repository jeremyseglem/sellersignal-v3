-- ============================================================================
-- 018_zip_release_notifications.sql — wait-list for claimed territories
--
-- When an agent visits the territories map and clicks a ZIP that's already
-- claimed by another agent, they can leave their email to be notified
-- when that territory becomes available again. This table is the wait
-- list. The territory release trigger (when an agent unclaims or has
-- their subscription lapse) emails everyone in the queue for that ZIP.
--
-- Design notes:
--   - Dedup is on (zip_code, email_lower) — same email + ZIP combo can't
--     stack up multiple subscriptions. Re-subscribing after notification
--     is fine because we mark notified rows and create a new row.
--   - email_lower stores the lowercased version for case-insensitive
--     dedup; original email is preserved in `email` for display.
--   - unsubscribe_token is a UUID generated server-side, used in the
--     unsubscribe link. Random per-row so leaking one doesn't expose
--     others.
--   - source column tracks where the subscription came from so we can
--     understand conversion ("territories_map" vs future "email_link"
--     vs "agent_referral").
--   - notified_at NULL means "still active in queue". Once notified, set
--     to now() — we keep the row for audit / re-engagement but exclude
--     from the queue lookup.
-- ============================================================================

CREATE TABLE IF NOT EXISTS zip_release_notifications (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    zip_code            text NOT NULL,
    email               text NOT NULL,
    email_lower         text NOT NULL GENERATED ALWAYS AS (lower(email)) STORED,
    created_at          timestamptz NOT NULL DEFAULT now(),
    notified_at         timestamptz,
    unsubscribe_token   uuid NOT NULL DEFAULT gen_random_uuid(),
    source              text NOT NULL DEFAULT 'territories_map',
    -- Referer / IP captured optionally for fraud / abuse review later.
    -- Not used by application logic right now.
    user_agent          text,
    ip_address          inet
);

-- Dedup: one active subscription per (ZIP, email). The partial index
-- on notified_at IS NULL means a user can re-subscribe AFTER being
-- notified (notified rows don't block new subs).
CREATE UNIQUE INDEX IF NOT EXISTS zip_release_notifications_active_unique
  ON zip_release_notifications (zip_code, email_lower)
  WHERE notified_at IS NULL;

-- Trigger lookup: when a ZIP releases, find everyone waiting for it.
CREATE INDEX IF NOT EXISTS zip_release_notifications_pending_idx
  ON zip_release_notifications (zip_code)
  WHERE notified_at IS NULL;

-- Unsubscribe link lookup.
CREATE INDEX IF NOT EXISTS zip_release_notifications_unsub_idx
  ON zip_release_notifications (unsubscribe_token);

COMMENT ON TABLE  zip_release_notifications IS
  'Wait list for territories the agent wants but are currently claimed. '
  'When a territory releases, all rows with matching zip_code and '
  'notified_at IS NULL get an email and are marked notified.';
COMMENT ON COLUMN zip_release_notifications.notified_at IS
  'Set when the release email was sent. NULL = still active in queue.';
COMMENT ON COLUMN zip_release_notifications.unsubscribe_token IS
  'Random UUID embedded in unsubscribe links. Hitting that endpoint '
  'with the matching token sets notified_at to now() (effectively '
  'removing the row from the queue without deleting audit history).';

-- RLS: this table is written by the public POST /api/zip-release-notifications
-- endpoint and read only by the server-side trigger. No agent-direct reads.
-- Block anon access entirely.
ALTER TABLE zip_release_notifications ENABLE ROW LEVEL SECURITY;
-- (No policies = no access for anon/authenticated roles. Server uses
-- service_role which bypasses RLS, which is what we want.)
