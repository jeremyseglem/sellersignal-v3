-- ============================================================================
-- 020_skip_trace.sql — skip-trace cache and TCPA compliance acknowledgments.
--
-- Two tables, one feature:
--
--   1. skip_trace_results_v3 — per-agent cache of skip-trace lookup results.
--      30-day TTL via expires_at, enforced in application code (not via
--      pg_cron) because the cache is also intentionally inspectable for
--      audit and analytics. The UNIQUE constraint on (agent_id, pin) means
--      one cached lookup per (agent, parcel) at a time — re-tracing
--      overwrites via UPSERT. Storing the full persons JSONB lets the UI
--      render the original Tracerfy response unchanged on cache hits.
--
--   2. skip_trace_compliance_acks_v3 — one row per agent recording their
--      one-time TCPA / DNC acknowledgment. The acknowledgment is account-
--      level, not per-action — agents click "I understand and agree" once,
--      then skip-trace works for them indefinitely until they delete their
--      account.
--
-- Provider choice (Tracerfy) is recorded on each result row so when we
-- swap providers later, cached results from the old provider are still
-- traceable. The cache key is (agent_id, pin), not (agent_id, pin,
-- provider) — switching providers does NOT invalidate cached results,
-- because the cached data is what the agent has already paid for and
-- already seen.
-- ============================================================================


-- ── Part 1: skip_trace_results_v3 — per-agent result cache ──────────
CREATE TABLE IF NOT EXISTS skip_trace_results_v3 (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Owner of the cached result. ON DELETE CASCADE: agent account
    -- removal wipes their trace history.
    agent_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Parcel the trace was run against. Same PIN-not-FK pattern as
    -- migration 011/019 so parcel reseeds don't cascade.
    pin          TEXT NOT NULL,
    zip_code     TEXT NOT NULL,

    -- Which provider returned this data. Today: 'tracerfy'. Future
    -- providers (batchdata, reiskip, tloxp) will set this to their own
    -- name. Indexed because analytics queries will group by provider.
    provider     TEXT NOT NULL,

    -- The Tracerfy "hit" flag — false means no person found at the
    -- address. False rows are cached too so we don't waste credits
    -- re-tracing a known-miss within the TTL window.
    hit          BOOLEAN NOT NULL,

    -- Credits Tracerfy reported deducting for this call. 0 on miss.
    credits_deducted INTEGER NOT NULL DEFAULT 0,

    -- Full persons array from the provider response, stored verbatim.
    -- For Tracerfy: an array of {full_name, phones[], emails[],
    -- mailing_address, deceased, property_owner, litigator, age, dob}.
    -- JSONB so the UI can render whatever fields the provider supplies
    -- without server-side knowledge of the shape.
    persons      JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- If the call failed (network error, 4xx/5xx from provider, etc.)
    -- the error message is recorded here and persons is empty.
    -- Failed rows DO NOT count against the monthly cap and are NOT
    -- treated as cache hits — agents can immediately retry.
    error        TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 30 days after creation, application code treats this row as
    -- expired and triggers a fresh lookup. The cached row is not
    -- deleted — it remains for audit and the upsert overwrites in
    -- place.
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),

    -- One cached result per (agent, parcel). Upsert on this constraint
    -- when a fresh lookup succeeds.
    UNIQUE (agent_id, pin)
);

-- Pattern 1: "look up cached result for this agent + parcel."
-- Covered by the UNIQUE constraint's implicit index.

-- Pattern 2: "count this agent's traces in current month" for the
-- per-agent monthly cap.
CREATE INDEX IF NOT EXISTS idx_skip_trace_results_v3_agent_created
    ON skip_trace_results_v3(agent_id, created_at DESC);

-- Pattern 3: analytics by provider over time.
CREATE INDEX IF NOT EXISTS idx_skip_trace_results_v3_provider_created
    ON skip_trace_results_v3(provider, created_at DESC);

ALTER TABLE skip_trace_results_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own trace results" ON skip_trace_results_v3;
CREATE POLICY "agent reads own trace results" ON skip_trace_results_v3
    FOR SELECT
    USING (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent inserts own trace results" ON skip_trace_results_v3;
CREATE POLICY "agent inserts own trace results" ON skip_trace_results_v3
    FOR INSERT
    WITH CHECK (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent updates own trace results" ON skip_trace_results_v3;
CREATE POLICY "agent updates own trace results" ON skip_trace_results_v3
    FOR UPDATE
    USING (auth.uid() = agent_id)
    WITH CHECK (auth.uid() = agent_id);


-- ── Part 2: skip_trace_compliance_acks_v3 — TCPA/DNC ack ─────────────
CREATE TABLE IF NOT EXISTS skip_trace_compliance_acks_v3 (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- One row per agent. CASCADE so account deletion removes the ack
    -- (and the next time they sign up they re-acknowledge).
    agent_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,

    -- When they acknowledged. Useful for audit if a TCPA question
    -- ever comes up.
    acked_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Version of the acknowledgment text shown. If we update the
    -- legal language later (new regulations, etc.) we bump this and
    -- can force re-acknowledgment by querying for outdated versions.
    -- Start at 'v1' for the current text.
    ack_version  TEXT NOT NULL DEFAULT 'v1'
);

ALTER TABLE skip_trace_compliance_acks_v3 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent reads own ack" ON skip_trace_compliance_acks_v3;
CREATE POLICY "agent reads own ack" ON skip_trace_compliance_acks_v3
    FOR SELECT
    USING (auth.uid() = agent_id);

DROP POLICY IF EXISTS "agent inserts own ack" ON skip_trace_compliance_acks_v3;
CREATE POLICY "agent inserts own ack" ON skip_trace_compliance_acks_v3
    FOR INSERT
    WITH CHECK (auth.uid() = agent_id);

-- No UPDATE / DELETE policies — acks are append-only from the agent's
-- side. If we need to revoke (or the agent wants to revoke) it's an
-- admin operation, not done through the agent API.
