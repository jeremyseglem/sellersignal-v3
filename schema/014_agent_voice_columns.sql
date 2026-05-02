-- ═══════════════════════════════════════════════════════════════════════
-- 014_agent_voice_columns.sql
-- ═══════════════════════════════════════════════════════════════════════
-- Extends the existing agent_profiles_v3 table (created in migration
-- 010) with the voice / stance / bio / generated_scripts columns that
-- power the agent-voice product (per docs/AGENT_VOICE_V1.md).
--
-- This is NOT a new table. The existing identity columns
-- (full_name, brokerage, license_number, headshot_url, etc.) stay
-- unchanged. We add four columns to the same row so each agent has
-- one profile across all use cases.
--
-- All new columns are nullable / default-empty. Existing rows are
-- unaffected. Existing RLS policies on the table cover the new
-- columns automatically.
--
-- Columns:
--   voice_sample                 — agent's own writing (free text).
--                                  May be a paragraph describing how
--                                  they communicate, or one pasted
--                                  real letter they've actually sent.
--                                  Used to teach the LLM their cadence
--                                  and word choice. Empty/NULL means
--                                  fall back to a system default voice.
--
--   stance                       — JSONB object holding ~10 forced-
--                                  choice behavioral dimensions. See
--                                  AGENT_VOICE_V1.md for the question
--                                  set. Default {} when agent skips
--                                  stance onboarding — the prompt
--                                  layer applies safe defaults
--                                  (indirect, relationship-first,
--                                  understated, etc.).
--
--   bio                          — JSONB object: { background,
--                                  geographic_anchors, affiliations }.
--                                  Used by the LLM as STANDBY context
--                                  the prompt draws on only when an
--                                  organic hook to the lead's parcel
--                                  exists. Default {}.
--
--   generated_scripts            — JSONB object: one entry per
--                                  archetype. Populated at onboarding
--                                  via 5-6 LLM calls. Lead-level
--                                  rendering injects parcel/lead
--                                  specifics via token substitution.
--                                  Default {}.
--
--   voice_onboarding_completed_at — timestamp when the agent first
--                                  completed voice onboarding (separate
--                                  from the existing onboarding_completed_at
--                                  which tracks identity-only setup).
--                                  NULL until voice onboarding is done.
-- ═══════════════════════════════════════════════════════════════════════

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS voice_sample TEXT,
    ADD COLUMN IF NOT EXISTS stance JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS bio JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS generated_scripts JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS voice_onboarding_completed_at TIMESTAMPTZ;

-- No new indexes needed — generated_scripts is read by primary-key
-- lookup (the user's own row), not searched. Same for stance/bio.
