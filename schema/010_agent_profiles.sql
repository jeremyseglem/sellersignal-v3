-- ============================================================================
-- 010_agent_profiles.sql — agent profile table for V3.
--
-- One row per authenticated user. Created fresh; no migration from any
-- legacy profiles table. Beta phase fields only — billing/Stripe state
-- lives elsewhere and is wired in a later migration.
--
-- Keys to auth.users (Supabase Auth's built-in users table) so the
-- profile is automatically scoped to the signed-in user. Row Level
-- Security policies below enforce that an agent can only read and
-- write their own row.
--
-- Fields support two end uses:
--   1. Agent identity in the SiteHeader and the dossier ('Hi from
--      [agent_name]')
--   2. Letter automation (Lob, Session 4) — full_name, brokerage,
--      phone, license_number, signature_url, headshot_url all flow
--      into the rendered letterhead.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_profiles_v3 (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,

    -- Identity
    full_name       TEXT,
    phone           TEXT,
    brokerage       TEXT,
    license_number  TEXT,
    license_state   TEXT,                  -- 'WA', 'MT', etc.

    -- Letter assets — public Supabase Storage URLs. Uploads are
    -- handled client-side; backend just stores the resulting URL.
    headshot_url    TEXT,
    signature_url   TEXT,
    logo_url        TEXT,                  -- agent's brokerage / personal logo

    -- Territory assignment. Beta is one ZIP per agent, enforced by
    -- the unique constraint below. Future phases may relax this to
    -- many-to-many via a separate agent_territories table.
    assigned_zip    TEXT UNIQUE,

    -- Optional onboarding state — drives the 'fill in your profile'
    -- prompts after first sign-in.
    onboarding_completed_at TIMESTAMPTZ,

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on assigned_zip for the common 'who has this ZIP?' lookup
-- on the territories grid.
CREATE INDEX IF NOT EXISTS idx_agent_profiles_v3_assigned_zip
    ON agent_profiles_v3(assigned_zip)
    WHERE assigned_zip IS NOT NULL;

-- Trigger to keep updated_at fresh on every row update.
CREATE OR REPLACE FUNCTION set_agent_profiles_v3_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_profiles_v3_updated_at ON agent_profiles_v3;
CREATE TRIGGER trg_agent_profiles_v3_updated_at
    BEFORE UPDATE ON agent_profiles_v3
    FOR EACH ROW
    EXECUTE FUNCTION set_agent_profiles_v3_updated_at();

-- ── Row Level Security ──────────────────────────────────────────
-- Each agent can read and write their own profile, nothing else.
-- The backend service-key bypasses RLS so server-side admin reads
-- still work.
ALTER TABLE agent_profiles_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own profile" ON agent_profiles_v3;
CREATE POLICY "agent reads own profile" ON agent_profiles_v3
    FOR SELECT
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "agent updates own profile" ON agent_profiles_v3;
CREATE POLICY "agent updates own profile" ON agent_profiles_v3
    FOR UPDATE
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "agent inserts own profile" ON agent_profiles_v3;
CREATE POLICY "agent inserts own profile" ON agent_profiles_v3
    FOR INSERT
    WITH CHECK (auth.uid() = id);

-- ── Auto-create profile row on user signup ──────────────────────
-- When Supabase Auth creates a new auth.users row (e.g. via magic
-- link), trigger an insert into agent_profiles_v3 with the user's
-- id and email. The agent fills in the rest via the /profile form.
CREATE OR REPLACE FUNCTION create_agent_profile_on_signup()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.agent_profiles_v3 (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_create_agent_profile_on_signup ON auth.users;
CREATE TRIGGER trg_create_agent_profile_on_signup
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION create_agent_profile_on_signup();
