-- 031_letter_digest_timezone.sql
--
-- Per-agent timezone preference for the daily letter digest task.
-- Resolves active issue #14 from MANIFESTO — v1 hardcoded the send
-- hour to America/Denver for every agent regardless of where they
-- live, which means WA-based agents receive their digest at 5-6am
-- Pacific (depending on DST alignment). Adding this column lets each
-- agent's profile carry its own timezone string; the digest task
-- reads it per-tick and decides per-agent whether the current hour
-- matches 7am in THAT agent's timezone.
--
-- The default 'America/Denver' preserves v1 behavior for any existing
-- agent rows that haven't been updated — no behavior change until an
-- operator (or future profile-page UI) sets it.
--
-- The column also handles other potential timezone-sensitive features
-- as they ship (e.g. weekly summary emails, in-app "scheduled today"
-- horizons). Named `digest_timezone` rather than plain `timezone` to
-- be unambiguous about its scope; if we later want a separate display
-- timezone for the briefing UI, that's a different column.

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS digest_timezone TEXT NOT NULL DEFAULT 'America/Denver';

-- No index — column is read once per tick per agent in the digest
-- task; the agent set is small.
