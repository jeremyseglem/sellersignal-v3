-- ============================================================================
-- 011_lead_interactions.sql — per-agent event log for lead memory.
--
-- Powers the "Mark as working / Not relevant / Sent to CRM" buttons on
-- each parcel dossier, plus the outcome dropdown that appears after a
-- lead has been marked working. The product needs continuity per lead
-- across weekly briefings without becoming a CRM. This table tracks
-- agent interactions at the event level, scoped per (agent, parcel).
--
-- Design: event log, not state row. Each click writes a new row;
-- "current state" is computed by reading the most recent event of
-- each kind. This:
--   - matches the spec's "events array" model
--   - preserves history naturally (no destructive updates)
--   - avoids race conditions from concurrent edits
--   - lets future analytics aggregate over event streams
--
-- "Undo" works by writing a superseding event, never by deleting.
-- RLS enforces no DELETE — once you mark something, it's history.
--
-- This is V1 of Lead Memory. Future versions may add:
--   - lead_notes (text input — explicitly out of scope for V1; the
--     spec's "do NOT add notes" rule prevents CRM creep)
--   - cross-agent visibility for shared territories (currently each
--     agent sees only their own events)
-- ============================================================================

CREATE TABLE IF NOT EXISTS lead_interactions_v3 (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The agent who performed the action. FK to Supabase auth.
    -- ON DELETE CASCADE: if the agent's account is deleted, their
    -- entire interaction history goes with it.
    agent_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- The parcel this event is about. PIN is a string identifier
    -- (KC: '471720-0260', Maricopa: APN format, etc.). NOT a FK to
    -- parcels_v3 — parcels can be reseeded/recanonicalized and we
    -- don't want CASCADE to delete agent history. PIN+ZIP is enough
    -- to look up the current parcel state at read time.
    pin          TEXT NOT NULL,
    zip_code     TEXT NOT NULL,

    -- The event type. Constrained set; see CHECK below.
    event_type   TEXT NOT NULL,

    -- Optional structured metadata for the event. Keeps the table
    -- forward-compatible without future migrations:
    --   - working:           {} (no extra metadata)
    --   - not_relevant:      {reason?: string}
    --   - sent_to_crm:       {crm?: 'follow_up_boss' | 'kvcore' | ...}
    --   - got_response:      {channel?: 'phone' | 'email' | 'letter'}
    --   - listing_discussion:{notes?: string} -- intentionally limited
    event_data   JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constrain event_type to the canonical set. Adding new event
    -- types requires a migration; this prevents typos from creating
    -- ghost states.
    CONSTRAINT lead_interactions_v3_event_type_check
        CHECK (event_type IN (
            'working',
            'not_relevant',
            'sent_to_crm',
            'got_response',
            'no_response',
            'listing_discussion',
            'closed',
            'reactivated'
        ))
);

-- ── Indexes for the two query patterns ──────────────────────────
-- Pattern 1: "what events exist for this parcel from this agent?"
-- Used by the dossier load to compute current status + history.
CREATE INDEX IF NOT EXISTS idx_lead_interactions_v3_agent_pin
    ON lead_interactions_v3(agent_id, pin, created_at DESC);

-- Pattern 2: "all events for this agent in this ZIP, newest first"
-- Used by the briefing load to overlay status on the action list
-- and pipeline, plus by the future Outcome Receipts feature.
CREATE INDEX IF NOT EXISTS idx_lead_interactions_v3_agent_zip
    ON lead_interactions_v3(agent_id, zip_code, created_at DESC);

-- ── Row Level Security ──────────────────────────────────────────
-- Each agent can read and insert their own events, nothing else.
-- No UPDATE or DELETE policies: events are immutable. To "undo,"
-- the client writes a superseding event (e.g., a 'working' event
-- after a 'not_relevant' event reactivates the lead).
-- The backend service-key bypasses RLS for any future admin work.
ALTER TABLE lead_interactions_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own interactions" ON lead_interactions_v3;
CREATE POLICY "agent reads own interactions" ON lead_interactions_v3
    FOR SELECT
    USING (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent inserts own interactions" ON lead_interactions_v3;
CREATE POLICY "agent inserts own interactions" ON lead_interactions_v3
    FOR INSERT
    WITH CHECK (auth.uid() = agent_id);

-- Explicitly NO UPDATE or DELETE policies — events are immutable.
-- RLS denies by default, so absence of these policies is the
-- enforcement.

-- ── Convenience view: current status per (agent, pin) ───────────
-- Computes the most recent event per parcel for fast status lookup.
-- Used by the BriefingPage when overlaying status on the lists, and
-- the future "show dismissed" toggle in exploration mode.
--
-- Why a view rather than a stored function: views can be queried with
-- the same RLS-aware client, no additional grant management needed.
CREATE OR REPLACE VIEW lead_status_v3 AS
SELECT DISTINCT ON (agent_id, pin)
    agent_id,
    pin,
    zip_code,
    event_type AS status,
    event_data,
    created_at AS status_at
FROM lead_interactions_v3
WHERE event_type IN ('working', 'not_relevant', 'sent_to_crm')
ORDER BY agent_id, pin, created_at DESC;
