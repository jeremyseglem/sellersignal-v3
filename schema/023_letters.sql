-- ════════════════════════════════════════════════════════════════════
-- 023 — Letter sending infrastructure (Lob integration)
-- ════════════════════════════════════════════════════════════════════
--
-- Two tables + an ALTER on agent_profiles_v3, to support:
--   1. Single-letter sends via Lob
--   2. Full 6-letter sequence sends (Lob send_date scheduled, 1/30/60/90/135/180 days)
--   3. Print-to-PDF (no Lob, no charge — uses letters_sent_v3 with method='pdf')
--   4. Pre-paid credit balance billing
--   5. Cancel-sequence support (cancels any unmailed Lob letters)
--
-- Pricing (cents):
--   single letter:  299  ($2.99)
--   6-letter sequence: 1499 ($14.99, saves $3 vs sending individually)
--   PDF: 0
--
-- Status fields mirror Lob's lifecycle so we can keep them in sync
-- from webhooks. See https://docs.lob.com/#tag/Letters for the full
-- state machine.
-- ════════════════════════════════════════════════════════════════════


-- ────────────────────────────────────────────────────────────────────
-- letter_sequences_v3 — one row per 6-letter cohort started.
-- ────────────────────────────────────────────────────────────────────
--
-- When an agent clicks "Start full sequence," we create one row here
-- plus 6 rows in letters_sent_v3 (one per letter index, scheduled at
-- the appropriate Lob send_date). This table is the cancel anchor —
-- if the agent wants to stop the sequence after letter 3 has mailed,
-- we walk the children, cancel any still-unmailed via Lob, mark this
-- row cancelled.
--
-- Single-letter sends do NOT create a sequence row — letters_sent_v3
-- alone covers those (sequence_id is nullable). This matters because
-- the single-letter button is the most common path and forcing a
-- sequence row would muddy that case.
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS letter_sequences_v3 (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pin         TEXT NOT NULL,
    zip_code    TEXT NOT NULL,

    -- Lifecycle
    status      TEXT NOT NULL DEFAULT 'active',
    -- 'active'    — at least one child letter still pending or in-flight
    -- 'completed' — all 6 reached terminal state (delivered, returned, etc.)
    -- 'cancelled' — agent stopped the sequence; remaining unmailed letters
    --               were cancelled via Lob
    -- 'failed'    — couldn't start (e.g., address verification failed
    --               for the recipient before any letter went out)

    -- Total billed when sequence started (cents). Stored at sequence
    -- level even though letters_sent_v3 also tracks per-letter cost,
    -- so we have an audit trail of the bundled price the agent paid.
    total_charged_cents  INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    cancel_reason TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT letter_sequences_v3_status_check
        CHECK (status IN ('active', 'completed', 'cancelled', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_letter_sequences_v3_agent
    ON letter_sequences_v3(agent_id, status);

CREATE INDEX IF NOT EXISTS idx_letter_sequences_v3_pin
    ON letter_sequences_v3(pin, zip_code);


-- ────────────────────────────────────────────────────────────────────
-- letters_sent_v3 — one row per individual letter created.
-- ────────────────────────────────────────────────────────────────────
--
-- Every send (single letter, sequence member, or PDF) writes a row
-- here. For Lob letters we store the lob_letter_id so webhook updates
-- can find the row. For PDFs we store nothing in lob_letter_id and
-- the status is 'pdf_rendered' immediately.
--
-- We don't cascade-delete from this table for audit-trail reasons —
-- once a letter has cost the agent money (or just been sent), the
-- record must persist even if the parcel or sequence is later
-- removed. Agent deletion cascades cleanly because the FK to
-- auth.users does (we keep the agent_id but lose the auth row).
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS letters_sent_v3 (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pin         TEXT NOT NULL,
    zip_code    TEXT NOT NULL,

    -- The 6-letter cohort this belongs to, NULL for single-letter sends.
    sequence_id UUID REFERENCES letter_sequences_v3(id) ON DELETE SET NULL,

    -- Which letter in the sequence (1-6). For single-letter sends this
    -- is the index the agent chose from the SixLettersModal tabs.
    letter_index INTEGER NOT NULL,

    -- Send method
    method      TEXT NOT NULL,
    -- 'lob_mail'      — sent via Lob's letter API
    -- 'pdf_download'  — rendered as PDF for agent to print + mail themselves

    -- Lob bookkeeping. NULL for PDF method.
    lob_letter_id          TEXT,
    lob_send_date          TIMESTAMPTZ,    -- scheduled date for Lob to process
    lob_expected_delivery  TIMESTAMPTZ,    -- Lob's estimate at create time
    lob_mode               TEXT,           -- 'test' or 'live' — which key was used
    lob_tracking_url       TEXT,

    -- Status mirrors Lob's lifecycle for lob_mail; for pdf_download
    -- we set 'pdf_rendered' immediately.
    status      TEXT NOT NULL DEFAULT 'created',
    -- Common (Lob lifecycle):
    --   'created'                  — Lob accepted the request
    --   'processed_for_delivery'   — Lob produced the physical piece
    --   'mailed'                   — Left Lob's facility, in USPS hands
    --   'in_transit'               — Moving through USPS
    --   'in_local_area'            — At recipient's local USPS
    --   'delivered'                — Confirmed delivered
    --   're-routed'                — Forwarded
    --   'returned_to_sender'       — Undeliverable
    --   'cancelled'                — We cancelled before processing
    --   'failed'                   — Lob rejected (bad address, balance, etc.)
    -- PDF:
    --   'pdf_rendered'             — Rendered for agent download

    status_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Cost the agent was charged for this letter (cents). 0 for PDF.
    -- For sequence members this is total_charged_cents / 6 (rounded).
    cost_cents  INTEGER NOT NULL DEFAULT 0,

    -- Lifecycle timestamps. Populated from webhook events as Lob
    -- transitions the letter through statuses.
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mailed_at   TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    failed_at   TIMESTAMPTZ,
    fail_reason TEXT,

    -- The HTML body that was sent — stored for reprint / audit.
    -- Optional (NULL means we don't have it captured). Reasonable
    -- size cap is ~30KB per letter.
    rendered_html TEXT,

    -- Recipient address snapshot — what we actually sent to. Stored
    -- explicitly rather than re-resolving from parcels_v3 because
    -- owner addresses can change after a letter is in-flight, and we
    -- want to know exactly what got mailed.
    recipient_name      TEXT,
    recipient_line1     TEXT,
    recipient_line2     TEXT,
    recipient_city      TEXT,
    recipient_state     TEXT,
    recipient_zip       TEXT,

    CONSTRAINT letters_sent_v3_method_check
        CHECK (method IN ('lob_mail', 'pdf_download')),

    CONSTRAINT letters_sent_v3_status_check
        CHECK (status IN (
            'created', 'processed_for_delivery', 'mailed', 'in_transit',
            'in_local_area', 'delivered', 're-routed', 'returned_to_sender',
            'cancelled', 'failed', 'pdf_rendered'
        )),

    CONSTRAINT letters_sent_v3_letter_index_check
        CHECK (letter_index BETWEEN 1 AND 6)
);

CREATE INDEX IF NOT EXISTS idx_letters_sent_v3_agent
    ON letters_sent_v3(agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_letters_sent_v3_pin
    ON letters_sent_v3(pin, zip_code);

CREATE INDEX IF NOT EXISTS idx_letters_sent_v3_sequence
    ON letters_sent_v3(sequence_id)
    WHERE sequence_id IS NOT NULL;

-- Lob ID lookup is the hot path for webhook handlers — every status
-- update arrives keyed by lob_letter_id and we need a fast lookup.
CREATE UNIQUE INDEX IF NOT EXISTS idx_letters_sent_v3_lob_id
    ON letters_sent_v3(lob_letter_id)
    WHERE lob_letter_id IS NOT NULL;


-- ────────────────────────────────────────────────────────────────────
-- agent_profiles_v3 — add letter-billing + return-address fields.
-- ────────────────────────────────────────────────────────────────────
--
-- Pre-paid credit balance (cents). Single source of truth for agent's
-- letter purchasing power. Top-ups via Stripe add to it, sends debit
-- from it. We use cents (INT) instead of dollars (NUMERIC) to avoid
-- floating-point reconciliation issues with Stripe.
--
-- Return address is the physical sender address Lob prints on the
-- envelope. Required by USPS so undeliverable mail comes back to a
-- real place. Separate from the agent's profile address fields if any
-- existed — explicit so the agent can route returns wherever they
-- want (home, brokerage office, PO box).
--
-- All fields nullable for backward compatibility. Letter-send endpoint
-- will reject if return_address_line1 / city / state / zip are missing
-- and surface a profile-completion prompt.
-- ────────────────────────────────────────────────────────────────────

ALTER TABLE agent_profiles_v3
    ADD COLUMN IF NOT EXISTS letter_credit_cents   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS return_address_name   TEXT,
    ADD COLUMN IF NOT EXISTS return_address_line1  TEXT,
    ADD COLUMN IF NOT EXISTS return_address_line2  TEXT,
    ADD COLUMN IF NOT EXISTS return_address_city   TEXT,
    ADD COLUMN IF NOT EXISTS return_address_state  TEXT,
    ADD COLUMN IF NOT EXISTS return_address_zip    TEXT;

-- Sanity guard: balance can't go negative. The send endpoint must
-- check before deducting, but this is a belt-and-suspenders catch
-- for race conditions or buggy callers.
ALTER TABLE agent_profiles_v3
    DROP CONSTRAINT IF EXISTS agent_profiles_v3_letter_credit_nonneg;
ALTER TABLE agent_profiles_v3
    ADD CONSTRAINT agent_profiles_v3_letter_credit_nonneg
    CHECK (letter_credit_cents >= 0);


-- ────────────────────────────────────────────────────────────────────
-- RLS policies — agents see only their own letters and sequences.
-- ────────────────────────────────────────────────────────────────────
--
-- Letter sends are inherently private — an agent's outreach data is
-- competitive intel. RLS blocks cross-agent reads at the database
-- level even if a backend bug forgets to filter.
-- ────────────────────────────────────────────────────────────────────

ALTER TABLE letters_sent_v3       ENABLE ROW LEVEL SECURITY;
ALTER TABLE letter_sequences_v3   ENABLE ROW LEVEL SECURITY;

-- letters_sent_v3 policies
DROP POLICY IF EXISTS letters_sent_v3_select_own ON letters_sent_v3;
CREATE POLICY letters_sent_v3_select_own ON letters_sent_v3
    FOR SELECT
    USING (agent_id = auth.uid());

-- No INSERT/UPDATE/DELETE policies for the agent role — backend uses
-- the service-role key, which bypasses RLS. This keeps agents from
-- forging history.

-- letter_sequences_v3 policies
DROP POLICY IF EXISTS letter_sequences_v3_select_own ON letter_sequences_v3;
CREATE POLICY letter_sequences_v3_select_own ON letter_sequences_v3
    FOR SELECT
    USING (agent_id = auth.uid());


-- ────────────────────────────────────────────────────────────────────
-- updated_at triggers — keep updated_at fresh on row mutation.
-- ────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_letter_sequences_v3_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_letter_sequences_v3_updated_at ON letter_sequences_v3;
CREATE TRIGGER trg_letter_sequences_v3_updated_at
    BEFORE UPDATE ON letter_sequences_v3
    FOR EACH ROW
    EXECUTE FUNCTION set_letter_sequences_v3_updated_at();


-- ────────────────────────────────────────────────────────────────────
-- Column comments for future reference.
-- ────────────────────────────────────────────────────────────────────

COMMENT ON TABLE letter_sequences_v3
    IS 'One row per 6-letter sequence cohort started by an agent.';
COMMENT ON TABLE letters_sent_v3
    IS 'One row per individual letter (Lob send or PDF render).';
COMMENT ON COLUMN agent_profiles_v3.letter_credit_cents
    IS 'Pre-paid credit balance in cents. Top-ups add, sends debit.';
COMMENT ON COLUMN agent_profiles_v3.return_address_name
    IS 'Name printed on envelope sender line. Defaults to full_name in UI.';
COMMENT ON COLUMN letters_sent_v3.lob_letter_id
    IS 'Lob letter ID for webhook lookup. NULL for PDF method.';
COMMENT ON COLUMN letters_sent_v3.cost_cents
    IS 'What agent was charged (cents). 0 for PDF method.';
