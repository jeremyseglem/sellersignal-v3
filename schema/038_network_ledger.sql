-- 038: The credibility ledger (dossier Contract 3).
--
-- "History cannot be backfilled, so the ledger's shape ships before the
-- marketplace does — even if scoring stays invisible for months."
--
-- Append-only event log for every marketplace interaction, both sides:
--   buyer seat:      need_posted | need_updated | need_renewed |
--                    need_withdrawn | need_expired
--   system:          match_run (payload: matched, tiers, zips pinged,
--                    specificity = criteria_count)
--   territory owner: demand_viewed | ping_pursued | ping_ignored |
--                    ping_declined | connection_opened |
--                    connection_rated (payload: rating, client_was_real)
--   integrity:       flag_raised | flag_confirmed
--                    (two confirmed no-real-buyer flags terminate a seat)
--
-- Scores are DERIVED from this log later; nothing here gates anything
-- yet. It ranks, it never gates.

CREATE TABLE IF NOT EXISTS network_ledger_v3 (
    id          BIGSERIAL PRIMARY KEY,
    actor       TEXT NOT NULL,              -- email identity (or 'system'/'admin')
    actor_role  TEXT NOT NULL,              -- buyer_seat | territory_owner | system
    event_type  TEXT NOT NULL,
    need_id     UUID,
    zip_code    TEXT,
    counterparty TEXT,                      -- the other seat, when one exists
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_network_ledger_actor
    ON network_ledger_v3 (actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_network_ledger_need
    ON network_ledger_v3 (need_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_network_ledger_event
    ON network_ledger_v3 (event_type, created_at DESC);

ALTER TABLE network_ledger_v3 ENABLE ROW LEVEL SECURITY;  -- no policies: service-role only
