# Agent Voice — V1 Spec

**Status:** Spec for review. No code yet.
**Date:** May 2, 2026
**Author:** Claude (in session with Jeremy)

---

## What this is

V1 of the agent-voice-driven outreach generation system. Converts SellerSignal from "tool that gives you leads with templates" into "tool that gives you leads with letters / phone scripts / door scripts in **your** voice, addressed to **this** lead, drawing on **your** background where relevant."

This is the differentiator. Two agents looking at the same probate lead get materially different outreach because they would actually approach that family differently in real life.

---

## Architecture (final)

```
agent_profile = {
  identity:      (already exists — full_name, brokerage, headshot, etc.)
  voice_sample:  one paragraph free text OR one pasted real letter
  stance:        10 forced-choice behavioral dimensions
  bio:           background, geographic_anchors, affiliations
  generated_scripts: { archetype → script } — populated once at onboarding
}
```

**Key principle:** generation runs ONCE per agent per archetype at onboarding (~6 LLM calls total). Lead-level rendering is token substitution only, no per-lead LLM. This keeps costs predictable and outputs stable.

---

## Schema changes

Migration 014 extends the existing `agent_profiles_v3` table. **Does NOT create a new table.** The existing table already has identity, brokerage, license, etc. We add:

```sql
ALTER TABLE agent_profiles_v3
    -- Voice sample: agent's own writing, used to teach the LLM how
    -- they sound on the page. Free text. May be a paragraph
    -- describing how they communicate, or one pasted real letter
    -- they've actually sent.
    ADD COLUMN IF NOT EXISTS voice_sample TEXT,

    -- Stance vector: 10 forced-choice behavioral dimensions stored
    -- as a JSON object. See "Stance questions" section below for
    -- the exact keys, allowed values, and meaning of each.
    -- Default {} when agent hasn't completed onboarding.
    ADD COLUMN IF NOT EXISTS stance JSONB DEFAULT '{}'::jsonb,

    -- Bio: background, geographic_anchors, affiliations. Used by
    -- the LLM as STANDBY context — drawn on only when an organic
    -- hook exists in the lead's parcel/neighborhood. See "Bio
    -- usage rules" below for the prompt guardrails. Default {}.
    ADD COLUMN IF NOT EXISTS bio JSONB DEFAULT '{}'::jsonb,

    -- Generated scripts: one per archetype, populated at onboarding
    -- via 5-6 LLM calls. Lead-level rendering injects parcel/lead
    -- specifics into these stored strings via token substitution.
    -- Default {}.
    ADD COLUMN IF NOT EXISTS generated_scripts JSONB DEFAULT '{}'::jsonb,

    -- Onboarding sub-state: did the agent complete the voice/stance/
    -- bio onboarding (separate from the existing onboarding_completed_at
    -- which tracked identity-only setup). Null until voice onboarding
    -- is finished.
    ADD COLUMN IF NOT EXISTS voice_onboarding_completed_at TIMESTAMPTZ;
```

All columns are nullable / default-empty. Existing rows are unaffected. Existing RLS policies on the table cover the new columns automatically.

---

## Voice sample input

**One field, free text, ~200 to ~1500 characters.** Either of:

1. A paragraph describing how the agent communicates with sellers ("I tend to be direct but never pushy. I write the way I'd talk if we were sitting in their kitchen. I avoid jargon and I don't try to sound like a brochure.")

2. A pasted real letter or email the agent has actually sent — preferable when available, since real text carries cadence the LLM can match.

Onboarding UI prompt:
> "Tell us how you sound when you write to a seller. You can describe your style in your own words, or paste a real letter you've sent — whichever is easier. Either way, this is what teaches the system how you sound on the page."

Optional click-to-expand helper sub-prompts:
- "Are you more direct or relationship-first?"
- "Do you focus on speed, discretion, or price?"
- "What do clients usually say about your style?"

---

## Stance questions

Ten forced-choice behavioral dimensions. Each maps to a clear behavioral signal the prompt can use deterministically. **No 1-5 scales — those produce noise.** Binary or ternary only.

For each: the question text shown to the agent, the allowed values, and what the value means in the prompt.

### 1. structural_acknowledgment
> When you reach out to a probate family or a divorce-affected owner, do you mention the situation directly?

- `direct` — "It's fine to say 'I came across the probate filing' or similar. I prefer being upfront."
- `indirect` — "I keep the source vague. Something like 'I work with families navigating decisions about a home.'"
- `it_depends` — "I read the situation. Depends on the family."

**Default:** `indirect` (safer floor).

### 2. first_contact_tempo
> When a new probate or divorce lead surfaces, do you want to be the first letter in their mailbox or come in later?

- `first` — "I want to be early. Speed matters."
- `late` — "I'd rather come in quiet, after the volume of other cold outreach has died down."

**Default:** `first`.

### 3. first_letter_substance
> Do your early letters lead with substance (market, comps, value) or with relationship (introduction, who I am, why I'm reaching out)?

- `substance` — "I lead with what I know about their situation and the market. The value is in the information."
- `relationship` — "I lead with introducing myself. The first letter isn't about the deal."

**Default:** `relationship`.

### 4. preferred_length
> Do your letters tend to run short and frequent, or longer and rarer?

- `short_frequent` — "Brief letters, more often."
- `long_rare` — "Longer letters, fewer of them."

**Default:** `long_rare`.

### 5. follow_up_posture
> If you don't hear back, do you keep writing on cadence or step away?

- `cadence` — "I keep writing until the sequence ends, regardless of whether they respond."
- `wait_for_signal` — "I write once or twice and stop unless they signal back."

**Default:** `cadence`.

### 6. price_voice
> Are you comfortable referencing specific values, comps, or numbers in early letters?

- `comfortable_early` — "Yes — naming a number is part of being useful."
- `only_when_asked` — "I avoid numbers in cold outreach. Save those for after they've engaged."

**Default:** `only_when_asked`.

### 7. self_presentation
> When you talk about your experience, do you reference it directly or let the work speak?

- `direct` — "I'll mention years in the market, notable transactions, my brokerage. It's relevant to credibility."
- `understated` — "I let the substance of the letter do the work. I rarely talk about myself."

**Default:** `understated`.

### 8. competitor_acknowledgment
> Are you willing to acknowledge other agents directly in your letters (e.g. "if you've decided to work with someone else, that's fine")?

- `acknowledge` — "Yes. Naming the elephant builds trust."
- `dont_reference` — "No. I focus on what I bring; I don't reference competitors."

**Default:** `dont_reference`.

### 9. door_knock_posture
> Are you comfortable cold-knocking on doors, or do you only knock after explicit signal?

- `cold_open` — "Yes, I'll go to the door cold. It's part of the job."
- `signal_required` — "I only knock if I have a real reason to be there. Otherwise leave a card."

**Default:** `signal_required`.

### 10. phone_posture
> Do you prefer cold-calling or letter-first?

- `comfortable_cold` — "I'll pick up the phone first. I think it's more direct."
- `letter_first` — "I prefer to write first and call only after they've responded or engaged."

**Default:** `letter_first`.

### How stance values plug into the generation prompt

The prompt receives the stance vector as a structured block. The LLM is given EXPLICIT behavioral instructions tied to each value, not asked to infer:

```
Agent stance:
- structural_acknowledgment: indirect
- first_contact_tempo: first
- first_letter_substance: relationship
- preferred_length: long_rare
- follow_up_posture: cadence
- price_voice: only_when_asked
- self_presentation: understated
- competitor_acknowledgment: acknowledge
- door_knock_posture: signal_required
- phone_posture: letter_first

Behavioral implications for this agent:
- Do not reference filings or records directly. Keep source vague.
- Lead with introduction and relationship in early letters,
  not substance or market data.
- Letters can run longer (5-10 sentences) — this agent prefers
  fewer, weightier touches over short frequent ones.
- Continue the cadence even without response — six letters total.
- Avoid specific numbers, comps, or valuations unless the lead
  asks for them.
- Do not foreground the agent's experience or credentials.
- It is acceptable to acknowledge the agent's competition directly
  ("if you've decided to work with someone else, that's fine").
- Phone scripts default to letter-first: "I prefer to write first."
- Door scripts default to leave-behind only.
```

This conversion (stance → behavioral instructions) happens server-side. The LLM never sees the raw stance keys.

---

## Bio schema

Three sub-fields. All free-text-but-bounded. All optional.

```typescript
bio: {
  background: string,
  // ~200-1000 chars. Where you're from, how you got into real
  // estate, career before real estate, schools, languages,
  // markets you've worked. Used by the LLM ONLY when an organic
  // hook to the lead exists.

  geographic_anchors: Array<{
    neighborhood: string,
    relationship: string,
  }>,
  // ~3-8 entries. Examples:
  //   { neighborhood: "Bridle Trails, Bellevue", relationship: "live here since 2019" }
  //   { neighborhood: "Mercer Island", relationship: "specialize in waterfront" }
  // The LLM uses these when the lead's parcel is in a named
  // neighborhood. Otherwise ignored.

  affiliations: string,
  // ~200-1000 chars. Brokerage details, notable transactions,
  // boards, community organizations, press coverage. Used in
  // letter 4 (direct offer) or letter 6 (standing offer), not
  // early relationship-building letters.
}
```

### Bio usage rules (prompt guardrails)

These appear verbatim in the system prompt:

```
Bio material rules:

- The agent has provided background information. Use it ONLY when
  it connects organically to this specific lead's parcel,
  neighborhood, or situation.

- Most letters should NOT reference the agent's background at all.
  Default to silence on bio.

- When background is referenced, it should appear once, briefly,
  in service of the lead — never as preamble or self-introduction.

- NEVER force a connection that isn't there. "As a fellow Bellevue
  resident" only works when the lead is in Bellevue AND the agent
  has named Bellevue in their geographic_anchors.

- Bio material should NEVER reference the lead's personal details
  (their employer, their school, their family). Bio matches happen
  at the parcel/neighborhood level, not the person level.

- Affiliations (brokerage, boards, press) belong in letter 4 or
  letter 6 of a sequence, not letter 1.
```

---

## Onboarding flow

**Single screen, four sections, top to bottom:**

1. **Voice sample** — one large textarea. Helper prompts on click.
2. **Stance** — 10 questions, radio buttons or pill selectors. Show all 10 on the screen, no multi-step wizard.
3. **Background** — `bio.background` textarea.
4. **Geographic anchors** — repeatable rows (`+ Add neighborhood`). Each row: neighborhood text input + relationship text input.
5. **Affiliations** — `bio.affiliations` textarea.

Submit button: "Generate my outreach scripts." On submit:
- Save profile to DB.
- Trigger generation endpoint.
- Show loading state ("Generating six archetype scripts — about 30 seconds…").
- On completion, redirect to a preview screen showing the 6 generated scripts side-by-side with archetype labels.

**Estimated agent time:** 8-12 minutes for thorough fill, 4-5 minutes for minimum-viable.

**Skipping is OK:**
- Skip stance → defaults from spec above are used.
- Skip bio → no bio material appears in any letter.
- Skip voice sample → falls back to default voice (Jeremy's voice as captured in `sixLetters_probate_v2.js` for now). The agent will get a system-default voice but with their stance/bio applied.

---

## Generation endpoint

`POST /api/agent/generate-scripts`

**Auth:** requires authenticated user. Operates on the calling user's `agent_profiles_v3` row only.

**Behavior:**
1. Read voice_sample, stance, bio from the user's profile.
2. For each of 6 archetypes (probate, divorce, investor, trust, longTenure, estateTransition), construct a prompt and call Anthropic.
3. Run the 6 calls in parallel.
4. Store results in `agent_profiles_v3.generated_scripts` as a JSON object: `{ probate: "...", divorce: "...", ... }`.
5. Set `voice_onboarding_completed_at = NOW()`.
6. Return the generated scripts to the client.

**Cost estimate:** 6 calls × ~3000 input tokens × ~800 output tokens at Sonnet 4.6 prices = roughly $0.05-0.08 per agent onboarding. One-time cost.

**Error handling:** if any of the 6 calls fail, return what succeeded and mark which failed. Agent can retry just the failed ones via `POST /api/agent/regenerate-script?archetype=probate`.

---

## Per-archetype prompt structure

Same system prompt across all archetypes:

```
You are helping a real estate agent write seller outreach in their own voice.

Your job is not to create a polished marketing template.
Your job is to preserve the agent's actual tone, restraint, confidence, and way of speaking.

Rules:
- Sound like the agent, not like a copywriter.
- Avoid salesy language.
- Avoid "I hope this finds you well."
- Avoid pressure.
- Avoid overexplaining.
- Do not invent credentials, statistics, or personal claims.
- Use plain language.
- The message should feel human, specific, and appropriate to the situation.
```

User prompt (per archetype):

```
Here is how this agent communicates:

[VOICE SAMPLE]

Agent stance:
[STANCE BLOCK rendered as behavioral implications — see "How stance values plug into the generation prompt" section above]

Agent bio (use only when organically relevant — see rules below):

Background:
[BIO.BACKGROUND]

Geographic anchors:
- [neighborhood]: [relationship]
- [neighborhood]: [relationship]

Affiliations:
[BIO.AFFILIATIONS]

Bio material rules:
[VERBATIM RULES from "Bio usage rules" section above]

Now write this agent's outreach for the following situation:

Archetype: [probate / divorce / investor / trust / longTenure / estateTransition]

Context:
[archetype-specific context paragraph — see /docs/SESSION_END_2026-05-01.md
 "Per-archetype user prompts" section for the per-archetype context]

Write the letter sequence as 6 letters labeled Day 1, Day 30, Day 60,
Day 90, Day 135, Day 180. Use [PROPERTY_ADDRESS], [NEIGHBORHOOD], and
[RECIPIENT_NAME] as placeholders for lead-specific details — those
will be substituted at render time, not now.

Output as JSON:
{
  "letter_sequence": [
    { "day": 1, "title": "...", "body": "..." },
    { "day": 30, "title": "...", "body": "..." },
    ...
  ],
  "phone_script": "...",
  "door_script": "..."
}
```

---

## Lead-level rendering

When a dossier is opened for a lead, the frontend:
1. Loads the agent's `generated_scripts[archetype]` for the lead's archetype.
2. Substitutes lead-specific tokens:
   - `[PROPERTY_ADDRESS]` → parcel.address
   - `[NEIGHBORHOOD]` → parcel.city or neighborhood
   - `[RECIPIENT_NAME]` → personal_representative.name_first (probate), trust title (trust), owner_name (others) — same logic as today's `resolveDefaultScripts`
3. Renders the letter sequence in the dossier's "Your approach" section (renamed from "What to say").
4. Renders phone script in the Phone tab, door script in the Door tab.

**No per-lead LLM call.** Pure substitution.

---

## Fallback behavior

If `agent_profiles_v3.generated_scripts` is empty (agent hasn't completed voice onboarding) → fall back to `archetypePlaybooks.js.defaultScripts` (the work shipped May 1) AND show a banner above the dossier scripts: "These are system defaults. Set up your voice profile to make these yours." with a button to the onboarding page.

---

## What's NOT in v1

- Per-lead voice override (e.g. "I know this family personally, write differently for this one")
- Multiple voice profiles per agent (e.g. different voice for divorce vs. probate)
- A/B testing different stance configurations
- Auto-extraction of voice from real sent emails / Outlook integration
- Stance learning from outcomes (which letters got responses)
- Bio extraction from LinkedIn or website upload
- Agent-uploaded headshot/letterhead integration into generated scripts

All deferred to v2 or later.

---

## Open questions before build

1. **Default voice when agent skips voice sample.** The spec says "fall back to Jeremy's voice." Is that actually what we want, or should the default be a more neutral/anonymous voice? Different agents starting from "the Jeremy default" might find it harder to override than starting from a blank canvas. **Recommend:** create a "neutral default voice" sample that's competent but characterless, separate from any specific agent's voice. Use that as the fallback. Costs maybe 30 minutes of careful drafting.

2. **Voice sample minimum length.** If an agent pastes 50 characters, can we generate well? Probably no. Should we require a minimum 200 chars before allowing submit? **Recommend:** soft-warn at <200 chars ("Add a bit more for better results") but allow submit. Don't block.

3. **Regeneration cost.** If an agent edits their voice/stance/bio after initial generation, do all 6 archetype scripts regenerate automatically? Each edit = $0.05-0.08. Could add up. **Recommend:** show a "Your voice profile changed. Regenerate scripts?" CTA after edits, don't auto-regenerate.

4. **Trustee name extraction (carryover from session 2026-05-01).** Trust archetype scripts use `[TRUSTEE_NAME]` as a token. Today the data we have is the trust title (e.g. "Coday Margaret Gold Trust"), no extracted current trustee. **Recommend:** for v1, leave the placeholder as-is and let the agent fill it in by hand on the call. Build trustee extraction in v2.

5. **Should onboarding be required to use the product, or optional?** If required, every signup hits the 8-12 minute setup before they can see leads. If optional, many agents will skip and get system defaults forever. **Recommend:** required, but with a "Skip for now (use system defaults)" option that's deliberately friction-y. Track skip rate and revisit.

---

## Recommended build order

1. **Migration 014** — schema columns. Safe, deterministic.
2. **Backend `POST /api/agent/generate-scripts`** — endpoint logic, prompt construction, Anthropic call, storage.
3. **Backend extension to `PUT /api/profile`** — accept the new fields (voice_sample, stance, bio).
4. **Smoke test from the command line** — manually populate a test agent's profile via PUT, call the generate endpoint, eyeball output. **Decision point: if output isn't clearly "in voice and matched to stance," stop and revisit prompt construction before building UI.**
5. **Frontend onboarding page** — single-screen form per the flow above.
6. **Frontend dossier integration** — read `generated_scripts` when present, substitute tokens, render. Keep `defaultScripts` as fallback.
7. **End-to-end test with Jeremy's profile** — fill in real voice sample (Broken Americana excerpt + Agency letter), real stance, real bio. Generate. Read all 6 scripts. Iterate.

---

## What gets done in this session vs. next

**This session (Saturday morning):**
- Lock this spec (you read, react, we adjust)
- Step 1: migration 014 (5 minutes)
- Step 2: backend generate-scripts endpoint (45-60 minutes)
- Step 3: extend PUT /api/profile (15 minutes)
- Step 4: smoke test (15 minutes)

**That's the decision point.** If smoke test output is good, push forward. If not, stop and revise. Either way, frontend work waits for next session.

**Next session:**
- Frontend onboarding page
- Frontend dossier integration
- End-to-end test
