# SellerSignal v3 — Session End (May 1, 2026)

## Read this first

This was a long session — six hours of debugging-then-shipping after a previous Claude in the same calendar window already shipped the multi-ZIP coverage work. The starting state: 281 Call Now leads across 11 ZIPs but Brian was flagging visible quality problems (stacked unrelated probates, scripts addressing dead people, capped pipeline counts).

I shipped real fixes for most of his named complaints. I also helped design — but did not build — what is probably the most important product decision in the project's history: **agent-voice-driven outreach generation**, which converts SellerSignal from "tool that gives you leads" to "tool that helps you win them in your own voice."

The build for that is the next session's job. This doc is the handoff so it doesn't get lost.

---

## What shipped tonight (in commit order)

### 1. Soft live name-match gate (`087f95f`)
**File:** `backend/ingest/legal_filings.py`

Brian flagged "every divorce shows probate" — single parcels attributed to multiple unrelated court filings. Audit found ~50 cases where unrelated Vietnamese names matched on particles (THI/VAN) plus surname only.

Two changes:
- Strip particles `THI`, `VAN`, `DE`, `LA`, `EL`, `DA` from `normalize_name`
- Keep single-letter tokens (was `len >= 2`, now `len >= 1`) so middle initials like `S` in "Michael S Hansen" don't get silently dropped

Production impact: 51 strict matches dropped, 3 Call Now leads affected. Trust continuity preserved (the soft gate doesn't catch Brian's screenshot cases — those go to shadow review).

### 2. Schema migration 013 — match review columns (applied in Supabase manually)
**File:** `schema/013_match_review.sql`

Adds three nullable columns to `raw_signal_matches_v3`:
- `match_review_status` — `likely_valid` / `needs_review` / `likely_false_positive` / NULL
- `match_review_reason` — short tag like `particle_only`, `middle_initial_disagree`, etc.
- `match_confidence_score` — 0.0 to 1.0

Plus a partial index on the status column. Idempotent migration (`IF NOT EXISTS` everywhere).

### 3. Shadow-mode match review classifier + audit endpoint (`4083620`, `5a35238`)
**Files:** `backend/scoring/match_review.py` (new), `backend/api/admin.py`

Pure classifier `classify_match(filing, owner)` returns `(status, reason, confidence)`. Stricter than the live gate. Detects:
- particle-only overlaps that the soft gate now strips at write-time but historical rows still have
- middle-name conflicts (initial-aware: 'S' matches 'Steven', not 'Ray')
- first-name swap (JOHN+RICHARDS overlapping but JOHN is first in one and middle in the other)
- exact full-token agreement → highest confidence likely_valid

Two endpoints:
- `POST /api/admin/audit-match-review` — runs classifier over all 1,117 strict matches, writes verdicts. Dry-run by default. Joins `raw_signal_matches_v3` to `parcels_v3` (for owner_name + zip_code) and `raw_signals_v3` (for matched_party from party_names[0]).
- `GET /api/admin/match-review-queue` — returns flagged rows sorted ascending by confidence. Filterable by status and zip_code.

Audit ran. Distribution against 1,117 production rows:
- 525 likely_valid (47%)
- 488 likely_false_positive (44%)
- 104 needs_review (9%)

### 4. Tax-foreclosure parcel-match handling fix (`8a2bbaf`)
**Files:** `backend/scoring/match_review.py`

Tax-foreclosure rows store a sentinel string in `matched_party` like `(Tax Foreclosure — parcel match)` because the match was made by parcel ID, not by name. The classifier was incorrectly flagging those as `insufficient_overlap`. Fix: detect "parcel match" substring in matched_party and return `likely_valid/cleared` with confidence 1.0.

5 of 7 Call Now leads at risk before fix moved out of the false-positive bucket after fix.

### 5. Promotion endpoint (`8a2bbaf`)
**Files:** `backend/api/admin.py`

`POST /api/admin/promote-match-review-deletion?reason=X&confirm=true` — deletes rows by reason. Required to actually act on shadow-mode findings. Dry-run by default. Reason-scoped — one promotion = one named cohort, traceable.

### 6. Promoted `insufficient_overlap` cohort
Ran the promotion. **63 rows deleted, 1 net Call Now lead dropped** across all 11 ZIPs.

### 7. True pipeline / watch-list counts (`588279d`)
**Files:** `backend/selection/weekly_selector.py`, `backend/api/briefings.py`, `frontend/src/pages/BriefingPage.jsx`, `frontend/src/components/briefing/PipelineList.jsx`

Brian: "Pipeline always says 100 in pipeline, there are way more."

Root cause: `build_now_count` and `strategic_holds_count` reflected rendered list LENGTH, capped at 100 / 1000.

Two new helpers in weekly_selector: `count_build_now_eligible()` and `count_strategic_holds_eligible()`. Mirror the selector's eligibility filters exactly, including owner-key dedup. New stats fields `build_now_total` and `strategic_holds_total`. Frontend prefers the new fields with fallback to old.

Real numbers exposed:
- 98004 Bellevue: **992 in pipeline · 892 on watch list** (was 100 · 892)
- 98006: 3,088 / 2,988
- 98052: 3,171 / 3,071

Render caps preserved at 100 / 1000 for performance. Only the count display changed.

### 8. Default Phone/Letter/Door scripts visible without Deep Signal (`95af985`)
**Files:** `frontend/src/lib/archetypePlaybooks.js`, `frontend/src/components/ParcelDossierV2.jsx`

Brian: Deep Signal addresses dead people. Specifically saw a probate letter "Dear Mr. Pere, you've been the owner for over 42 years" — addressed to the deceased.

Root cause: Deep Signal prompt receives `owner_name` + cohort + signals but NOT structural data (PR name, contact_status, archetype). It writes scripts blind to who's actually being addressed.

Fix path B (free path): use structural data already exposed via `harvester_matches[].personal_representative` to render archetype-correct scripts immediately. No LLM call needed.

Added `defaultScripts: { phone, letter, door }` to each of 6 archetypes (probate / divorce / estateTransition / investor / longTenure / general). Token substitution at render time:
- `{pr_first}` from harvester match's PR (probate)
- `{decedent}` from all_case_parties (probate)
- `{owner_first}`, `{owner_name}`, `{address}`, `{city}` from parcel
- Safe fallbacks: "Friend" / "your loved one" never invents a name

`WhatToSaySection` rewritten: always render Phone/Letter/Door tabs from defaults. Deep Signal output preferred per-channel when available. Generate Deep Signal button kept but moved below tabs as optional upgrade.

### 9. Six-letter archetype-specific sequences (`8864899`)
**Files:** `frontend/src/lib/sixLetters.js`

Refactored `generateSixLetters(parcel, harvesterMatches, archetypeKey)` to dispatch on archetype. Six sequences:
- probate (addresses PR by first name, never the deceased)
- divorce (discreet, brief, neutral)
- investor (institutional voice, business cadence, 1031/disposition framing)
- trust (institutional, references trust accounting / beneficiary distributions)
- estateTransition (family-relational)
- longTenure / general fallback (original copy preserved)

All keep the same Day 1/30/60/90/135/180 cadence. The wiring is correct. **The COPY is generic and Anthropic-house-style.** Jeremy reviewed the trust sequence and said: "these are dense and inhuman. solid concept but really rote and lawyer like."

The probate sequence was revoiced in Jeremy's voice (saved as draft in `frontend/src/lib/sixLetters_probate_v2.js`, NOT wired into production). Jeremy approved it. The trust revoice (saved as `frontend/src/lib/sixLetters_trust_v2.js`) is also NOT wired and Jeremy explicitly rejected it as too dense and missing agent personality.

The voice problem is what led to the agent-voice product redesign below.

---

## The big idea (queued for next session)

Mid-session Jeremy proposed: **what if the phone/letter/door scripts were generated based on the agent's actual voice and bio, not a generic template?** Every other lead-gen tool gives every agent the same template. SellerSignal would give each agent THEIR letter for THIS lead.

This isn't a feature, it's the product. It converts SellerSignal from "tool that finds leads" to "tool that helps you win leads in your own voice." It also creates real switching cost — the system encodes how the agent works, not just what the system finds.

### Architecture (final design from session)

**Inputs (single voice block, no 20-field form):**
- Free text: "Tell me how you typically approach sellers. Paste 1-2 real messages you've sent (email, text, letter), OR describe your style. What makes you different from other agents?"
- Optional click-to-expand prompts: "More direct or relationship-first?" / "Speed, discretion, or price?" / "What do clients usually say about you?"

**Storage:**
```
agent_profile {
  agent_id,
  voice_raw: "...full text...",
  generated_scripts: {
    probate: "...",
    investor: "...",
    long_tenure: "...",
    divorce: "...",
    estate_transition: "...",
    trust: "...",
  }
}
```

**Generation: ONCE per agent at onboarding (5-6 LLM calls total).** Not per lead.

**Lead-level rendering: token substitution only, no LLM call.** Inject lead specifics into stored archetype script.

**Fallback:** if agent has no profile, use default voice (Jeremy's, since that's what we voice-matched the v2 probate draft against).

### Production-ready prompt set

System prompt:
```
You are helping a real estate agent write seller outreach in their own voice.

Your job is not to create a polished marketing template.
Your job is to preserve the agent's actual tone, restraint, confidence, and way of speaking.

Rules:
- Sound like the agent, not like a copywriter.
- Keep it short.
- Avoid salesy language.
- Avoid "I hope this finds you well."
- Avoid pressure.
- Avoid overexplaining.
- Do not invent credentials, statistics, or personal claims.
- Use plain language.
- The message should feel human, specific, and appropriate to the situation.
```

Per-archetype user prompts: see "Lead archetype prompts" section in this doc's tail. Five archetypes drafted (probate / investor / long-tenure / divorce / permit-completion). Trust and estate-transition still need prompts.

### One real correction Claude flagged

The probate prompt has: *"avoid saying 'I noticed the probate filing' unless the agent's voice is unusually direct."*

That's a guardrail that asks the LLM to make a judgment call about how direct the agent is. Models default soft under that ambiguity. **Better to make structural-acknowledgment a separate explicit input on the agent profile.**

Add a single onboarding question:
> "When you reach out about a probate, do you mention the filing directly, or do you keep the source vague?"

Same applies to divorce ("not mention divorce directly" is the right default but a forensic-style agent might override). Let agent voice override the prompt's guardrail explicitly, not implicitly.

### What NOT to build in v1
- 20+ profile fields
- Structured form inputs
- Per-lead LLM generation (cost would explode)
- Heavy templating system

### What to build in v1 (estimated 1-2 days)
1. Schema migration: `agent_profiles` table with `voice_raw` text + `generated_scripts` JSON column + `structural_acknowledge_preferences` JSON
2. Onboarding flow: single text input + optional helper prompts, plus the structural-acknowledgment question
3. Generation endpoint: `POST /api/agent/generate-scripts` — runs 5-6 LLM calls, stores results
4. Render integration: dossier prefers agent's generated_scripts when available, falls back to default voice
5. UI label change: "What to say" → "Your approach"

---

## Open questions for next session

### Agent-voice product
1. **Trustee name extraction.** Trust archetype scripts will need to address a specific trustee name when one is identifiable. Today the data we have is the trust title in `parcel.owner_name` ("Coday Margaret Gold Trust") — no extracted current trustee. Two paths: (a) leave the trustee placeholder for the agent to fill on the call, (b) build trustee extraction in the data pipeline. Worth deciding before wiring trust into the agent-voice flow.

2. **Default voice when agent has no profile.** Jeremy's voice (per the v2 probate draft) is a reasonable default. But the trust v2 draft was rejected as bad even in his voice. Either we ship the agent-voice product alongside fixing the default trust voice, or we accept that the no-profile state has known-mediocre trust copy as a known caveat.

3. **What goes inline vs. in onboarding.** The "structural acknowledgment" preference (mention the filing directly or not) feels like onboarding. But there might be a per-lead override too — Brian might handle one specific Bellevue probate where he WOULD mention the filing because he knows the family. Worth deciding whether overrides exist.

### Match review (deferred)
4. **`first_name_diff` cohort** (234 rows in shadow). Sample of 30 + 10 spot-checks showed ~93-100% are confident different-humans. Promoting would drop ~76 Call Now leads. Jeremy chose not to promote tonight to preserve trust continuity. Brian or Jeremy should review the queue at `GET /api/admin/match-review-queue?status=likely_false_positive&limit=N` and make the call.

5. **`middle_initial_disagree` cohort** (141 rows). Smaller sample reviewed but not enough to promote confidently. Same disposition as #4.

6. **`token_only_no_middle` cohort** (104 rows in needs_review). Genuinely ambiguous. The "Hsin Yu Lin / SHANA HSIN-HWA LIN" class. Probably needs a more nuanced rule than current classifier supports — short-Asian-name vs long-Asian-name structural detection. Defer.

### Deep Signal investment decision
7. **Run investigation across all 11 ZIPs?** Currently only 98004 has `investigated_count > 0`. Investigation pipeline (LinkedIn, Google news, FastPeopleSearch, etc. via SerpAPI) is built and wired but only enabled for one ZIP. Cost: ~$0.02-0.05 per parcel × ~80,000 parcels across 11 ZIPs = $1,600-4,000 one-time + ongoing for new leads. Big budget question. Without it, Deep Signal stays mostly useless for 10 of 11 ZIPs. With it, Deep Signal becomes a real differentiator — actual LinkedIn-resolved professional context, news mentions, age signals.

### Data-pipeline work uncovered
8. **Vietnamese particle false positive that survived the gate** — the Ba Van Nguyen / HOAN BA NGUYEN match in 98052 (different humans, both probate-side surnames). The soft gate doesn't catch this; the shadow gate flags it as `insufficient_overlap`. Will be cleaned by promotion of that cohort if it happens.

9. **The trust v2 draft is salvageable as scaffolding.** Even though Jeremy rejected it as too rote, the substance (disposition vs. distribution-in-kind, basis mechanics, what a sale nets) is structurally correct and worth keeping as raw material for the agent-voice probate prompt. The voice was wrong, not the substance.

---

## Files created this session

### Production (committed, deployed)
- `backend/scoring/match_review.py` (new)
- `schema/013_match_review.sql` (new)
- `frontend/src/lib/sixLetters.js` (substantially refactored)

### Modified
- `backend/ingest/legal_filings.py`
- `backend/api/admin.py`
- `backend/api/briefings.py`
- `backend/selection/weekly_selector.py`
- `frontend/src/pages/BriefingPage.jsx`
- `frontend/src/components/briefing/PipelineList.jsx`
- `frontend/src/components/ParcelDossierV2.jsx`
- `frontend/src/lib/archetypePlaybooks.js`

### Drafts (NOT wired into production)
- `frontend/src/lib/sixLetters_probate_v2.js` — Jeremy approved
- `frontend/src/lib/sixLetters_trust_v2.js` — Jeremy rejected as too dense

### Schema applied
- `schema/013_match_review.sql` applied via Supabase SQL editor

---

## Things I (Claude) should not repeat next session

1. **Falsely claim a feature is missing without checking git log.** I almost rewrote the entire archetype-specific six-letter sequence before noticing commit `8864899` (by my own account) had already shipped it earlier in this session. The work fell out of context due to compaction. Always check `git log` for recent commits before assuming something needs to be built.

2. **Treat voice and substance as the same problem.** I produced the trust draft thinking I had voice-matched Jeremy's writing, but Jeremy correctly identified that voice without personality is just style. The substance was correct, the voice cadence was correct, but there was no agent in the letter. This led directly to the agent-voice product realization. **The lesson: writing for someone is different from writing in their voice. Both are needed.**

3. **Estimate timelines without thinking.** I called the agent-voice product a "multi-week effort." Jeremy correctly pushed back — kept tight, it's a 1-2 day v1. I tend to overestimate when I'm uncertain about scope; better to break the work into named milestones and estimate per-milestone.

4. **Volume-respond when the user is frustrated.** When Jeremy said "these are dense and inhuman," my instinct was to immediately try again. The right move (which I did, on the second beat) was to sit with the criticism and articulate what was actually wrong before drafting again.

---

## Recommended first actions for next session

1. Read this doc and the manifesto. Don't propose actions yet.
2. Verify production health: `curl -s https://sellersignal.co/api/health` and hit one or two briefing endpoints.
3. If Jeremy is starting on the agent-voice product: re-read the architecture section above and the prompt set. Ask before building the schema. Confirm v1 scope is the 5-step list.
4. If Jeremy wants to revisit any of the open questions above: pick one. Don't pick more than one per session. They all interact.
5. **Do not promote any more match-review cohorts without explicit Jeremy approval per cohort.** The shadow infrastructure is in place; the audit results are there to read. But trust continuity is the standing principle and surprise demotions are not OK.
