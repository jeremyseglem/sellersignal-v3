"""
Agent voice prompt construction.

The agent voice product turns each agent's voice/stance/bio into a
per-archetype outreach script (6-letter sequence + phone script + door
script). This module is the prompt layer — it has no I/O, no DB
dependencies, no Anthropic SDK dependency. Pure functions.

Two callers:
  - backend.api.admin.voice_smoketest_endpoint — passthrough endpoint
    used during prompt iteration, returns raw output for inspection.
  - backend.api.profile.generate_scripts_endpoint — the real endpoint,
    reads inputs from the authenticated user's agent_profiles_v3 row
    and writes results back.

Both pass through `build_voice_prompt(...)` to construct the user
prompt and `detect_banned_phrases(...)` to gate output quality.
"""
from __future__ import annotations
import re
from typing import Any


# ─── System prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are helping a real estate agent write seller outreach in their own voice.

Your job is not to create a polished marketing template.
Your job is to preserve the agent's actual tone, restraint, confidence, and way of speaking.

CRITICAL: Do not fall back to generic real-estate copywriting. The default LLM register for "thoughtful agent letter" is exactly what we are NOT trying to produce. If the output reads like it could have been written by any competent agent, you have failed. It must read like THIS agent — and only this agent — wrote it.

Three fidelity rules that override everything else:

1. CADENCE matters more than vocabulary. Read the voice sample carefully and mirror its sentence rhythm:
   - Match em-dash usage. If the sample uses em-dashes for clarifying or qualifying clauses, your output must too.
   - Match colon-after-setup constructions (e.g. "comes down to one thing: who's running the process").
   - Match the alternation between long, clause-stacked sentences and short flat ones. Short declarative sentences after longer ones land hard. Use them.
   - Match where the warmth lives. In some voices, warmth lives in the third beat after an em-dash. In others, it lives in a brief sign-off. Read the sample and match.

2. DISTINCTIVE PHRASES from the voice sample should appear VERBATIM somewhere in the output, not paraphrased. If the sample says "That's your decision, on your timeline" — use that exact phrase, do not rewrite it as "the timing is yours" or "it's your call." The agent's signature moves are the most important voice signal.

3. NO TWIN SENTIMENTALITY. The default LLM warmth pattern is to pair two sentimental statements: "I hope X. I hope Y." or "I want you to know X. I want you to know Y." or "If you sold, I hope it went smoothly. If you held it, I hope it brings peace." This is a dead giveaway. The agent's voice produces ONE controlled sentence of warmth at most, then returns to substance. Never pair warmth statements. If you find yourself writing a second "I hope..." — delete the first and rewrite without either.

BANNED PHRASES — these are dead giveaways of LLM house style. Any of these appearing in your output will fail the fidelity bar:
- "I'd be honored" / "honored to" / "honored by"
- "I'd welcome the chance" / "I'd welcome the opportunity" / "welcome the opportunity to"
- "I'd love to" / "would love to"
- "navigating" (as in "navigating decisions" or "navigating a transition")
- "I hope this finds you well"
- "weight of both" / "weight of this" / similar sentimental abstraction
- "during this difficult time" / "in this difficult time"
- "if it ever does" / "if it ever comes" (corny redundancy after a conditional)
- "I understand how complex this process can be" / "I understand how difficult"
- "I want you to know that..." / "I just want you to know..."
- "I just wanted to make sure you knew" (wordy hedge)
- "Please don't hesitate to..." (formal cliche)
- "I hope it brings" / "I hope it brings peace" / "brings the family peace"
- "I hope it went smoothly"
- Any sentence beginning with "Whether you..." or "Whether that's..." (LLM tic)
- "I imagine you've made" (presumptuous LLM warmth)
- "respects your timeline" / "respects your process" (corporate)
- Adjective stacking for warmth: "genuine," "heartfelt," "sincere," "thoughtful" used as filler

Other rules:
- Sound like the agent, not like a copywriter.
- Avoid salesy language.
- Avoid pressure.
- Avoid overexplaining.
- Do not invent credentials, statistics, or personal claims.
- Use plain words. Complexity comes from sentence structure, not vocabulary.
- If you are tempted to add an adjective for warmth, don't. The structure does the work; adjectives drain it.
- Sign-offs that do warmth work the body should be doing ("Warm regards," "With sincere gratitude") are forbidden. End on the actual point or a flat closer."""


# ─── Archetype context (the situational priming for each lead type) ──

ARCHETYPE_CONTEXT: dict[str, str] = {
    'probate': """The recipient is the personal representative of an estate after a death — a family member (often spouse, adult child, or sibling) who has been appointed by the court to administer the deceased's affairs. They are dealing with grief AND administrative complexity simultaneously. The property may need to be sold, transferred to a beneficiary, or held; that decision belongs to the family on their timeline. The agent should NOT pressure, NOT assume the property will be sold, and NOT address the deceased.""",

    'divorce': """The recipient is an owner navigating a divorce or asset division. The property may be subject to a settlement decision. This requires extreme discretion — the agent must NOT mention divorce directly, MUST NOT imply the agent has private knowledge of the situation, and should frame outreach around generic "property decisions during life transitions" without specifying what kind. The owner may not yet have decided whether to sell.""",

    'investor': """The recipient is an institutional or investor owner (often an LLC, trust holding investment property, or out-of-area individual). The property is held as an asset, not a primary residence. Conversation expectations are business-tone — disposition timing, cap rate, 1031 considerations, off-market opportunity. The owner is sophisticated; do not over-explain market basics.""",

    'trust': """The recipient is the trustee of a trust holding the property. The trustee may be the spouse, an adult child, a professional, or a family-elected representative. The decision about the property is FIDUCIARY — made on behalf of beneficiaries, in coordination with counsel and accountants, on the trust's timeline. Tone should be respectful of fiduciary duty, institutional rather than personal.""",

    'longTenure': """The recipient is a long-time homeowner — typically 15+ years at the property — with no obvious distress signal or court filing. There is no urgent trigger. The goal is to start a relationship, not push for a listing. Tone should be soft, patient, locally credible. Avoid 'your home is worth' hype. Do not assume they want to sell or that life events are imminent.""",

    'estateTransition': """The recipient is part of a family with a long-held property in a transition phase — multi-generational ownership, possible upcoming inheritance, or recent family changes that may affect the property. No court filing has occurred yet. Tone should be relational, family-aware, low-pressure.""",
}


ARCHETYPES: list[str] = list(ARCHETYPE_CONTEXT.keys())


# ─── Bio usage rules (verbatim block injected into user prompt) ──────

BIO_USAGE_RULES = """Bio material rules:

- The agent has provided background information. Use it ONLY when it connects organically to this specific lead's parcel, neighborhood, or situation.

- Most letters should NOT reference the agent's background at all. Default to silence on bio.

- When background is referenced, it should appear once, briefly, in service of the lead — never as preamble or self-introduction.

- NEVER force a connection that isn't there. "As a fellow Bellevue resident" only works when the lead is in Bellevue AND the agent has named Bellevue in their geographic_anchors.

- Bio material should NEVER reference the lead's personal details (their employer, their school, their family). Bio matches happen at the parcel/neighborhood level, not the person level.

- Affiliations (brokerage, boards, press) belong in letter 4 or letter 6 of a sequence, not letter 1."""


# ─── Stance defaults ─────────────────────────────────────────────────
# When an agent skips a stance question, these defaults apply. The
# defaults skew "soft / understated / wait-for-signal" because it's
# easier for an agent to ask for a more aggressive setting than to
# undo damage from a too-aggressive default.

STANCE_DEFAULTS: dict[str, str] = {
    'structural_acknowledgment': 'indirect',
    'first_contact_tempo': 'first',
    'first_letter_substance': 'relationship',
    'preferred_length': 'long_rare',
    'follow_up_posture': 'cadence',
    'price_voice': 'only_when_asked',
    'self_presentation': 'understated',
    'competitor_acknowledgment': 'dont_reference',
    'door_knock_posture': 'signal_required',
    'phone_posture': 'letter_first',
}


def stance_to_behavior(stance: dict | None) -> str:
    """Convert the stance vector into explicit behavioral instructions.
    The LLM sees the behavioral instructions, not the raw keys."""
    s = {**STANCE_DEFAULTS, **(stance or {})}
    lines = []

    sa = s.get('structural_acknowledgment')
    if sa == 'direct':
        lines.append('- It is acceptable to reference the situation explicitly (e.g., "I came across the probate filing"). The agent prefers being upfront about the source.')
    elif sa == 'indirect':
        lines.append('- Do not reference filings, court records, or the source of how the agent learned about this situation. Keep the source vague (e.g., "I work with families in this area").')
    else:
        lines.append('- The agent reads the situation case-by-case. Default to vague unless context strongly justifies being explicit.')

    tempo = s.get('first_contact_tempo')
    if tempo == 'first':
        lines.append('- This agent values being early. Tone of letter 1 is timely, not delayed or hesitant.')
    else:
        lines.append('- This agent prefers to come in late and quiet. Letter 1 should acknowledge the volume of cold outreach and position itself as different.')

    sub = s.get('first_letter_substance')
    if sub == 'substance':
        lines.append('- Lead with substance and market knowledge in early letters, not introduction or relationship.')
    else:
        lines.append('- Lead with introduction and relationship in early letters. Substance and market data appear in later letters (60+ days in).')

    length = s.get('preferred_length')
    if length == 'short_frequent':
        lines.append('- Letters should run SHORT — 3-5 sentences max per letter. Brevity is part of the voice.')
    else:
        lines.append('- Letters can run longer (5-12 sentences) — this agent prefers fewer, weightier touches over short frequent ones.')

    fu = s.get('follow_up_posture')
    if fu == 'cadence':
        lines.append('- Continue the cadence even without response. The full 6-letter sequence runs regardless of reply.')
    else:
        lines.append('- After 1-2 letters with no response, the sequence steps back. Letters 3-6 should reflect that posture (less frequent, more "standing offer" tone).')

    pv = s.get('price_voice')
    if pv == 'comfortable_early':
        lines.append('- The agent is comfortable referencing specific values, comps, or dollar figures in early letters where useful.')
    else:
        lines.append('- Avoid specific numbers, comps, or valuations unless the lead has explicitly asked. Substance comes through framing, not numbers, in cold outreach.')

    sp = s.get('self_presentation')
    if sp == 'direct':
        lines.append('- The agent will reference experience, transactions, and credentials directly when relevant to credibility.')
    else:
        lines.append("- Do not foreground the agent's experience or credentials. The work speaks. Letters should rarely reference the agent's background.")

    ca = s.get('competitor_acknowledgment')
    if ca == 'acknowledge':
        lines.append("- It is acceptable to acknowledge the agent's competition directly (e.g., \"if you've decided to work with someone else, that's fine\"). Naming the elephant builds trust.")
    else:
        lines.append('- Do not reference other agents or competing offers. Focus on what this agent brings.')

    dk = s.get('door_knock_posture')
    if dk == 'cold_open':
        lines.append('- Door scripts can assume the agent is comfortable cold-knocking. Default opener engages directly when someone answers.')
    else:
        lines.append('- Door scripts should default to leave-behind only — cards and notes left at the door, not active engagement, unless explicit signal indicates the recipient wants conversation.')

    pp = s.get('phone_posture')
    if pp == 'comfortable_cold':
        lines.append('- Phone scripts assume the agent is comfortable calling cold as the first touch.')
    else:
        lines.append('- Phone scripts default to letter-first posture: the call comes only after a letter, or only after the recipient has signaled willingness.')

    return '\n'.join(lines)


def format_bio(bio: dict | None) -> str:
    """Format bio dict into the prompt-block. Returns 'No bio provided.'
    when empty — the prompt rules already say to default to silence on
    bio, so empty just makes that explicit."""
    if not bio:
        return 'No bio provided.'

    parts = []

    bg = (bio.get('background') or '').strip()
    if bg:
        parts.append(f'Background:\n{bg}')

    anchors = bio.get('geographic_anchors') or []
    if anchors:
        anchor_lines = []
        for a in anchors:
            if isinstance(a, dict):
                n = (a.get('neighborhood') or '').strip()
                r = (a.get('relationship') or '').strip()
                if n and r:
                    anchor_lines.append(f'- {n}: {r}')
                elif n:
                    anchor_lines.append(f'- {n}')
        if anchor_lines:
            parts.append('Geographic anchors:\n' + '\n'.join(anchor_lines))

    aff = (bio.get('affiliations') or '').strip()
    if aff:
        parts.append(f'Affiliations:\n{aff}')

    if not parts:
        return 'No bio provided.'
    return '\n\n'.join(parts)


def build_voice_prompt(voice_sample: str | None, stance: dict | None,
                       bio: dict | None, archetype: str) -> str:
    """Construct the per-archetype user prompt."""
    if archetype not in ARCHETYPE_CONTEXT:
        raise ValueError(f"unknown archetype: {archetype}")

    archetype_context = ARCHETYPE_CONTEXT[archetype]
    behavior = stance_to_behavior(stance)
    bio_block = format_bio(bio)
    voice_block = (voice_sample or '').strip() or '(No voice sample provided — use a neutral, measured, professional voice as a default.)'

    return f"""Here is how this agent communicates:

{voice_block}

Behavioral implications for this agent (apply these strictly):
{behavior}

Agent bio (use only when organically relevant to the lead's parcel or neighborhood):

{bio_block}

{BIO_USAGE_RULES}

Now write this agent's outreach for the following situation:

Archetype: {archetype}

Context:
{archetype_context}

Write the full outreach package as a JSON object with these keys:

{{
  "letter_sequence": [
    {{ "day": 1,   "title": "...", "body": "..." }},
    {{ "day": 30,  "title": "...", "body": "..." }},
    {{ "day": 60,  "title": "...", "body": "..." }},
    {{ "day": 90,  "title": "...", "body": "..." }},
    {{ "day": 135, "title": "...", "body": "..." }},
    {{ "day": 180, "title": "...", "body": "..." }}
  ],
  "phone_script": "...",
  "door_script": "..."
}}

Use these placeholder tokens for lead-specific details (they will be substituted at render time):
- [PROPERTY_ADDRESS]
- [NEIGHBORHOOD]
- [RECIPIENT_NAME]   (the personal representative for probate, the trustee for trust, the owner for others)
- [DECEDENT_NAME]    (probate only — the name of the deceased)
- [AGENT_NAME]       (the agent's signature)

Phone script formatting: include "BEFORE YOU CALL" / "OPENER" / "REASON" / "LIKELY REACTIONS" (with 3 reaction branches: send-info / not-interested / busy) / "GRACEFUL EXIT" / "AFTER THE CALL" sections. The agent's spoken lines should be marked "YOU:".

Door script formatting: include "BEFORE YOU KNOCK — JUDGMENT CALL" (with at least 2-3 specific situational rules: when to knock, when to leave a card without knocking) / "OPENER" / "LIKELY REACTIONS" / "LEAVE-BEHIND" sections.

Output only the JSON object. No preamble, no markdown fence."""


# ─── Banned-phrase enforcement ───────────────────────────────────────

_BANNED_REGEXES: list[str] = [
    r"\bI'd be honored\b",
    r"\bhonored to\b",
    r"\bI'd welcome the (chance|opportunity)\b",
    r"\bwelcome the opportunity\b",
    r"\bI'd love to\b",
    r"\bwould love to\b",
    r"\bnavigating\b",
    r"I hope this finds you well",
    r"\bweight of (both|this)\b",
    r"\bduring this difficult time\b",
    r"\bin this difficult time\b",
    r"\bif it ever does\b",
    r"\bif it ever comes\b",
    r"I understand how (complex|difficult)",
    r"\bI want you to know that\b",
    r"\bI just want(ed)? to (make sure|let you know)\b",
    r"\bPlease don't hesitate\b",
    r"I hope it brings",
    r"I hope it went smoothly",
    r"^\s*Whether (you|that|that's|this)\b",
    r"\bI imagine you've made\b",
    r"\brespects your timeline\b",
    r"\brespects your process\b",
]


def detect_banned_phrases(text: str) -> list[str]:
    """Return list of banned-phrase regex patterns that matched."""
    hits = []
    for pat in _BANNED_REGEXES:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            hits.append(pat)
    return hits


def banned_retry_message(violations: list[str]) -> str:
    """Construct the retry user message that names the specific
    violations and asks for a rewrite."""
    return (
        "Your previous output violated the BANNED PHRASES rule. "
        "Specifically, these patterns appeared and must not:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nRewrite the entire output. Same JSON structure, same "
          "lead-specific token placeholders, same archetype context — "
          "but do not use any of the patterns above. Replace each "
          "with phrasing that fits the agent's actual cadence (em-dash, "
          "short flat sentences after long ones, no twin sentimentality, "
          "no LLM warmth tells). Output only the JSON object."
    )


# ─── End-to-end generation helper ────────────────────────────────────

def generate_archetype_script(client: Any, voice_sample: str | None,
                              stance: dict | None, bio: dict | None,
                              archetype: str,
                              max_tokens: int = 4000) -> dict:
    """Generate one archetype's full output package. Runs the prompt,
    detects banned phrases, retries once if needed, parses JSON.

    Returns:
      {
        'archetype': str,
        'parsed':   dict | None,        # parsed JSON if it parsed, else None
        'final_output': str,             # the chosen output text
        'first_attempt_violations': list[str],
        'retry_violations': list[str] | None,
        'used_retry': bool,
        'tokens_in': int,
        'tokens_out': int,
        'retry_tokens_in': int | None,
        'retry_tokens_out': int | None,
      }

    Caller is responsible for the Anthropic client. Raises whatever
    the SDK raises on API errors.
    """
    user_prompt = build_voice_prompt(voice_sample, stance, bio, archetype)

    resp = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    raw_output = resp.content[0].text if resp.content else ''
    tokens_in = getattr(resp.usage, 'input_tokens', None)
    tokens_out = getattr(resp.usage, 'output_tokens', None)

    violations = detect_banned_phrases(raw_output)
    retry_output = None
    retry_violations = None
    retry_tokens_in = None
    retry_tokens_out = None
    if violations:
        try:
            retry_resp = client.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {'role': 'user', 'content': user_prompt},
                    {'role': 'assistant', 'content': raw_output},
                    {'role': 'user', 'content': banned_retry_message(violations)},
                ],
            )
            retry_output = retry_resp.content[0].text if retry_resp.content else ''
            retry_violations = detect_banned_phrases(retry_output)
            retry_tokens_in = getattr(retry_resp.usage, 'input_tokens', None)
            retry_tokens_out = getattr(retry_resp.usage, 'output_tokens', None)
        except Exception:
            retry_output = None

    final_output = retry_output if (
        retry_output is not None
        and retry_violations is not None
        and len(retry_violations) < len(violations)
    ) else raw_output
    used_retry = final_output is retry_output

    parsed = None
    try:
        import json as _json
        clean = final_output.strip()
        if clean.startswith('```'):
            lines = clean.split('\n')
            if lines[0].startswith('```'): lines = lines[1:]
            if lines and lines[-1].strip() == '```': lines = lines[:-1]
            clean = '\n'.join(lines)
        parsed = _json.loads(clean)
    except Exception:
        parsed = None

    return {
        'archetype': archetype,
        'parsed': parsed,
        'final_output': final_output,
        'first_attempt_violations': violations,
        'retry_violations': retry_violations,
        'used_retry': used_retry,
        'tokens_in': tokens_in,
        'tokens_out': tokens_out,
        'retry_tokens_in': retry_tokens_in,
        'retry_tokens_out': retry_tokens_out,
    }
