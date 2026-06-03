-- 030_letter_digest_timestamp.sql
--
-- Adds letter_digest_last_sent_at to agent_profiles_v3, used by the
-- daily letter-activity digest task (backend/tasks/letter_digest.py).
--
-- The digest task ticks hourly and fires at 7am America/Denver. For
-- each agent with letter activity in the prior 24h, it sends an email
-- summary and stamps this column. Idempotency: if the column's date
-- (interpreted in America/Denver) matches today's date in the same
-- timezone, the digest is skipped — prevents double-sending if the
-- task tick window overlaps the send time.
--
-- NULL means "never sent a digest" — first digest fires the first
-- time the agent has activity.

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS letter_digest_last_sent_at TIMESTAMPTZ;

-- No index needed — the column is read once per tick per agent and
-- the agent set is small (well under 1000 rows for the foreseeable
-- future). If the task ever scans by this column, add a partial
-- index on (letter_digest_last_sent_at) WHERE NOT NULL.
