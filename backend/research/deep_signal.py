"""
Deep Signal engine — generates grounded psychological profile + outreach
scripts for an investigated parcel.

Ports the CRITICAL DATA HONESTY RULES prompt from the Node.js production
site (see sellersignal/server.js:3610). Uses Claude Sonnet 4 because the
script quality drops noticeably on Haiku for this task.

Flow:
    1. Read parcel + investigation rows from Supabase
    2. Build research block from investigation.signals (already categorized)
    3. Call Claude Sonnet with strict grounding prompt
    4. Parse JSON response
    5. Cache in deep_signals_v3 keyed by pin
    6. Return structured payload

Cache policy: first call synthesizes (~3s, ~$0.02). Subsequent calls for
the same pin return the cached row instantly.

Unlike the Node.js version, v3 does NOT do its own noise filtering. The
investigation pipeline already produces category-clean signals with
trust levels — we trust that upstream filtering rather than re-running it.
"""
from __future__ import annotations

import json
import re
from typing import Optional

MODEL = 'claude-sonnet-4-20250514'
MAX_TOKENS = 2500
TIMEOUT_SECONDS = 30

# ── Prompt: ported from Node.js server.js with minor cleanups ──────────
# The grounding rules below are the exact rules that prevent fabrication.
# Do not soften them without checking real outputs — they're the reason
# v3 doesn't hallucinate "her 25-year UW dental career."
SYSTEM_PROMPT = """You are SellerSignal's Deep Signal engine. You produce grounded psychological profiles and outreach strategies for real estate prospects.

CRITICAL DATA HONESTY RULES:
1. GROUND every claim in the VERIFIED RESEARCH block. Reference specific findings by exact phrasing. If the research says "Retirement indicators in public records", say "public records suggest recent retirement" — not "she's contemplating life changes."
2. DO NOT fabricate occupations, degrees, universities, company names, titles, or personal history that aren't explicitly in the research. If you don't see it in VERIFIED RESEARCH, it doesn't exist for this person.
3. DO NOT invent specifics. Phrases like "his University of Washington dental background", "his role as CEO of [company]", "her 25-year career at [firm]" are FABRICATIONS unless those exact facts appear in the research. Prefer vague-but-honest ("the owner's professional background") over specific-but-fabricated.
4. Cohort-only prospects (trust + absentee + long tenure with no life events) deserve honest acknowledgment. Say "limited public research surface — analysis based on ownership structure alone" and write generic but respectful scripts. DO NOT invent life events to fill narrative space.
5. Entity-owned parcels (LLC, Trust, Company) require institutional voice — address the entity, don't invent individuals.

OUTPUT FORMAT:
Respond with ONLY a JSON object (no array, no code fence). Keys:
{
  "motivation":       "3-5 sentences grounded STRICTLY in the VERIFIED RESEARCH block. Reference at least 2 specific findings by name. If research is thin, say so honestly.",
  "timeline":         "0-3 months | 3-6 months | 6-12 months | 12+ months",
  "best_channel":     "call | mail | door",
  "call_script":      "Full 4-6 sentence phone script. Reference specific verified findings naturally. No fabrication.",
  "mail_script":      "Full 4-6 sentence letter. Same grounding rules.",
  "door_script":      "Full 4-6 sentence door knock. Same grounding rules.",
  "what_not_to_say":  "2-3 specific things to avoid, tied to what research actually reveals. Not generic 'do not be pushy.'",
  "research_grounded": true
}"""


# ──────────────────────────────────────────────────────────────────────
# Research block construction
# ──────────────────────────────────────────────────────────────────────
def _build_research_block(parcel: dict, investigation: dict) -> tuple[str, bool]:
    """
    Assemble a VERIFIED RESEARCH text block from investigation signals.

    Returns (text, has_substance). has_substance is False when the only
    evidence is structural cohort data — caller can decide whether to
    synthesize anyway or return a thin response.
    """
    signals = (investigation or {}).get('signals') or []

    # Group by category — matches the v3 signal categorization
    life_events = [s for s in signals if s.get('category') == 'life_event']
    listings    = [s for s in signals if s.get('category') == 'listing']
    identity    = [s for s in signals if s.get('category') == 'identity']
    financial   = [s for s in signals if s.get('category') == 'financial']
    other       = [s for s in signals
                   if s.get('category') not in
                   ('life_event', 'listing', 'identity', 'financial')]

    sections: list[str] = []

    if life_events:
        lines = [
            f"  - {s.get('type', '?')}: {s.get('detail', '')} ({s.get('trust', 'medium')} trust)"
            for s in life_events
        ]
        sections.append("  LIFE EVENTS:\n" + "\n".join(lines))

    if listings:
        lines = [
            f"  - {s.get('type', '?')}: {s.get('detail', '')} ({s.get('trust', 'medium')} trust)"
            for s in listings
        ]
        sections.append("  LISTING HISTORY:\n" + "\n".join(lines))

    if financial:
        lines = [
            f"  ⚠ {s.get('detail', '')} ({s.get('trust', 'medium')} trust)"
            for s in financial
        ]
        sections.append("  FINANCIAL / RISK SIGNALS:\n" + "\n".join(lines))

    if identity:
        lines = [
            f"  - {s.get('detail', '')} ({s.get('trust', 'medium')} trust)"
            for s in identity
        ]
        sections.append("  WHO THEY ARE:\n" + "\n".join(lines))

    if other:
        lines = [
            f"  - {s.get('type', '?')}: {s.get('detail', '')}"
            for s in other
        ]
        sections.append("  OTHER SIGNALS:\n" + "\n".join(lines))

    research = "\n".join(sections).strip()
    has_substance = bool(life_events or financial or identity or listings)
    return research, has_substance


def _build_prompt(parcel: dict, investigation: dict) -> str:
    """Construct the full user-message prompt."""
    research, has_substance = _build_research_block(parcel, investigation)

    # Structural cohort / rank info — always present
    owner = parcel.get('owner_name') or parcel.get('owner_name_raw') or '?'
    addr = parcel.get('address') or '?'
    city = parcel.get('city') or ''
    state = parcel.get('state') or ''
    value = parcel.get('total_value') or 0
    value_str = f"${value:,}" if value else '?'
    tenure = parcel.get('tenure_years')
    tenure_str = f"{tenure:.0f}yr" if tenure is not None else '?'
    mail_addr = parcel.get('owner_address') or '?'
    cohort = parcel.get('signal_family') or '?'
    owner_type = parcel.get('owner_type') or 'unknown'

    # Action reason: what the pressure engine concluded from the evidence
    action_reason = (investigation or {}).get('action_reason', '')
    action_category = (investigation or {}).get('action_category', '')

    prompt_section = f"""[1] {owner} — {addr}, {city} {state}
  Owner type: {owner_type} | Cohort: {cohort} | Assessed: {value_str}
  Tenure: {tenure_str} | Mail address: {mail_addr}
  Scored as: {action_category} ({action_reason})

  VERIFIED RESEARCH (noise-filtered, only category-clean signals):
{research if has_substance else '  (limited — ownership structure and cohort only, no life events or financial signals found)'}"""

    return f"""CRITICAL DATA HONESTY RULES (repeated for emphasis):
- GROUND every claim in VERIFIED RESEARCH below. Reference specific findings by exact phrasing.
- DO NOT fabricate occupations, companies, titles, or personal history absent from the research.
- Trust-owned or LLC-owned parcels use institutional voice, not invented individual names.

PROSPECT:
{prompt_section}
"""


# ──────────────────────────────────────────────────────────────────────
# Response parsing
# ──────────────────────────────────────────────────────────────────────
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_response(text: str) -> dict:
    """Strip optional markdown fences, then parse as JSON."""
    clean = _JSON_FENCE.sub('', text).strip()
    # If the model emitted surrounding prose, try to extract the first JSON object
    if not clean.startswith('{'):
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            clean = match.group(0)
    return json.loads(clean)


REQUIRED_KEYS = ('motivation', 'timeline', 'best_channel',
                 'call_script', 'mail_script', 'door_script',
                 'what_not_to_say')


def _validate(parsed: dict) -> dict:
    """Ensure expected keys exist; fill missing with safe empties."""
    out = {}
    for k in REQUIRED_KEYS:
        v = parsed.get(k)
        out[k] = v if isinstance(v, str) and v.strip() else ''
    # Normalize channel
    ch = (out.get('best_channel') or '').lower().strip()
    if ch not in ('call', 'mail', 'door'):
        ch = 'mail'  # safe default
    out['best_channel'] = ch
    return out


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def generate_deep_signal(parcel: dict, investigation: dict,
                         client=None) -> dict:
    """
    Synthesize a Deep Signal for an investigated parcel.

    Returns a dict with:
      motivation, timeline, best_channel, call_script, mail_script,
      door_script, what_not_to_say, model, tokens_in, tokens_out

    Raises on API error — caller handles HTTP 500 / 503 shaping.
    """
    if client is None:
        # Lazy import keeps module import-safe when running tests without SDK
        from anthropic import Anthropic
        client = Anthropic()

    user_prompt = _build_prompt(parcel, investigation)

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    raw_text = resp.content[0].text
    parsed = _parse_response(raw_text)
    validated = _validate(parsed)

    # Stamp metadata for cache row
    validated['model'] = MODEL
    try:
        validated['tokens_in'] = resp.usage.input_tokens
        validated['tokens_out'] = resp.usage.output_tokens
    except AttributeError:
        validated['tokens_in'] = None
        validated['tokens_out'] = None

    # Keep the raw response for future diagnostic use
    validated['_raw'] = parsed
    return validated
