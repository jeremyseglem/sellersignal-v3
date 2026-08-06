-- 039: Buyer-agent seats (dossier Phase 3 account type, dark-gated).
--
-- Buyer agents register through the same auth + profile system as
-- territory agents (agent_profiles_v3 already carries full_name,
-- phone, brokerage, license_number, license_state from migration 010).
-- This migration adds:
--   role 'buyer_agent'      — post-demand-only seat; no supply access
--   network_approved        — dark switch: signups accumulate, access
--                             is granted per-seat by an operator. The
--                             pending roll is itself the marketing
--                             asset (verified buyer-agent audience +
--                             territory-funnel leads).
--   license_status          — 'unverified' | 'verified' | 'rejected';
--                             manual verification for beta, registry
--                             integration later.

ALTER TABLE agent_profiles_v3
    DROP CONSTRAINT IF EXISTS agent_profiles_v3_role_check;
ALTER TABLE agent_profiles_v3
    ADD CONSTRAINT agent_profiles_v3_role_check
    CHECK (role IN ('agent', 'operator', 'buyer_agent'));

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS network_approved BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS license_status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS network_joined_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_agent_profiles_network_pending
    ON agent_profiles_v3 (network_approved, role)
    WHERE role = 'buyer_agent';
