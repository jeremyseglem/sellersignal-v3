-- Migration 016: operator-aware on-signup trigger
--
-- Replaces the create_agent_profile_on_signup() function from
-- migration 010 with a version that sets role='operator' at row
-- creation time when the new user's email matches the hardcoded
-- operator allowlist.
--
-- Why this exists:
-- Migration 015 added a 'role' column and seeded existing
-- operator rows by email. But operators who sign up AFTER
-- migration 015 ran would be created with the default role
-- ('agent'), and would need a manual UPDATE to be promoted.
-- This migration moves the operator decision into the trigger
-- itself, so any future operator signup is correctly classified
-- without intervention.
--
-- Adding a new operator: append their email to the IN (...) list
-- below and re-run this migration (it's a CREATE OR REPLACE so
-- it's idempotent).
--
-- This is intentionally a hardcoded allowlist rather than a
-- table lookup. With 2-4 known operators ever, the simplicity
-- wins; an allowlist table would be over-engineering.

CREATE OR REPLACE FUNCTION create_agent_profile_on_signup()
RETURNS TRIGGER AS $$
DECLARE
    new_role TEXT;
BEGIN
    -- Decide role based on email allowlist.
    IF NEW.email IN (
        'jeremy.seglem@theagencyre.com',
        'brian.hawkins@theagencyre.com'
    ) THEN
        new_role := 'operator';
    ELSE
        new_role := 'agent';
    END IF;

    INSERT INTO public.agent_profiles_v3 (id, email, role)
    VALUES (NEW.id, NEW.email, new_role)
    ON CONFLICT (id) DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- The trigger itself was created in migration 010 and points at
-- the function by name; replacing the function above is enough.
-- No need to DROP/RECREATE the trigger.
