-- Migration 015: agent role column + operator seeding
--
-- Adds a 'role' column to agent_profiles_v3 with values:
--   'agent'    — the default. Sees one claimed ZIP. Can claim a ZIP.
--   'operator' — platform operator. Sees all ZIPs. Cannot claim a ZIP
--                (operators don't compete for territory).
--
-- Also seeds the two known operator emails (Jeremy, Brian). The
-- update is keyed on email so it works whether or not those agents
-- have signed up yet — when they sign up later, the on-signup
-- trigger from migration 010 creates their row with the default
-- 'agent' role, and a re-run of this migration's UPDATE will
-- promote them. (Or the operator email list can be re-applied
-- ad-hoc.)

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'agent';

-- Constrain to known values. Idempotent — drops and re-adds the
-- check constraint so re-running this migration doesn't fail.
ALTER TABLE agent_profiles_v3
    DROP CONSTRAINT IF EXISTS agent_profiles_v3_role_check;
ALTER TABLE agent_profiles_v3
    ADD CONSTRAINT agent_profiles_v3_role_check
    CHECK (role IN ('agent', 'operator'));

-- Seed operators by email. Safe to re-run — only updates rows
-- whose role isn't already 'operator'.
UPDATE agent_profiles_v3
   SET role = 'operator'
 WHERE email IN (
       'jeremy.seglem@theagencyre.com',
       'brian.hawkins@theagencyre.com'
       )
   AND role <> 'operator';

-- Index supports the gate queries: lookups by id are already keyed
-- (PK), but we sometimes filter by role for admin-style endpoints.
CREATE INDEX IF NOT EXISTS idx_agent_profiles_v3_role
    ON agent_profiles_v3(role)
    WHERE role <> 'agent';
