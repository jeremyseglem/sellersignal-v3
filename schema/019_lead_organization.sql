-- ============================================================================
-- 019_lead_organization.sql — notes, tags, and action-tracking event types.
--
-- Extends Lead Memory (migration 011) for beta. Three concerns in one
-- migration because they ship together as one feature surface ("organize
-- and track my leads"):
--
--   1. Adds four action-event types to lead_interactions_v3:
--        - 'called'       — agent called the lead (event_data holds outcome
--                            + optional duration/number, agent records what
--                            happened on the call)
--        - 'mailed'       — agent sent a mailer (event_data holds template
--                            id + future Lob letter id once that ships)
--        - 'voicemail'    — agent left voicemail (event_data holds optional
--                            transcript or notes about what they said)
--        - 'skip_traced'  — agent ran skip-trace (event_data holds provider
--                            + hits + cost_cents for analytics)
--
--      These are ACTIONS performed on a lead, distinct from funnel STATUS
--      ('working', 'not_relevant', 'sent_to_crm') and from contact OUTCOMES
--      ('got_response', 'no_response', 'listing_discussion', 'closed').
--      They render in the dossier history line and feed analytics but do
--      NOT change funnel status — an agent calling a lead is still
--      'working' on it. The view lead_status_v3 is intentionally NOT
--      modified.
--
--      'dismissed' is intentionally NOT added: 'not_relevant' already
--      means "remove this lead from my list" and the UI just needs to
--      surface that more clearly. Adding parallel event types for the
--      same semantic creates ambiguity.
--
--   2. lead_notes_v3 — multiple notes per (agent, parcel), MUTABLE, with
--      created_at and updated_at. This is the deliberate reversal of
--      migration 011's "do NOT add notes" rule: beta agents need a place
--      to write down call/mail context per prospect. Capped at 4000 chars
--      per note to discourage CRM-style sprawl while leaving room for
--      genuine context. Multiple rows preserve note history naturally —
--      an agent can see what they thought two weeks ago alongside today.
--
--   3. lead_tags_v3 — flat (agent, pin, zip, tag). An agent's distinct set
--      of tag strings IS their taxonomy; no separate taxonomy table to
--      manage. Each tag assignment is one row; unique constraint on
--      (agent_id, pin, tag) prevents duplicate assignments. Tags are
--      free-form free-text per agent (not shared across agents) — each
--      agent organizes their own pipeline how they want.
--
-- Tags vs funnel status: tags are intentionally separate from funnel
-- status (the lead_status_v3 view) so we never lose the structured
-- "where is this lead" answer to free-text creep. A lead can be
-- {status: working, tags: ['estate sale next month', 'out of state']}.
-- ============================================================================


-- ── Part 1: Extend lead_interactions_v3 event_type vocabulary ──────────
-- Drop-and-recreate the CHECK constraint. Safe because existing rows
-- all use the original vocabulary; the new constraint is a superset.
ALTER TABLE lead_interactions_v3
    DROP CONSTRAINT IF EXISTS lead_interactions_v3_event_type_check;

ALTER TABLE lead_interactions_v3
    ADD CONSTRAINT lead_interactions_v3_event_type_check
    CHECK (event_type IN (
        -- Funnel status (from migration 011)
        'working',
        'not_relevant',
        'sent_to_crm',
        -- Contact outcomes (from migration 011)
        'got_response',
        'no_response',
        'listing_discussion',
        'closed',
        'reactivated',
        -- NEW: actions performed on a lead (migration 019)
        'called',
        'mailed',
        'voicemail',
        'skip_traced'
    ));


-- ── Part 2: lead_notes_v3 — mutable free-text notes per lead ──────────
CREATE TABLE IF NOT EXISTS lead_notes_v3 (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Owner of the note. ON DELETE CASCADE: agent account removal wipes
    -- their notes, same as lead_interactions_v3.
    agent_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- The parcel the note is about. Same PIN-not-FK pattern as 011 so
    -- parcel reseeds don't cascade. zip_code stored alongside for fast
    -- ZIP-scoped queries without joining parcels_v3.
    pin          TEXT NOT NULL,
    zip_code     TEXT NOT NULL,

    -- The note text itself. 1..4000 chars: empty notes are meaningless,
    -- the cap discourages CRM-style sprawl while leaving room for real
    -- per-prospect context. Frontend should enforce a similar limit
    -- with a character counter so agents don't lose work to a 4001-char
    -- server rejection.
    body         TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pattern: "all notes for this agent on this parcel, newest first."
-- Used by the dossier load to render the notes section.
CREATE INDEX IF NOT EXISTS idx_lead_notes_v3_agent_pin
    ON lead_notes_v3(agent_id, pin, created_at DESC);

-- Auto-bump updated_at on UPDATE. Keeps client-visible timestamps
-- accurate without trusting the API layer to set them.
CREATE OR REPLACE FUNCTION touch_lead_notes_v3_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lead_notes_v3_touch_updated_at ON lead_notes_v3;
CREATE TRIGGER lead_notes_v3_touch_updated_at
    BEFORE UPDATE ON lead_notes_v3
    FOR EACH ROW
    EXECUTE FUNCTION touch_lead_notes_v3_updated_at();

-- RLS: agents read/write their own notes. Unlike lead_interactions_v3,
-- notes ARE mutable — UPDATE and DELETE policies are present.
ALTER TABLE lead_notes_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own notes" ON lead_notes_v3;
CREATE POLICY "agent reads own notes" ON lead_notes_v3
    FOR SELECT
    USING (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent inserts own notes" ON lead_notes_v3;
CREATE POLICY "agent inserts own notes" ON lead_notes_v3
    FOR INSERT
    WITH CHECK (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent updates own notes" ON lead_notes_v3;
CREATE POLICY "agent updates own notes" ON lead_notes_v3
    FOR UPDATE
    USING (auth.uid() = agent_id)
    WITH CHECK (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent deletes own notes" ON lead_notes_v3;
CREATE POLICY "agent deletes own notes" ON lead_notes_v3
    FOR DELETE
    USING (auth.uid() = agent_id);


-- ── Part 3: lead_tags_v3 — flat tag assignments ────────────────────────
CREATE TABLE IF NOT EXISTS lead_tags_v3 (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    agent_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    pin          TEXT NOT NULL,
    zip_code     TEXT NOT NULL,

    -- The tag string itself. 1..40 chars: long enough for meaningful
    -- labels ("Wants to list next month") but short enough to display
    -- as a chip without truncation. Frontend should normalize whitespace
    -- and case before sending so 'Hot Lead' and 'hot lead' don't both
    -- exist for the same agent.
    tag          TEXT NOT NULL CHECK (length(tag) BETWEEN 1 AND 40),

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate (agent, pin, tag) — clicking "add tag" with the
    -- same string is a no-op rather than an error path.
    UNIQUE (agent_id, pin, tag)
);

-- Pattern 1: "list this agent's tags in this ZIP, with counts."
-- Powers the briefing-page filter chip row.
CREATE INDEX IF NOT EXISTS idx_lead_tags_v3_agent_zip_tag
    ON lead_tags_v3(agent_id, zip_code, tag);

-- Pattern 2: "what tags are on this parcel for this agent."
-- Powers the dossier tag chip row.
CREATE INDEX IF NOT EXISTS idx_lead_tags_v3_agent_pin
    ON lead_tags_v3(agent_id, pin);

-- RLS: agents read/insert/delete their own tag assignments. No UPDATE
-- — to "rename" a tag, an agent deletes and re-adds. The frontend can
-- automate that flow if needed; the schema stays simple.
ALTER TABLE lead_tags_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own tags" ON lead_tags_v3;
CREATE POLICY "agent reads own tags" ON lead_tags_v3
    FOR SELECT
    USING (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent inserts own tags" ON lead_tags_v3;
CREATE POLICY "agent inserts own tags" ON lead_tags_v3
    FOR INSERT
    WITH CHECK (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent deletes own tags" ON lead_tags_v3;
CREATE POLICY "agent deletes own tags" ON lead_tags_v3
    FOR DELETE
    USING (auth.uid() = agent_id);
