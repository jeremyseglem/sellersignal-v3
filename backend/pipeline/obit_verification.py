"""
Obit Survivor Verification — gates the promotion from Band 2.5 (probable) to Band 1A (confirmed).

For each Band 2.5 candidate with an obit match:
  1. Fetch the full obituary text from the source URL
  2. Parse out the names of named SURVIVORS (and sometimes predeceased) from the text
  3. Cross-reference those names against the property's:
       - current owner name
       - trust grantor name
       - trustee name
  4. Classify the match:
       - 'confirmed':  survivor name explicitly matches property name → Band 1A
       - 'no_match':   full obit checked, no overlap → reject from Band 1
       - 'unverified': obit fetch failed / no survivor list → leave as Band 2.5

This is the trust gate at the top of the list.
"""
import re, json, os, sys
from datetime import datetime

# Known obit sources and their URL patterns (we built source-aware fetching)
OBIT_SOURCE_MAP = {
    'seattletimes.com':   'https://obituaries.seattletimes.com/obituary/',
    'dignitymemorial.com': 'https://www.dignitymemorial.com/obituaries/',
    'everloved.com':      'https://everloved.com/life-of/',
    'echovita.com':       'https://www.echovita.com/us/wa/bellevue/',
}


def extract_survivor_names(obit_text):
    """
    Parse an obit body and extract named people mentioned as survivors,
    predeceased family, or similar relational roles.
    Returns a list of {name, role, raw_context}.
    """
    if not obit_text: return []
    people = []

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', obit_text)

    # Common survivor-sentence patterns
    # Pattern 1: "survived by [names]" — grab up to 300 chars after
    patterns = [
        (r'survived by\s+(.{5,400}?)(?:\.|\bThe\b|\bIn lieu\b|\bA celebration\b|\bFuneral\b|$)', 'survivor'),
        (r'is survived by\s+(.{5,400}?)(?:\.|\bThe\b|\bIn lieu\b|\bA celebration\b|\bFuneral\b|$)', 'survivor'),
        (r'preceded in death by\s+(.{5,400}?)(?:\.|\bShe\b|\bHe\b|\bSurvived\b|\bThe\b|$)', 'predeceased'),
        (r'predeceased by\s+(.{5,400}?)(?:\.|\bShe\b|\bHe\b|\bSurvived\b|\bThe\b|$)', 'predeceased'),
        (r'(?:her|his)\s+(?:husband|wife|spouse|partner|son|daughter|mother|father|sister|brother|children|siblings?|grandchildren|parents?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z.]+){0,3}(?:\s+and\s+[A-Z][a-z]+(?:\s+[A-Z][a-z.]+){0,3})?)', 'relative'),
    ]

    for pattern, role in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fragment = match.group(1)
            # Extract proper names from the fragment
            # Pattern: capitalized words, possibly with middle initials / apostrophes
            name_pattern = re.compile(r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-.]+){0,3})\b")
            for nm in name_pattern.finditer(fragment):
                name = nm.group(1).strip()
                # Filter out relationship words that match the regex
                if name.split()[0].lower() in {'the', 'his', 'her', 'their', 'she', 'he', 'a', 'an', 'in',
                                                'also', 'additionally', 'including', 'late', 'beloved'}:
                    continue
                # Only keep if it has at least 2 words (first + last) OR is clearly a full name
                tokens = name.split()
                if len(tokens) < 2: continue
                people.append({'name': name, 'role': role, 'context': fragment[:200]})

    # Dedupe by name (case-insensitive)
    seen = set()
    out = []
    for p in people:
        k = p['name'].lower()
        if k in seen: continue
        seen.add(k)
        out.append(p)
    return out


def tokenize_name(name):
    if not name: return set()
    cleaned = re.sub(r"[^A-Za-z' ]", " ", name.upper()).replace("'", "")
    junk = {'JR', 'SR', 'II', 'III', 'IV', 'MR', 'MRS', 'DR', 'PHD',
            'TRUSTEE', 'TRUST', 'TR', 'TRS', 'CO', 'FAMILY', 'LIVING',
            'REVOCABLE', 'IRREVOCABLE', 'ESTATE', 'OF', 'THE', 'AND'}
    return {t for t in cleaned.split() if t.isalpha() and len(t) >= 2 and t not in junk}


def verify_match(survivors, property_owner, property_grantor=None, deceased_name=None):
    """
    Given parsed survivor list + property names, return verification classification.

    Returns:
      ('confirmed', confidence_detail)  — survivor explicitly named as property owner/grantor
      ('confirmed_deceased', detail)    — deceased IS the grantor (trust termination)
      ('no_match', reason)              — full obit checked, no overlap
    """
    owner_tokens = tokenize_name(property_owner or '')
    grantor_tokens = tokenize_name(property_grantor or '') if property_grantor else set()
    deceased_tokens = tokenize_name(deceased_name or '') if deceased_name else set()

    # Priority 1: The DECEASED matches the grantor directly
    #   (Gordon Gilbert Jr is the grantor of a trust = trust terminates on death)
    if grantor_tokens and deceased_tokens:
        overlap = grantor_tokens & deceased_tokens
        # Strong: 2+ given name overlap + surname
        # This means the deceased person is literally the trust grantor
        surname_matches = len(overlap) >= 2
        if surname_matches:
            return ('confirmed_deceased_is_grantor', {
                'deceased': deceased_name,
                'grantor': property_grantor,
                'token_overlap': sorted(overlap),
            })

    # Priority 2: A SURVIVOR is the current property owner
    #   (Gordon died, wife Sue is survivor and is the trustee/owner)
    for s in survivors:
        if s['role'] not in ('survivor', 'relative'): continue
        survivor_tokens = tokenize_name(s['name'])
        # Check against owner
        if owner_tokens:
            owner_overlap = owner_tokens & survivor_tokens
            non_surname_overlap = [t for t in owner_overlap if t not in ()]  # keep all
            if len(owner_overlap) >= 2:
                return ('confirmed_survivor_is_owner', {
                    'survivor': s['name'],
                    'owner': property_owner,
                    'token_overlap': sorted(owner_overlap),
                    'role_in_obit': s['role'],
                    'context': s['context'][:200],
                })
        # Check against grantor
        if grantor_tokens:
            grantor_overlap = grantor_tokens & survivor_tokens
            if len(grantor_overlap) >= 2:
                return ('confirmed_survivor_is_grantor', {
                    'survivor': s['name'],
                    'grantor': property_grantor,
                    'token_overlap': sorted(grantor_overlap),
                    'role_in_obit': s['role'],
                })

    # No strong match found
    return ('no_match', {
        'survivors_checked': len(survivors),
        'survivor_names': [s['name'] for s in survivors[:10]],
    })


# ═══════════════════════════════════════════════════════════════════════
# SANDBOX-ONLY ORCHESTRATOR — NOT RUNNABLE IN V3 AS-IS
# ═══════════════════════════════════════════════════════════════════════
# verify_all_current_matches() below was written to run inside the v2
# sandbox environment. It reads from and writes to hardcoded absolute
# paths under /home/claude/sellersignal_v2/out/ that only exist in the
# sandbox filesystem. Calling this function in v3 will raise FileNotFoundError.
#
# THE THREE PURE FUNCTIONS ABOVE (extract_survivor_names, tokenize_name,
# verify_match) ARE THE PORTABLE SURFACE AREA. They take plain arguments
# and return plain values — no I/O. v3's pipeline should call those
# directly, fed by a v3-native data source (Supabase table or live fetch),
# not via this orchestrator.
#
# When the v3 pipeline orchestration layer is wired up (later porting
# session), this function will either be:
#   - Rewritten to read obit matches and text from Supabase, OR
#   - Replaced by an inline orchestration call in the pipeline driver
#
# Left verbatim for now so the semantic reference to how v2 stitched
# these three pure functions together is preserved — but DO NOT CALL
# from v3 code until it's been properly rewired.
# ═══════════════════════════════════════════════════════════════════════
def verify_all_current_matches(obit_text_cache=None):
    """
    Run verification across all Band 2.5 / current Band 1 obit matches.
    Uses cached obit text if provided, or marks as 'unverified' if obit unavailable.
    """
    matches = json.load(open('/home/claude/sellersignal_v2/out/band1-obit-convergence.json'))

    if obit_text_cache is None:
        obit_text_cache = {}

    # Load any existing verification cache
    cache_path = '/home/claude/sellersignal_v2/out/obit-text-cache.json'
    if os.path.exists(cache_path):
        obit_text_cache = json.load(open(cache_path))

    results = []
    summary = {'confirmed': 0, 'no_match': 0, 'unverified': 0}

    for m in matches:
        obit_name = m.get('obit_name')
        owner = m.get('matched_name') if m.get('match_type') == 'owner' else None
        grantor = m.get('matched_name') if m.get('match_type') == 'grantor' else None

        # Load cached obit text for this obit
        obit_text = obit_text_cache.get(obit_name, '')
        if not obit_text:
            # No obit text cached → unverified
            results.append({
                **m,
                'verification_status': 'unverified',
                'verification_detail': 'No obit text available; run web_fetch on source URL'
            })
            summary['unverified'] += 1
            continue

        survivors = extract_survivor_names(obit_text)
        status, detail = verify_match(survivors, owner, grantor, deceased_name=obit_name)

        results.append({
            **m,
            'verification_status': status,
            'verification_detail': detail,
            'survivors_parsed': [s['name'] for s in survivors],
        })

        if status.startswith('confirmed'):
            summary['confirmed'] += 1
        elif status == 'no_match':
            summary['no_match'] += 1
        else:
            summary['unverified'] += 1

    # Save
    out_path = '/home/claude/sellersignal_v2/out/obit-verification-results.json'
    with open(out_path, 'w') as f:
        json.dump({'results': results, 'summary': summary}, f, indent=2, default=str)
    return results, summary


if __name__ == "__main__":
    results, summary = verify_all_current_matches()
    print(f"Verification results:")
    print(f"  Confirmed (→ Band 1A): {summary['confirmed']}")
    print(f"  No match (→ reject or Band 2.5): {summary['no_match']}")
    print(f"  Unverified (obit text not fetched): {summary['unverified']}")
