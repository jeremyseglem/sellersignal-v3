"""
Shadow-mode strict matcher for raw_signal_matches_v3 calibration.

The live gate in backend.ingest.legal_filings.name_match is soft — it
accepts any 2-token overlap so trust-titled owners and unusual name
formats keep matching. That softness leaves obvious-on-inspection
false positives in production: cases like "Michael S Hansen" matching
"Michael Ray Hansen" (different middle initials = different humans),
or "Lan Thi Thanh Nguyen" matching "Linh Thi Ngoc Nhu Nguyen" (only
the particle THI and the surname Nguyen overlap).

This module implements a STRICTER classifier that runs in shadow:
  - It does NOT remove matches from production.
  - It writes a verdict (status / reason / confidence) to columns on
    raw_signal_matches_v3.
  - The verdict is what powers the human-review queue; nothing in the
    selector or briefings reads these columns.

Once enough flagged matches have been reviewed and patterns are clear,
specific rules can be promoted into the live gate. Until then, this
module is read-only with respect to product behavior.
"""
from __future__ import annotations
import re
from typing import Optional

from backend.ingest.legal_filings import (
    normalize_name,
    _NAME_NOISE,
    _WHITESPACE,
    _TITLE_TOKENS,
    _TRUST_TOKENS,
    _PARTICLE_TOKENS,
)


# ─── Verdict types (kept in sync with schema 013) ───────────────────────

STATUS_LIKELY_VALID          = "likely_valid"
STATUS_NEEDS_REVIEW          = "needs_review"
STATUS_LIKELY_FALSE_POSITIVE = "likely_false_positive"

# Reason tags. Short, stable strings — UI / queries can filter by these.
REASON_CLEARED                = "cleared"                  # survived all checks
REASON_PARTICLE_ONLY          = "particle_only"            # only THI/VAN-class shared
REASON_MIDDLE_INITIAL_DISAGREE = "middle_initial_disagree"  # 'S' vs 'R'
REASON_MIDDLE_FULL_DISAGREE   = "middle_full_disagree"     # 'Bradford' vs 'Patrick'
REASON_FIRST_NAME_DIFF        = "first_name_diff"          # different first names
REASON_TOKEN_ONLY_NO_MIDDLE   = "token_only_no_middle"     # ambiguous, no middle to check
REASON_INSUFFICIENT_OVERLAP   = "insufficient_overlap"     # < 2 tokens after stripping


def _ordered_tokens(name: str) -> list[str]:
    """Tokenize like normalize_name but preserve token order. Needed to
    identify which token is the middle by position."""
    if not name:
        return []
    up = name.upper()
    up = _NAME_NOISE.sub(" ", up)
    up = _WHITESPACE.sub(" ", up).strip()
    out = []
    for t in up.split():
        if not t: continue
        if t in _TITLE_TOKENS or t in _TRUST_TOKENS or t in _PARTICLE_TOKENS:
            continue
        out.append(t)
    return out


def _is_trust_formatted(filing_name: str, owner_name: str) -> bool:
    """Trust-titled names have unreliable token order ('Coday Margaret
    Gold Trust' is surname-first). The shadow gate skips middle-name
    checks for these — the soft gate is the right floor for trusts."""
    combined = ((filing_name or '') + ' ' + (owner_name or '')).upper()
    return any(marker in combined for marker in ('TRUST', 'TTEE', 'TST'))


def _initial_aware_match(a: str, b: str) -> bool:
    """Return True if a and b represent the same name component allowing
    for initial abbreviation. 'S' matches 'Steven'; 'S' does not match
    'Ray'. Both-full names must equal exactly."""
    if not a or not b:
        return False
    if len(a) == 1:
        return b.startswith(a)
    if len(b) == 1:
        return a.startswith(b)
    return a == b


def classify_match(filing_name: str, owner_name: str) -> tuple[str, str, float]:
    """
    Classify a (filing_name, owner_name) pair as shadow-strict status.

    Returns: (status, reason, confidence) — see schema 013 for column
    semantics. Pure function, no I/O.

    The gate runs in this order:

      0. Sentinel/placeholder filing_name (e.g. tax foreclosure parcel-
         level matches that have no real name to compare) → likely_valid.
         The match was made by PIN, not by name; name-match logic
         doesn't apply.
      1. Token overlap < 2 → likely_false_positive (insufficient evidence)
      2. Particles drove the overlap → likely_false_positive (particle_only)
      3. Trust-formatted → likely_valid (we trust soft-gate floor here)
      4. Both names are exactly 3-token first-middle-last:
           - Initial-aware middle match → likely_valid (cleared)
           - Middle initial conflict → likely_false_positive
           - Middle full-word conflict → likely_false_positive
      5. Different first-name token in same position → likely_false_positive
      6. Otherwise (e.g. one side missing middle) → needs_review
    """
    # --- Step 0: parcel-level matches (tax foreclosure, etc.) carry a
    # placeholder string in matched_party and are not name-based. They
    # were made by PIN and have nothing to do with name disambiguation.
    # Sentinel patterns we've observed in production:
    #   "(Tax Foreclosure — parcel match)"
    #   "(parcel match)"
    fname_lower = (filing_name or '').lower()
    if 'parcel match' in fname_lower or not filing_name.strip():
        return (STATUS_LIKELY_VALID, REASON_CLEARED, 1.0)

    a_tokens = normalize_name(filing_name)
    b_tokens = normalize_name(owner_name)
    overlap = a_tokens & b_tokens

    # --- Step 1: insufficient overlap. Live gate would also reject.
    if len(overlap) < 2:
        return (STATUS_LIKELY_FALSE_POSITIVE, REASON_INSUFFICIENT_OVERLAP, 0.0)

    # --- Step 2: particle-only. Re-tokenize WITHOUT particle stripping
    # to see whether the overlap was driven by particles. If stripping
    # particles reduces overlap below 2, it was particle-driven.
    # (normalize_name already strips particles; compare against a
    # particle-keeping tokenization.)
    def _tokens_with_particles(name: str) -> set[str]:
        if not name: return set()
        up = name.upper()
        up = _NAME_NOISE.sub(" ", up)
        up = _WHITESPACE.sub(" ", up).strip()
        toks = {t for t in up.split() if len(t) >= 1}
        toks -= _TITLE_TOKENS
        toks -= _TRUST_TOKENS
        # Note: particles NOT stripped here.
        return toks
    a_with_p = _tokens_with_particles(filing_name)
    b_with_p = _tokens_with_particles(owner_name)
    overlap_with_p = a_with_p & b_with_p
    overlap_particles = overlap_with_p & _PARTICLE_TOKENS
    overlap_non_particle = overlap_with_p - _PARTICLE_TOKENS
    # If the particle-keeping overlap had >=2 tokens but the particle-
    # stripped overlap has <2, the overlap was particle-driven. (The
    # live gate now strips particles too, so post-deploy this case
    # should be rare in newly-written matches — but it explains
    # historical false positives that already exist in the table.)
    if len(overlap_particles) >= 1 and len(overlap_non_particle) < 2:
        return (STATUS_LIKELY_FALSE_POSITIVE, REASON_PARTICLE_ONLY, 0.1)

    # --- Step 3: trust-formatted owners. The soft gate is the floor.
    # We don't have enough structure to apply middle-name logic.
    if _is_trust_formatted(filing_name, owner_name):
        # Strong cleared signal if surname appears in trust title; medium
        # confidence otherwise.
        return (STATUS_LIKELY_VALID, REASON_CLEARED, 0.8)

    # --- Step 3.5: full-token agreement. When every meaningful token in
    # one side appears in the other (and there are at least 2 tokens),
    # it's an exact identity match — 'Ming Hsing Chi' vs 'MING HSING CHI',
    # 'Quang Van Nguyen' vs 'QUANG VAN NGUYEN', etc. The Step-4 middle
    # logic doesn't catch these because there's no token "outside the
    # overlap" to compare. Mark cleared with high confidence.
    smaller = min(len(a_tokens), len(b_tokens))
    if smaller >= 2 and len(overlap) >= smaller:
        return (STATUS_LIKELY_VALID, REASON_CLEARED, 1.0)

    # --- Step 4: both names parse cleanly as 3-token first-middle-last.
    a_ord = _ordered_tokens(filing_name)
    b_ord = _ordered_tokens(owner_name)
    if len(a_ord) == 3 and len(b_ord) == 3:
        # Identify shared first+last by overlap; remaining token is middle.
        a_middle = next((t for t in a_ord if t not in overlap), None)
        b_middle = next((t for t in b_ord if t not in overlap), None)
        # Identify first/last position to detect first-name swap
        # (e.g. 'John Edward Richards' vs 'Gordon John Richards' both
        # have JOHN+RICHARDS overlap but JOHN is first in one and middle
        # in the other — clearly different humans).
        a_first, a_mid_pos, a_last = a_ord[0], a_ord[1], a_ord[2]
        b_first, b_mid_pos, b_last = b_ord[0], b_ord[1], b_ord[2]
        if a_first != b_first and a_last == b_last:
            # First names differ → different humans, even if other tokens overlap.
            return (STATUS_LIKELY_FALSE_POSITIVE, REASON_FIRST_NAME_DIFF, 0.1)
        if a_middle and b_middle:
            if _initial_aware_match(a_middle, b_middle):
                return (STATUS_LIKELY_VALID, REASON_CLEARED, 0.95)
            # Middle conflict — initial vs initial, or full vs full.
            if len(a_middle) == 1 or len(b_middle) == 1:
                return (STATUS_LIKELY_FALSE_POSITIVE, REASON_MIDDLE_INITIAL_DISAGREE, 0.2)
            return (STATUS_LIKELY_FALSE_POSITIVE, REASON_MIDDLE_FULL_DISAGREE, 0.15)
        # 3-token on both sides but middle is empty on one — fall through.

    # --- Step 5: 3-token vs other length, can't compare middles cleanly.
    # This is the genuine ambiguity zone. Token overlap is real but we
    # don't have structural confidence. Examples:
    #   'Hsin Yu Lin' (3 tok) vs 'SHANA HSIN-HWA LIN' (4 tok)
    #   'Soo Min Park' (3 tok) vs 'RAN-SOO PARK' (3 tok where SOO is middle)
    # Mark for human review.
    return (STATUS_NEEDS_REVIEW, REASON_TOKEN_ONLY_NO_MIDDLE, 0.5)
