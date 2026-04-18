# SellerSignal v3 — Status at Session End (April 18, 2026)

## Read this first

This document exists because I (Claude) made the same architectural mistake
today that ultimately made the v1/v2 codebase unreliable: I treated
module names and partial code as a substitute for reading what the code
actually does. I built new orchestrators on top of a partial port of
the v2 pipeline without verifying the port was complete. The result:
hallucinated leads that looked credible to the code because the code
had never implemented the verification layer that would have rejected
them.

This is the same failure mode the user flagged explicitly. It is on
me. Next session needs to start from ground truth, not from my
optimism about what's already wired.

## What actually exists in v3 right now

### Real and trustworthy

- **Schema** (`schema/001_*.sql`, `schema/002_*.sql`) — 7 Postgres tables,
  RLS, zip_coverage_v3 lifecycle. Applied in Supabase. Works.
- **Parcel data for 98004** — 6,658 real parcels from the sandbox's
  `bellevue-98004-owners.json`, loaded via the `seed` CLI command. Real
  PINs, owners, addresses, values, tenure. Trustworthy.
- **Archetype classifier** (`backend/scoring/why_not_selling.py`) — after
  multiple fixes today, classifies parcels into 12 structural archetypes
  based on owner_type, tenure, name patterns. Correctly handles the
  98004 data. Zero API cost. Trustworthy.
- **Banding** (`backend/scoring/banding_v3.py`) — applies Band 0-4 based
  on archetype + hard disqualifiers (institutional, REO, tax agent,
  brokerage regex banks). Correctly produces ~1,880 Band 0 / 3,343 Band
  1 / 1,262 Band 2 / 173 Band 2.5 / 0 Band 3 for 98004. Trustworthy.
- **Coverage layer** (`backend/api/zip_gate.py`, `backend/api/coverage.py`) —
  enforces `zip_coverage_v3.status = 'live'` on all ZIP-scoped endpoints.
  Trustworthy.
- **CLI lifecycle** (`backend/ingest/zip_builder.py`) — status / register /
  seed / classify / band / publish / pause commands all work. `investigate`
  works at the *orchestration* level but produces bad results — see below.
- **Mock-mode safety fix** (commit `6de9dd3`) — no more silent mock-mode
  fallback. SERPAPI_KEY missing = hard error unless SELLERSIGNAL_MOCK=1
  is explicitly set. Trustworthy.
- **Frontend scaffold** — never run by the user, never tested against
  live data. The scaffolding exists but is unverified.

### NOT trustworthy — the core issue

**The investigation pipeline in v3 is NOT the v2 pipeline.** I ported
`investigation/__init__.py` (the raw SerpAPI scan + signal extraction)
but never ported the verification, candidate review, or evidence
resolution layers. v2 had:

  - `candidate_search.py` (512 lines) — per-family source-specific search
  - `candidate_review.py` (243 lines) — rejects ~96% of raw signals
  - `decision_signals.py` (265 lines) — entity activity cross-reference
  - `lead_builder.py` (303 lines) — synthesis into verified leads
  - `obit_verification.py` (215 lines) — dedicated obit verification
  - `evidence_resolution.py` (1,055 lines) — resolves evidence to owner

  **Total: 2,593 lines of verification logic that v3 does not have.**

When I ran the investigation on 98004 with real SerpAPI data, the
pipeline produced 11 CALL NOWs, all false positives. Every obituary
match was a different person who shared only a common first name with
the owner. Every probate match was either a law-firm marketing page or
a same-first-name attorney with unrelated practice. The name-match
filter I added today (`_snippet_mentions_owner`) fires on any token,
including common first names like "John", "James", "Robert" — which is
why the false positives got through.

This is not fixable with a surface patch. The v2 pipeline had
multi-stage evidence resolution that validated every claim against
multiple corroborating sources. v3 has one regex pass with no
verification layer. The investigation engine v3 currently has is not
capable of producing trustworthy leads, regardless of how many times
we tighten its regex.

## What was spent / what was built

- SerpAPI credits spent today:
  - First run: **$0** (mock mode — not real, produced synthetic output)
  - Second run: **$7.36** (real, produced 11 false-positive CALL NOWs)
  - Total real: **$7.36**

- Supabase: tables created, 98004 parcels loaded, 98004 classified and
  banded, 98004 paused (no agent can query).

- No frontend has been run. No Railway deploy exists. v3 has never
  served a real user request. The live sellersignal.co still points at
  v1 — completely untouched by today's work.

## Current state of 98004 in Supabase

- `zip_coverage_v3.status = 'paused'` (set at session end)
- `parcels_v3`: 6,658 real parcels, classified, banded
- `investigations_v3`: contains real SerpAPI results from the second run
  that should be treated as garbage. Either deleted at session end or
  preserved for analysis — check state on pickup.

## Two paths forward (user picks next session)

### Path A: Port the v2 verification pipeline into v3

Estimated: 2-3 focused Claude Code sessions.

Must port (in order):
1. `candidate_search.py` → `backend/candidates/search.py`
   Per-family source-specific search. Replaces the single
   `investigate_parcel` function with a family-by-family fanout.
2. `candidate_review.py` → `backend/candidates/review.py`
   The layer that rejected 565/600 candidates in the v2 run.
3. `decision_signals.py` → `backend/candidates/entity_activity.py`
   Cross-references entity activity across the full deed universe.
4. `obit_verification.py` → `backend/candidates/obit_verify.py`
   Dedicated obituary verification — must match full name, geography,
   date of death against living parcel owner.
5. `evidence_resolution.py` → `backend/candidates/evidence.py`
   The largest and most subtle module. Decides whether evidence
   actually resolves to the owner. Do not simplify when porting.
6. `lead_builder.py` → `backend/candidates/lead_builder.py`
   Synthesis into shipped leads with approach, channel, window.

Then rewire `backend/selection/zip_investigation.py` to call the full
pipeline, not just `investigate_parcel`.

After this, v3 produces real leads. Then run 98004 investigation
again (~$8).

### Path B: Use the v2 scripts directly, feed results into v3 schema

Estimated: 1 focused Claude Code session.

v2 scripts live at `/mnt/user-data/outputs/` / previous sandboxes.
Run them against 98004 directly. Output JSON in the shape v3 expects.
Load into `investigations_v3`. Use v3 only as the hosting/UI layer.

Faster path to a working product. Keeps two codebases alive
permanently — technical debt, but acceptable as an MVP path.

### Path A is better long-term. Path B is better for this-month momentum.

## Critical principles for next session

1. **Read before writing.** Before porting a module, read the full v2
   source. Don't assume. Don't rely on module names.

2. **Verify against the real 98004 false-positive cases.** The 11
   CALL NOWs from today's run are concrete failure cases. Any new
   pipeline must reject all 11 before spending money.

3. **No silent fallbacks.** Mock mode is explicit-only now. Keep it
   that way. Any new fallback paths (cache miss, missing config, etc.)
   must fail loudly.

4. **Owner-name matching must require surname-level distinctiveness.**
   First-name-only matches are worse than useless at luxury-territory
   scale.

5. **Every signal must carry provenance.** Source URL, source snippet,
   matched query. If the pipeline can't produce these, the signal is
   not a signal.

6. **No driveways without verification.** The real test of any lead is:
   would you, Jeremy, walk up that driveway based on this evidence? If
   not, the signal fails.

## Commit history of today's session

- `5b69049` — Initial v3 scaffold
- `cb29777` — Decision engine + why_not_selling + persistence + 3 API endpoints
- `4208436` — ZIP coverage layer (schema 002, gate, CLI)
- `25c4933` — Full ZIP build pipeline (ingest/band/investigate wired)
- `e748ebd` — Frontend scaffold + schema apply docs
- `b383853` — RLS fix for serpapi_budget_v3
- `5f01759` — Seed command + bellevue-98004-owners.json data
- `7f37ec6` — classify/band: paginate reads, update-not-upsert
- `6c4d201` — Classifier: phrase-context matching for estate/heirs
- `443c9f9` — Signal extraction: provenance + name matching (INSUFFICIENT)
- `6de9dd3` — CRITICAL: kill silent mock-mode fallback

## What to tell next Claude

"Read docs/STATUS.md first. It describes a pipeline architecture gap
that I (previous Claude) missed during the v2→v3 port. Do NOT iterate
on the current v3 investigation module. The fix is to port the v2
candidate pipeline properly. User has decided on Path A or Path B —
ask which. Do not start coding until the user confirms the path."
