-- ============================================================
-- Migration 021: Enhanced Skip Tracing async support
-- ============================================================
-- Purpose: extend skip_trace_results_v3 to track Tracerfy's async
-- Enhanced Skip Tracing batch jobs. Enhanced returns up to 8 relatives
-- with full contact info, 5 aliases, 5 past addresses — exactly what
-- we need to surface PRs who don't live at the property.
--
-- Standard (synchronous) trace stays in `persons` JSONB. Enhanced
-- data lands in `enhanced_data` JSONB after the webhook fires.
--
-- Flow:
--   1. /lookup runs standard trace, caches result, returns to agent
--   2. If probate lead + PR not in standard result, submit Enhanced
--      batch to Tracerfy
--   3. Save tracerfy_queue_id + enhanced_pending=true on the cache row
--   4. Tracerfy POSTs webhook to us 5-30 min later with results
--   5. Webhook handler fetches the CSV, parses relatives, updates
--      enhanced_data and enhanced_pending=false
--   6. Agent's next view of the lead surfaces the new family contacts
--
-- Run this in the Supabase SQL editor.
-- ============================================================

-- ------------------------------------------------------------
-- New columns on skip_trace_results_v3
-- ------------------------------------------------------------

ALTER TABLE skip_trace_results_v3
  -- Tracerfy's queue_id (from POST /v1/api/trace/ response). Webhook
  -- delivery references this to find the matching cache row.
  ADD COLUMN IF NOT EXISTS enhanced_queue_id text,

  -- True between submission and webhook completion. Frontend uses
  -- this to render "Searching for relatives..." banner.
  ADD COLUMN IF NOT EXISTS enhanced_pending boolean DEFAULT false NOT NULL,

  -- Timestamps for diagnostics + stale-detection. If pending=true and
  -- submitted_at is >30 min ago, the webhook probably never arrived;
  -- treat as silent failure and stop showing the loading banner.
  ADD COLUMN IF NOT EXISTS enhanced_submitted_at timestamptz,
  ADD COLUMN IF NOT EXISTS enhanced_completed_at timestamptz,

  -- The relatives + aliases + past addresses payload, as returned by
  -- the webhook and parsed from the CSV. Shape:
  --   {
  --     "relatives": [
  --       {"name": "Janice Parker", "relationship": "daughter",
  --        "phones": ["6098932735"], "emails": ["..."], "age": 62},
  --       ...
  --     ],
  --     "aliases": [...],
  --     "past_addresses": [...]
  --   }
  -- Defensive nullable — webhook may arrive with parse failure or
  -- empty data. Distinguish "completed, no data" (empty {}) from
  -- "not yet completed" (null).
  ADD COLUMN IF NOT EXISTS enhanced_data jsonb,

  -- For diagnostics: webhook delivery failed, CSV parse failed, etc.
  -- Null on success.
  ADD COLUMN IF NOT EXISTS enhanced_error text;

-- ------------------------------------------------------------
-- Index for fast webhook lookup by queue_id
-- ------------------------------------------------------------
-- The webhook handler receives a queue_id and needs to find the
-- matching cache row immediately. Without this index, the lookup
-- table-scans skip_trace_results_v3, which is fine at small scale
-- but worth indexing now since we know the access pattern.

CREATE INDEX IF NOT EXISTS idx_skip_trace_enhanced_queue_id
  ON skip_trace_results_v3 (enhanced_queue_id)
  WHERE enhanced_queue_id IS NOT NULL;

-- ------------------------------------------------------------
-- Backfill (no-op): existing rows are pre-Enhanced, leave them alone
-- ------------------------------------------------------------
-- No backfill needed. New rows get the defaults. Existing rows
-- have enhanced_pending=false (the default) and null for the rest,
-- which is the correct "this row predates Enhanced" state.

-- ------------------------------------------------------------
-- Verification queries (run these after applying to confirm)
-- ------------------------------------------------------------
-- Check the new columns exist:
--   SELECT column_name, data_type, column_default
--     FROM information_schema.columns
--    WHERE table_name = 'skip_trace_results_v3'
--      AND column_name LIKE 'enhanced_%'
-- ORDER BY column_name;
--
-- Confirm the index was created:
--   SELECT indexname FROM pg_indexes
--    WHERE tablename = 'skip_trace_results_v3'
--      AND indexname = 'idx_skip_trace_enhanced_queue_id';
