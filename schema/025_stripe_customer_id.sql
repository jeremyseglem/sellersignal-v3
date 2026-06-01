-- ============================================================================
-- 025_stripe_customer_id.sql — Stripe Customer mapping on agent profile.
--
-- Adds the stripe_customer_id column to agent_profiles_v3. One Stripe
-- Customer per agent — created on first checkout, persisted forever.
-- The saved payment method on that Customer is reused for:
--   1. The $299/month recurring territory subscription
--   2. Future Lob mail-balance top-ups (separate wiring, same Customer)
-- No re-entry of card details ever required after the first purchase.
--
-- The stripe_subscription_id column already exists on agent_territories_v3
-- (in the initial v3 schema). This migration only adds the customer-level
-- field on the profile.
--
-- Operators (jeremy.seglem@theagencyre.com, brian.hawkins@theagencyre.com)
-- never go through the checkout flow and will keep stripe_customer_id = NULL
-- indefinitely. That's expected.
-- ============================================================================

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

-- One Stripe Customer per agent — enforced via a partial unique index that
-- ignores NULL (so operators and pre-checkout agents don't conflict).
CREATE UNIQUE INDEX IF NOT EXISTS agent_profiles_v3_stripe_customer_id_idx
    ON agent_profiles_v3(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;
