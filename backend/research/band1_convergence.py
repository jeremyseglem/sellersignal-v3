"""
Band-1 promotion: cross-reference obituary harvest against Tier-2 Eastside leads.

When an obit name matches:
  - a current silent-transition owner → confirmed death, estate needs disposition
  - a trust grantor → trust terminated, property will transfer/sell
  - a dormant absentee owner → confirmed death of the dormant owner

These are "biology already triggered" leads. They promote from Band 2 inference
to Band 1 confirmed-imminent.

Output: JSON of PIN → {obit, match_type, confidence} for consumption by apply_banding.py
"""
import json, re, os
from datetime import datetime

# Token junk / name-noise filter
NAME_JUNK = {
    'JR', 'SR', 'II', 'III', 'IV', 'MR', 'MRS', 'DR', 'PHD', 'MD',
    'TRUSTEE', 'TRUST', 'CO-TR', 'CO', 'TR', 'TRS', 'FAMILY', 'LIVING',
    'REVOCABLE', 'IRREVOCABLE', 'SPOUSAL', 'PERS', 'REP', 'ESTATE',
    'OF', 'THE', 'AND', 'A', 'AN',
}
# Common surnames that would false-positive too aggressively without more signal
COMMON_SURNAMES = {
    'SMITH', 'JOHNSON', 'WILLIAMS', 'BROWN', 'JONES', 'GARCIA', 'MILLER',
    'DAVIS', 'RODRIGUEZ', 'MARTINEZ', 'WILSON', 'ANDERSON', 'TAYLOR',
    'THOMAS', 'MOORE', 'JACKSON', 'MARTIN', 'LEE', 'THOMPSON', 'WHITE',
    'HARRIS', 'CLARK', 'LEWIS', 'WALKER',
}


def tokenize_name(name):
    """Extract uppercase alphabetic tokens ≥ 2 chars, stripping junk."""
    if not name: return set()
    cleaned = re.sub(r"[^A-Za-z' ]", " ", name.upper())
    cleaned = cleaned.replace("'", "")
    tokens = [t for t in cleaned.split() if t.isalpha() and len(t) >= 2]
    return {t for t in tokens if t not in NAME_JUNK}


def match_obit_to_name(obit_tokens, target_tokens, surname):
    """
    Returns match confidence:
      - 'strong'              — uncommon surname + 2+ given-name match
      - 'medium'              — uncommon surname + 1 given-name match
      - 'needs_verification'  — common surname + 1 given-name match (could be anyone)
      - None                  — no match or surname-only on common name
    """
    if not surname or surname not in target_tokens:
        return None
    overlap = obit_tokens & target_tokens
    non_surname_overlap = overlap - {surname}
    if surname in COMMON_SURNAMES:
        # Common surname: need at least 1 given-name overlap just to surface as candidate
        if len(non_surname_overlap) >= 2:
            return 'strong'  # 2+ given name match on a common surname is still strong
        if len(non_surname_overlap) >= 1:
            return 'needs_verification'  # possible, flag for manual review
        return None
    # Uncommon surname
    if len(non_surname_overlap) >= 2:
        return 'strong'
    if len(non_surname_overlap) >= 1:
        return 'medium'
    # Surname-only on uncommon surname — flag for review
    return 'needs_verification'


# ─── LOAD DATA ────────────────────────────────────────────────────────
OBITS = [
    # From run_bellevue.py harvest, plus a few Medina/MI additions
    {"name": "Patricia Ann Rutledge", "date": "2026-03-20", "age_ctx": None, "area": "Bellevue"},
    {"name": "Harriet Ellen Brooks", "date": "2026-03-24", "age_ctx": 92, "area": "Bellevue"},
    {"name": "Steven Robert Williams", "date": "2026-03-01", "age_ctx": None, "area": "Bellevue"},
    {"name": "Katherine Jo Hinman", "date": "2026-01-01", "age_ctx": None, "area": "Bellevue"},
    {"name": "Liang-Tang Linda Lo Lee", "date": "2026-02-11", "age_ctx": 70, "area": "Bellevue"},
    {"name": "William Henry Walker Jr", "date": "2026-01-27", "age_ctx": 75, "area": "Bellevue"},
    {"name": "James Patrick Tierney", "date": "2026-03-29", "age_ctx": 87, "area": "Bellevue"},
    {"name": "Craig Groshart", "date": "2026-02-10", "age_ctx": None, "area": "Bellevue"},
    {"name": "Donald Eugene Hancock Sr", "date": "2026-03-01", "age_ctx": None, "area": "Bellevue"},
    {"name": "Gerald Edward Jaderholm Sr", "date": "2026-03-01", "age_ctx": None, "area": "Bellevue"},
    {"name": "Polly Anderson", "date": "2026-02-15", "age_ctx": 93, "area": "Bellevue"},
    {"name": "Garth Thomas", "date": "2025-09-10", "age_ctx": None, "area": "Bellevue"},
    {"name": "Gordon Wilson Gilbert Jr", "date": "2025-05-16", "age_ctx": 96, "area": "Bellevue"},
    {"name": "Linda L Williams", "date": "2026-02-01", "age_ctx": 80, "area": "Bellevue"},
    {"name": "Helen Petrakou Stoneman", "date": "2026-01-15", "age_ctx": None, "area": "Bellevue"},
    {"name": "Eugenia O'Keefe Murphy", "date": "2026-02-05", "age_ctx": 81, "area": "Bellevue"},
    {"name": "Devorah Weinstein", "date": "2026-04-11", "age_ctx": 85, "area": "Bellevue"},
    {"name": "Victor Elfendahl Parker", "date": "2025-04-15", "age_ctx": None, "area": "Medina"},
    {"name": "Adabelle Whitney Gardner", "date": "2026-02-15", "age_ctx": None, "area": "Bellevue"},
    {"name": "Kemp Edward Hiatt Sr", "date": "2026-03-15", "age_ctx": 92, "area": "Bellevue"},
    {"name": "Patricia Ann Dahlin", "date": "2026-03-25", "age_ctx": 80, "area": "Bellevue"},
    {"name": "Marilyn Joan Anderson", "date": "2026-04-11", "age_ctx": 93, "area": "Mercer Island"},
    {"name": "Rande Kenneth Bidgood", "date": "2026-03-30", "age_ctx": 78, "area": "Bellevue"},
    {"name": "Beth Dahlstrom", "date": "2026-03-01", "age_ctx": None, "area": "Seattle"},
    {"name": "Janny Hartley", "date": "2026-04-12", "age_ctx": None, "area": None},
    {"name": "Joan Carol Dehn Whidden", "date": "2026-03-10", "age_ctx": 89, "area": None},
]


def load_tier2_candidates():
    """Returns list of (pin, owner_name, grantor_name, signal_family, zip, record)"""
    out = []

    # 98004 (three separate files)
    for path, fam in [
        ('/home/claude/kc-data/bellevue-98004-silent-transition.json', 'silent_transition'),
        ('/home/claude/kc-data/bellevue-98004-trust-aging.json', 'trust_aging'),
        ('/home/claude/kc-data/bellevue-98004-dormant-absentee.json', 'dormant_absentee'),
    ]:
        if not os.path.exists(path): continue
        for L in json.load(open(path)):
            owner = L.get('owner') or L.get('current_name') or ''
            grantor = L.get('grantor_prior_name') or L.get('grantor') or ''
            out.append({
                'pin': L['pin'], 'owner': owner, 'grantor': grantor,
                'signal_family': fam, 'zip': '98004', 'record': L,
            })

    # Eastside other ZIPs
    EASTSIDE = '/home/claude/eastside-tier2'
    for z in ['98039', '98040', '98033', '98006', '98005']:
        for name in ['silent', 'trust', 'dormant']:
            path = f'{EASTSIDE}/{z}-{name}.json'
            if not os.path.exists(path): continue
            fam_map = {'silent': 'silent_transition', 'trust': 'trust_aging', 'dormant': 'dormant_absentee'}
            fam = fam_map[name]
            for L in json.load(open(path)):
                owner = L.get('owner') or ''
                grantor = L.get('grantor') or ''
                out.append({
                    'pin': L['pin'], 'owner': owner, 'grantor': grantor,
                    'signal_family': fam, 'zip': z, 'record': L,
                })
    return out


def run():
    tier2 = load_tier2_candidates()
    print(f"Loaded {len(tier2):,} Tier-2 lead records across Eastside")

    # Pre-tokenize each lead's owner + grantor names
    for t in tier2:
        t['owner_tokens'] = tokenize_name(t['owner'])
        t['grantor_tokens'] = tokenize_name(t['grantor'])

    matches = []
    for obit in OBITS:
        name = obit['name']
        tokens = tokenize_name(name)
        if len(tokens) < 2:
            continue
        surname_candidates = [t for t in tokens if t not in COMMON_SURNAMES] or list(tokens)
        # last name heuristic: last non-junk token of the original name string
        raw_tokens = [t.upper() for t in re.sub(r"[^A-Za-z' ]", " ", name).split()
                      if t.isalpha() and len(t) >= 2]
        raw_tokens = [t for t in raw_tokens if t not in NAME_JUNK]
        surname = raw_tokens[-1] if raw_tokens else None
        if not surname:
            continue

        # Match against all tier2 owner_tokens AND grantor_tokens
        for t in tier2:
            # owner match
            owner_match = match_obit_to_name(tokens, t['owner_tokens'], surname)
            grantor_match = match_obit_to_name(tokens, t['grantor_tokens'], surname) if t['grantor_tokens'] else None
            if owner_match or grantor_match:
                match_type = None
                if owner_match:
                    match_type = 'owner'
                    confidence = owner_match
                else:
                    match_type = 'grantor'
                    confidence = grantor_match
                matches.append({
                    'pin': t['pin'],
                    'obit_name': name,
                    'obit_date': obit['date'],
                    'obit_age': obit.get('age_ctx'),
                    'obit_area': obit.get('area'),
                    'match_type': match_type,
                    'confidence': confidence,
                    'matched_name': t['owner'] if match_type == 'owner' else t['grantor'],
                    'signal_family': t['signal_family'],
                    'zip': t['zip'],
                    'address': t['record'].get('address'),
                    'value': t['record'].get('value'),
                })

    # Dedupe - same pin + same obit = one match, prefer strong over medium
    seen = {}
    for m in matches:
        key = (m['pin'], m['obit_name'])
        if key not in seen:
            seen[key] = m
        elif seen[key]['confidence'] == 'medium' and m['confidence'] == 'strong':
            seen[key] = m
    matches = list(seen.values())

    print(f"\nTotal obit×Tier-2 matches: {len(matches)}")
    print(f"  Strong:               {sum(1 for m in matches if m['confidence'] == 'strong')}")
    print(f"  Medium:               {sum(1 for m in matches if m['confidence'] == 'medium')}")
    print(f"  Needs verification:   {sum(1 for m in matches if m['confidence'] == 'needs_verification')}")

    print(f"\n═══ BAND 1 LEADS — OBIT × TIER-2 CONVERGENCE ═══")
    # Sort: strong first, then by value
    matches.sort(key=lambda m: (m['confidence'] != 'strong', -(m['value'] or 0)))
    for m in matches:
        conf_mark = '🟢' if m['confidence'] == 'strong' else '🟡'
        print(f"\n{conf_mark} {m['address']}  ${m['value']:,}  [{m['zip']}]")
        print(f"    Signal: {m['signal_family']}  Match type: {m['match_type']}  Confidence: {m['confidence']}")
        print(f"    Obit: {m['obit_name']}  ({m['obit_date']}, age {m.get('obit_age') or '?'}, {m.get('obit_area') or '?'})")
        print(f"    Matched name: {m['matched_name']}")

    # Save
    os.makedirs('/home/claude/sellersignal_v2/out', exist_ok=True)
    with open('/home/claude/sellersignal_v2/out/band1-obit-convergence.json', 'w') as f:
        json.dump(matches, f, indent=2, default=str)
    print(f"\n✓ Saved to /home/claude/sellersignal_v2/out/band1-obit-convergence.json")

    return matches


if __name__ == "__main__":
    run()
