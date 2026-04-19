"""
Owner-name canonicalizer — parses KC Assessor owner strings into structured form.

Powered by Claude Haiku 4.5 because owner-string shapes are too heterogeneous
for deterministic rules (13+ observed patterns including "First Last",
"Last First", "Last First+Spouse-trust", trust names with trustee, LLCs
with embedded persons, mid-position suffixes like "William K Jr Blethen",
non-Anglo hyphenated names, etc.).

Output schema is the same that's written to owner_canonical_v3:
  {
    surname_primary: str
    surnames_all:    list[str]
    given_primary:   str
    given_all:       list[str]
    entity_type:     'individual' | 'trust' | 'llc' | 'company' | 'unknown'
    entity_name:     str
    co_owners:       list[{surname: str, given: list[str]}]
    confidence:      float 0.0-1.0
  }

Cost: ~$0.0005 per name using Haiku 4.5 (~$3 to backfill a 6,000-parcel ZIP).
"""
from __future__ import annotations

import json
import time
from typing import Optional


MODEL = 'claude-haiku-4-5-20251001'
MAX_TOKENS = 500
MAX_RETRIES = 2
INTER_CALL_SLEEP_S = 0.05   # polite rate limiting; Haiku is fast


SYSTEM_PROMPT = """You parse raw King County WA Assessor property-owner name strings into structured form.

The raw strings are heterogeneous. Common patterns:
  - "First M Last"                             → individual, simple
  - "Last First[-suffix]"                      → individual, surname-first Assessor convention
  - "Last First+Other-trust"                   → individual + trust tail
  - "<name> Revocable Living Trust"            → trust, not individual
  - "<name> LLC" / "<name> Corporation"        → entity, not individual
  - "First+CoFirst Family Trust+Ttees"         → multi-owner trust
  - "Number <Name> Trust +macleod Sarah"       → named trust with individual co-owner

Your job: given ONE raw owner string, output a JSON object with these fields:
  surname_primary: string (uppercase surname of the primary human owner, empty if pure entity)
  surnames_all:    array of uppercase surnames appearing in the string
  given_primary:   string (uppercase given/first name of primary owner)
  given_all:       array of uppercase given-name tokens for primary owner
  entity_type:     one of: "individual", "trust", "llc", "company", "unknown"
  entity_name:     string (the trust/LLC/company name if any, uppercase)
  co_owners:       array of {surname: string, given: array of strings} for secondary owners
  confidence:      float 0.0-1.0 (your certainty)

Rules:
  - DROP single-letter middle initials from given_all (e.g. "Bradford Lee Smith" → given_all=["BRADFORD","LEE"], "Steven A Ballmer" → given_all=["STEVEN"])
  - DROP suffixes (JR, SR, II, III, IV) — they are not part of the name
  - Handle mid-position suffixes like "William K Jr Blethen" → given_primary="WILLIAM", surname_primary="BLETHEN"
  - Preserve hyphenated surnames ("Pratt-Barlow") and hyphenated given names ("Shu-Ping")
  - For multi-owner records split by "+", the FIRST chunk is primary
  - Co-owners with only a given name (common in trusts like "Bohan David+liesl Trust") inherit the primary surname
  - Pure LLC/Corp: surname_primary="" and surnames_all=[]
  - Trust with named trustee (e.g. "Stork Suzanne-trustee Of The Willow Tree Trust"): surname_primary="STORK", given_primary="SUZANNE", entity_type="trust", entity_name="WILLOW TREE TRUST"
  - When you genuinely cannot parse, set confidence low (below 0.5)

Output ONLY the JSON object, no prose, no markdown fences."""


# ═══════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════
_VALID_ENTITY = {'individual', 'trust', 'llc', 'company', 'unknown'}
_REQUIRED_KEYS = {'surname_primary', 'surnames_all', 'given_primary',
                  'given_all', 'entity_type', 'entity_name', 'co_owners',
                  'confidence'}


def _validate_and_normalize(parsed: dict, raw: str) -> dict:
    """
    Enforce the schema on LLM output. Missing keys get sensible defaults;
    invalid entity_type is coerced to 'unknown' with conf=0.2.
    Returns a dict suitable for direct insert into owner_canonical_v3.
    """
    missing = _REQUIRED_KEYS - set(parsed.keys())
    for k in missing:
        if k in ('surnames_all', 'given_all', 'co_owners'):
            parsed[k] = []
        elif k == 'confidence':
            parsed[k] = 0.3
        else:
            parsed[k] = ''

    # Normalize strings — uppercase, strip whitespace
    for sk in ('surname_primary', 'given_primary', 'entity_type', 'entity_name'):
        v = parsed.get(sk, '')
        if not isinstance(v, str):
            v = str(v or '')
        parsed[sk] = v.strip().upper() if sk != 'entity_type' else v.strip().lower()

    # Arrays of strings — uppercase
    for lk in ('surnames_all', 'given_all'):
        v = parsed.get(lk) or []
        if not isinstance(v, list):
            v = []
        parsed[lk] = [str(x).strip().upper() for x in v if str(x).strip()]

    # co_owners: list of {surname, given}
    co = parsed.get('co_owners') or []
    if not isinstance(co, list):
        co = []
    clean_co = []
    for c in co:
        if not isinstance(c, dict):
            continue
        surname = str(c.get('surname', '') or '').strip().upper()
        given = c.get('given') or []
        if not isinstance(given, list):
            given = []
        given = [str(g).strip().upper() for g in given if str(g).strip()]
        if surname or given:
            clean_co.append({'surname': surname, 'given': given})
    parsed['co_owners'] = clean_co

    # entity_type validation — only cap confidence if caller supplied a
    # non-empty but invalid value. Empty string means "no entity info" and
    # the caller's confidence should stand.
    if parsed['entity_type'] not in _VALID_ENTITY:
        was_nonempty_invalid = bool(parsed['entity_type'])
        parsed['entity_type'] = 'unknown'
        if was_nonempty_invalid:
            parsed['confidence'] = min(float(parsed.get('confidence', 0.2)), 0.2)

    # confidence numeric & bounded
    try:
        conf = float(parsed.get('confidence', 0.5))
    except (TypeError, ValueError):
        conf = 0.3
    parsed['confidence'] = max(0.0, min(1.0, conf))

    # Ensure primary surname appears in surnames_all
    if parsed['surname_primary'] and parsed['surname_primary'] not in parsed['surnames_all']:
        parsed['surnames_all'].insert(0, parsed['surname_primary'])

    parsed['raw_name'] = raw
    parsed['model'] = MODEL
    return parsed


def _strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith('```'):
        # Drop opening fence
        parts = t.split('\n', 1)
        t = parts[1] if len(parts) == 2 else t[3:]
        # Drop closing fence
        if t.endswith('```'):
            t = t.rsplit('```', 1)[0]
        # Drop "json" language tag if present
        if t.startswith('json'):
            t = t[4:]
    return t.strip()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════
def canonicalize_owner_name(raw: str, client=None) -> dict:
    """
    Parse a single owner_name string. Returns a validated dict suitable
    for upsert into owner_canonical_v3.

    On any failure (API down, malformed JSON, empty string), returns
    a low-confidence 'unknown' record rather than raising — the caller
    can filter by confidence for re-runs.
    """
    raw = (raw or '').strip()
    if not raw:
        return _validate_and_normalize({
            'surname_primary': '', 'surnames_all': [],
            'given_primary': '', 'given_all': [],
            'entity_type': 'unknown', 'entity_name': '',
            'co_owners': [], 'confidence': 0.0,
        }, raw='')

    # Lazy import keeps module import-safe when running tests without the SDK
    if client is None:
        try:
            from anthropic import Anthropic
        except ImportError:
            return _validate_and_normalize({
                'surname_primary': '', 'surnames_all': [],
                'given_primary': '', 'given_all': [],
                'entity_type': 'unknown', 'entity_name': raw,
                'co_owners': [], 'confidence': 0.0,
            }, raw=raw)
        client = Anthropic()

    last_err: Optional[str] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': f'Parse this owner name: {raw}'}],
            )
            text = resp.content[0].text
            text = _strip_markdown_fences(text)
            parsed = json.loads(text)
            result = _validate_and_normalize(parsed, raw=raw)
            # Stamp usage if available (for cost telemetry in backfill)
            try:
                result['_tokens_in'] = resp.usage.input_tokens
                result['_tokens_out'] = resp.usage.output_tokens
            except AttributeError:
                pass
            return result
        except json.JSONDecodeError as e:
            last_err = f'json_decode: {e}'
        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'
        if attempt < MAX_RETRIES:
            time.sleep(0.5 * (attempt + 1))

    # Give up; return unknown
    return _validate_and_normalize({
        'surname_primary': '', 'surnames_all': [],
        'given_primary': '', 'given_all': [],
        'entity_type': 'unknown', 'entity_name': raw,
        'co_owners': [],
        'confidence': 0.1,
    }, raw=raw) | {'_error': last_err or 'unknown'}


def canonicalize_batch(raws: list[str], client=None,
                       sleep_s: float = INTER_CALL_SLEEP_S) -> list[dict]:
    """Serial batch canonicalize — rate-limit friendly."""
    out = []
    for raw in raws:
        out.append(canonicalize_owner_name(raw, client=client))
        if sleep_s:
            time.sleep(sleep_s)
    return out


# ═══════════════════════════════════════════════════════════════════════
# Supabase upsert helper
# ═══════════════════════════════════════════════════════════════════════
def upsert_canonical(supa, pin: str, canonical: dict) -> None:
    """
    Upsert a parsed record into owner_canonical_v3. Strips private telemetry
    fields (leading underscore) before write.
    """
    clean = {k: v for k, v in canonical.items() if not k.startswith('_')}
    # Ensure the required fields are present
    row = {
        'pin': pin,
        'surname_primary': clean.get('surname_primary', '') or None,
        'surnames_all': clean.get('surnames_all', []),
        'given_primary': clean.get('given_primary', '') or None,
        'given_all': clean.get('given_all', []),
        'entity_type': clean.get('entity_type', 'unknown'),
        'entity_name': clean.get('entity_name', '') or None,
        'co_owners': clean.get('co_owners', []),
        'confidence': clean.get('confidence', 0.0),
        'raw_name': clean.get('raw_name', ''),
        'model': clean.get('model', MODEL),
    }
    supa.table('owner_canonical_v3').upsert(row, on_conflict='pin').execute()
