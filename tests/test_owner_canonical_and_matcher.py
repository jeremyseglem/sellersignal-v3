"""
Tests for owner_canonicalizer + canonical-aware matcher.
No API calls — validation + matching tested with synthetic canonical rows.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '.')

from backend.ingest.owner_canonicalizer import _validate_and_normalize
from backend.pipeline.legal_filings import (
    name_match,
    match_canonical,
    strong_match,
    surname_only_match,
    _extract_surname,
    normalize_name,
)

FAILS = 0
PASSES = 0


def t(label: str, got, want):
    global FAILS, PASSES
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r}\n         want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


# ═══════════════════════════════════════════════════════════════════════
# 1. Validator — schema normalization
# ═══════════════════════════════════════════════════════════════════════
print("═══ VALIDATOR ═══")

# Happy path: complete LLM output
t("complete valid input",
  _validate_and_normalize({
      'surname_primary': 'Smith',
      'surnames_all': ['smith'],
      'given_primary': 'John',
      'given_all': ['John', 'M'],
      'entity_type': 'individual',
      'entity_name': '',
      'co_owners': [],
      'confidence': 0.9,
  }, raw='John M Smith'),
  {
      'surname_primary': 'SMITH',
      'surnames_all': ['SMITH'],
      'given_primary': 'JOHN',
      'given_all': ['JOHN', 'M'],
      'entity_type': 'individual',
      'entity_name': '',
      'co_owners': [],
      'confidence': 0.9,
      'raw_name': 'John M Smith',
      'model': 'claude-haiku-4-5-20251001',
  })

# Missing fields get defaults
result = _validate_and_normalize({
    'surname_primary': 'Clapp',
    'entity_type': 'individual',
}, raw='Kristina H Clapp')
t("missing fields defaulted", result['surnames_all'], ['CLAPP'])
t("missing fields: given_all=[]", result['given_all'], [])
t("missing fields: co_owners=[]", result['co_owners'], [])

# Invalid entity_type → unknown + cap conf
result = _validate_and_normalize({
    'surname_primary': 'X', 'entity_type': 'wat', 'confidence': 0.9,
}, raw='X')
t("invalid entity_type → unknown", result['entity_type'], 'unknown')
t("invalid entity_type caps confidence", result['confidence'], 0.2)

# Co-owners normalization
result = _validate_and_normalize({
    'surname_primary': 'Auslander',
    'given_all': ['Robert'],
    'entity_type': 'individual',
    'co_owners': [
        {'surname': 'auslander', 'given': ['mary']},
        'garbage entry',  # malformed, should be dropped
        {'surname': '', 'given': ['liesl']},  # given-only co-owner
    ],
}, raw='Auslander Robert+mary G')
t("co_owners uppercased + malformed dropped",
  result['co_owners'],
  [{'surname': 'AUSLANDER', 'given': ['MARY']},
   {'surname': '', 'given': ['LIESL']}])

# Bare {} input — validator defaults fill in, conf should default to 0.3
# (this is what happens when LLM returns barely anything usable; the
# "empty raw string" path in canonicalize_owner_name explicitly sets 0.0)
result = _validate_and_normalize({}, raw='')
t("bare {} input → unknown conf=0.3 (defaults path)",
  (result['entity_type'], result['confidence']),
  ('unknown', 0.3))

# Explicit-empty path — caller supplies conf=0.0 for known-empty
result = _validate_and_normalize({
    'surname_primary': '', 'surnames_all': [],
    'given_primary': '', 'given_all': [],
    'entity_type': 'unknown', 'entity_name': '',
    'co_owners': [], 'confidence': 0.0,
}, raw='')
t("explicit empty → unknown conf=0.0",
  (result['entity_type'], result['confidence']),
  ('unknown', 0.0))

# Surname_primary auto-added to surnames_all if missing
result = _validate_and_normalize({
    'surname_primary': 'Frantz',
    'surnames_all': [],  # LLM forgot to include primary
    'entity_type': 'individual',
}, raw='William T Frantz')
t("primary auto-added to surnames_all",
  result['surnames_all'],
  ['FRANTZ'])


# ═══════════════════════════════════════════════════════════════════════
# 2. Canonical matcher — the production path
# ═══════════════════════════════════════════════════════════════════════
print()
print("═══ CANONICAL MATCHER ═══")


def canon(surname='', given_all=None, surnames_all=None, co_owners=None,
          entity_type='individual'):
    return {
        'surname_primary': surname.upper(),
        'surnames_all': [s.upper() for s in (surnames_all or [surname])],
        'given_primary': (given_all or [''])[0].upper(),
        'given_all': [g.upper() for g in (given_all or [])],
        'entity_type': entity_type,
        'entity_name': '',
        'co_owners': co_owners or [],
        'confidence': 1.0,
        'raw_name': '',
        'model': 'test',
    }


# STRONG matches — decedent name collides with owner on surname + given
t("STRONG: James Fraioli ↔ canon{Fraioli, James}",
  match_canonical('JAMES JOSEPH FRAIOLI',
                  canon('Fraioli', ['James'])),
  ('STRONG', 3))

t("STRONG: William Frantz ↔ canon{Frantz, William Thomas}",
  match_canonical('WILLIAM THOMAS FRANTZ',
                  canon('Frantz', ['William', 'T'])),
  ('STRONG', 3))

# SURNAME_ONLY — surname hit, no given overlap
t("SURNAME_ONLY: Victoria Frantz ↔ canon{Frantz, William}",
  match_canonical('VICTORIA N FRANTZ',
                  canon('Frantz', ['William', 'T'])),
  ('SURNAME_ONLY', 2))

t("SURNAME_ONLY: Robert Case II ↔ canon{Case, Laurel}",
  match_canonical('ROBERT CASE II',
                  canon('Case', ['Laurel', 'A'])),
  ('SURNAME_ONLY', 2))

# NO MATCH — different surnames
t("NO_MATCH: Robert Lee Harris ↔ canon{Steil, Robert Lee}",
  match_canonical('ROBERT LEE HARRIS',
                  canon('Steil', ['Robert', 'Lee'])),
  None)

# NO MATCH — pure LLC
t("NO_MATCH: any decedent ↔ pure LLC",
  match_canonical('JOHN SMITH',
                  canon('', surnames_all=[], entity_type='llc')),
  None)

# Multi-owner trust — surname in co_owner list
multi_owner_canonical = canon(
    'Zhang', ['Bowen'],
    surnames_all=['ZHANG', 'LIU'],
    co_owners=[{'surname': 'LIU', 'given': ['QI']}],
    entity_type='trust',
)
t("STRONG: Qi Liu ↔ multi-owner trust (co_owner surname + given match)",
  match_canonical('QI LIU', multi_owner_canonical),
  ('STRONG', 3))

# Co-owner with no given (Bohan David+liesl Trust case → liesl inherits Bohan)
bohan = canon(
    'Bohan', ['David'],
    co_owners=[{'surname': 'BOHAN', 'given': ['LIESL']}],
    entity_type='trust',
)
t("STRONG: Liesl Bohan ↔ Bohan David+liesl Trust",
  match_canonical('LIESL BOHAN', bohan),
  ('STRONG', 3))

# Trust with embedded primary person (Uberstine Gary trustee case)
uberstine = canon(
    'Uberstine', ['Gary'],
    entity_type='trust',
)
t("STRONG: Gary Uberstine decedent ↔ Uberstine Gary trustee of Willow Tree Trust",
  match_canonical('GARY UBERSTINE', uberstine),
  ('STRONG', 3))


# ═══════════════════════════════════════════════════════════════════════
# 3. Legacy string matcher — still strict, still rejects false positives
# ═══════════════════════════════════════════════════════════════════════
print()
print("═══ LEGACY STRING MATCHER (back-compat, still strict) ═══")

t("legacy: 'James J Fraioli' ↔ 'JAMES JOSEPH FRAIOLI' (MATCH)",
  name_match("JAMES JOSEPH FRAIOLI", "James J Fraioli"), True)

t("legacy: 'ROBERT LEE HARRIS' ↔ 'Robert Lee Steil' (REJECT)",
  name_match("ROBERT LEE HARRIS", "Robert Lee Steil"), False)

t("legacy: 'Mary Jane Smith' ↔ 'Mary Jane Jones' (REJECT)",
  name_match("Mary Jane Smith", "Mary Jane Jones"), False)

t("legacy: 'VICTORIA FRANTZ' ↔ 'William T Frantz' (REJECT — no given overlap)",
  name_match("VICTORIA N FRANTZ", "William T Frantz"), False)


# ═══════════════════════════════════════════════════════════════════════
# 4. Surname extraction — must handle decedent + owner formats
# ═══════════════════════════════════════════════════════════════════════
print()
print("═══ SURNAME EXTRACTION ═══")

t("extract: 'ROBERT CASE II'", _extract_surname("ROBERT CASE II"), "CASE")
t("extract: 'JAMES C SMITH JR'", _extract_surname("JAMES C SMITH JR"), "SMITH")
t("extract: 'William T Frantz'", _extract_surname("William T Frantz"), "FRANTZ")
t("extract: empty", _extract_surname(""), "")
t("extract: 'GENEVIEVE C ASHFORD'", _extract_surname("GENEVIEVE C ASHFORD"), "ASHFORD")


# ═══════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════
print()
print(f"{'─'*60}")
if FAILS == 0:
    print(f"✓ ALL {PASSES} TESTS PASSED")
    sys.exit(0)
else:
    print(f"✗ {FAILS} FAILED, {PASSES} PASSED")
    sys.exit(1)
