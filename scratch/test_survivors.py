"""Prototype survivor/preceded-by extractor. Tested against real obit excerpts
pulled from /diag/obituary-excerpts. Iterate here before merging into
backend/harvesters/obituary.py.
"""
import json
import re
from typing import Optional


# Relationship keywords we recognize. Order matters: longer/more-specific
# patterns first so "step-daughter" doesn't get eaten by "daughter".
RELATIONSHIPS = [
    # Partners
    "loving wife", "beloved wife", "dear wife", "wife", "widow",
    "loving husband", "beloved husband", "dear husband", "husband", "widower",
    "partner", "spouse", "life partner",
    # Children
    "daughter-in-law", "son-in-law", "step-daughter", "step-son",
    "daughters", "sons", "daughter", "son", "children", "child",
    # Parents
    "mother", "father", "mom", "dad", "parents",
    # Siblings
    "sisters", "brothers", "sister", "brother", "siblings",
    # Extended
    "grandchildren", "grandsons", "granddaughters", "grandson", "granddaughter",
    "great-grandchildren", "great-grandson", "great-granddaughter",
    "nephews", "nieces", "nephew", "niece",
    "aunts", "uncles", "aunt", "uncle",
    "cousins", "cousin",
    "stepchildren", "stepmother", "stepfather",
]

# Marker phrases that start the "who survives them" section
SURVIVED_BY_MARKERS = [
    r"is\s+survived\s+by",
    r"are\s+survived\s+by",
    r"survived\s+by",
    r"survivors?\s+include",
    r"leaves\s+behind",
    r"leaves?\s+(?:to\s+)?mourn",
    r"is\s+lovingly\s+remembered\s+by",
    r"she\s+leaves",
    r"he\s+leaves",
]

# Marker phrases for the "who died before them" section
PRECEDED_BY_MARKERS = [
    r"preceded\s+in\s+death\s+by",
    r"predeceased\s+by",
    r"was\s+preceded\s+by",
]

# Terminators — the survivor section ends at these. Crucially, we also
# terminate when we hit the OTHER section's marker (so preceded_by text
# doesn't leak into survivors and vice-versa).
ALL_SECTION_MARKERS_RE = re.compile(
    r"\b(?:is\s+survived\s+by|survived\s+by|survivors?\s+include|"
    r"leaves\s+behind|preceded\s+in\s+death\s+by|predeceased\s+by|"
    r"was\s+preceded\s+by|is\s+lovingly\s+remembered|"
    r"she\s+leaves|he\s+leaves)\b",
    re.IGNORECASE,
)

SECTION_TERMINATORS = [
    r"\.\s+(?:services?|funeral|memorial|burial|interment|visitation|"
    r"celebration\s+of\s+life|graveside|committal|rosary|viewing)\b",
    r"\.\s+(?:in\s+lieu|donations?|contributions?|flowers?)\b",
    r"\.\s+(?:arrangements?|a\s+celebration|please\s+join)\b",
    r"\.\s+(?:she|he|they)\s+(?:was\s+born|was\s+an?|was\s+the|worked)\b",
    r"\.\s+[A-Z][a-z]+\s+(?:was\s+born|graduated|enlisted|attended)\b",
]


def _find_section(text: str, start_markers: list, this_section_type: str) -> Optional[str]:
    """Find first occurrence of any start_marker and extract text up to
    the first terminator, the OTHER section marker, or 800 chars.

    this_section_type: 'survivors' or 'preceded_by' — used to ensure we
    stop at the opposing section's marker instead of leaking into it.
    """
    lo = text.lower()
    # Find earliest start marker
    earliest = None
    for pat in start_markers:
        m = re.search(pat, lo)
        if m and (earliest is None or m.end() < earliest):
            earliest = m.end()
    if earliest is None:
        return None
    chunk = text[earliest : earliest + 800]
    chunk_lo = chunk.lower()

    # 1) Terminate at next sentence-ending terminator (funeral services etc.)
    terminator_pos = None
    for pat in SECTION_TERMINATORS:
        m = re.search(pat, chunk_lo)
        if m and (terminator_pos is None or m.start() < terminator_pos):
            terminator_pos = m.start() + 1  # keep the period

    # 2) Terminate at next section marker (survivors → preceded_by, etc.)
    # This prevents leakage between sections.
    opposing_pos = None
    for m in ALL_SECTION_MARKERS_RE.finditer(chunk):
        # Skip markers that are part of THIS section (e.g. "is survived by"
        # at position 0 is the one we just matched — skip ones at start).
        if m.start() < 3:
            continue
        # The marker text must match the OPPOSING section type
        marker_text = m.group().lower()
        is_survivor_marker = (
            "survived" in marker_text or "leaves" in marker_text
            or "survivor" in marker_text or "remembered" in marker_text
        )
        if this_section_type == "preceded_by" and is_survivor_marker:
            opposing_pos = m.start()
            break
        if this_section_type == "survivors" and not is_survivor_marker:
            opposing_pos = m.start()
            break

    cut_positions = [p for p in (terminator_pos, opposing_pos) if p is not None]
    if cut_positions:
        chunk = chunk[: min(cut_positions)]
    return chunk.strip()


def _parse_names_from_chunk(chunk: str) -> list:
    """
    Given a chunk like:
      "his wife Jane, sons John, Michael, and Mark, and daughter Sarah"
    Return:
      [{name: "Jane", relationship: "wife"},
       {name: "John", relationship: "son"},
       {name: "Michael", relationship: "son"},
       {name: "Mark", relationship: "son"},
       {name: "Sarah", relationship: "daughter"}]
    """
    results = []
    if not chunk:
        return results

    # Strip leading prepositions/articles
    text = chunk
    # Find all "{relationship} {name}[, name, ...]" groups
    # Strategy: split on relationship keywords, then parse names within
    # each segment.
    rel_pattern = r"\b(" + "|".join(re.escape(r) for r in RELATIONSHIPS) + r")\b"
    segments = re.split(rel_pattern, text, flags=re.IGNORECASE)
    # segments alternates: [pre-text, rel1, between1, rel2, between2, ...]
    # We pair (rel, next_segment) and extract names from next_segment.
    i = 1
    while i < len(segments):
        rel = segments[i].lower()
        after = segments[i + 1] if i + 1 < len(segments) else ""
        # Normalize: singular relationship for cleaner storage
        rel_singular = _singularize_relationship(rel)
        # Extract names from `after` — stop only at period or newline.
        # Semicolons are commonly used as LIST SEPARATORS between multiple
        # entries in a relationship group ("three children: Todd Bohon,
        # Stanwood, WA; Cynthia Cooper, ..."), not as section enders, so
        # don't cut on `;`. The split on the next relationship keyword
        # above already bounds us.
        boundary = re.search(r"[\.\n]", after)
        if boundary:
            names_segment = after[: boundary.start()]
        else:
            names_segment = after[:400]
        names = _split_names(names_segment)
        for n in names:
            if n:
                results.append({
                    "name":         n,
                    "relationship": rel_singular,
                })
        i += 2
    return results


def _singularize_relationship(rel: str) -> str:
    """'sons' -> 'son', 'daughters' -> 'daughter', 'children' -> 'child',
    'grandchildren' -> 'grandchild', preserve compound rels."""
    rel = rel.lower().strip()
    simple = {
        "sons": "son", "daughters": "daughter", "children": "child",
        "sisters": "sister", "brothers": "brother", "siblings": "sibling",
        "grandchildren": "grandchild", "great-grandchildren": "great-grandchild",
        "grandsons": "grandson", "granddaughters": "granddaughter",
        "nephews": "nephew", "nieces": "niece",
        "aunts": "aunt", "uncles": "uncle", "cousins": "cousin",
        "stepchildren": "stepchild",
        "parents": "parent",
        "loving wife": "wife", "beloved wife": "wife", "dear wife": "wife",
        "loving husband": "husband", "beloved husband": "husband",
        "dear husband": "husband",
    }
    return simple.get(rel, rel)


# Name pattern: 2-4 capitalized tokens. Each token can have internal caps
# for McDonald, O'Brien, etc. Allows hyphen for "Mary-Jane", periods for "J."
_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z'\.\-]{1,}"
    r"(?:\s+[A-Z][A-Za-z'\.\-]{1,}){0,3})\b"
)


def _split_names(segment: str) -> list:
    """Extract capitalized name phrases from a segment.
    Handles 'Jane', 'Jane Smith', 'Mary Jane Smith', 'John, Michael, and Mark',
    'Jane (Smith) Doe'.

    Critically: stops at ' of ' / ' in ' / ' from ' / ' at ' to avoid
    capturing city/state in "Todd Bohon of Millington, TN"."""
    # Strip parentheses — maiden names etc. are noise for our purposes
    segment = re.sub(r"\([^)]*\)", " ", segment)
    # Cut at location prepositions (after a name, "of Millington, TN" starts
    # a location clause — we want to drop everything after ' of '/' in '/etc.)
    # We apply this per comma-separated piece to handle "son John of Chicago,
    # daughter Sarah of Miami" correctly.
    pieces = re.split(r",\s*(?:and\s+)?|\s+and\s+", segment)
    names_out = []
    stopwords = {
        "The", "His", "Her", "Their", "She", "He", "They", "Who", "Whom",
        "WA", "USA", "United", "States", "Washington", "Seattle", "Bellevue",
        "Kirkland", "Redmond", "University", "School", "High", "Hospital",
        "Center", "Medical", "Obituary", "Service", "Services", "Memorial",
        "God", "Jesus", "Christ", "Lord", "Lt", "Capt", "Sgt", "Rev",
        "Born", "Died", "January", "February", "March", "April", "May",
        "June", "July", "August", "September", "October", "November", "December",
        "Mom", "Dad", "Mother", "Father",
        # US state abbreviations — often appear after "of Millington, TN"
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WV", "WI", "WY",
    }
    for piece in pieces:
        # Strip location clause: "Todd Bohon of Millington" -> "Todd Bohon"
        piece = re.split(
            r"\s+(?:of|in|from|at|residing\s+in|living\s+in|near)\s+",
            piece,
            maxsplit=1,
        )[0]
        matches = _NAME_RE.findall(piece)
        for m in matches:
            tokens = m.split()
            # Reject single-token "names" — they're almost always cities
            # ("Millington", "Stanwood", "Edmonds") or state abbreviations
            # ("TN", "WA"). Real family members in obits are almost always
            # written as "First Last". We lose single-first-name parents
            # ("his father Patrick") but that's an acceptable precision
            # tradeoff vs. polluting the heir list with place names.
            if len(tokens) < 2:
                continue
            if all(t in stopwords for t in tokens):
                continue
            # Collapse internal whitespace runs
            clean = re.sub(r"\s+", " ", m).strip()
            names_out.append(clean)
    # Dedupe preserving order
    seen = set()
    deduped = []
    for n in names_out:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped


def extract_survivors(text: str) -> list:
    chunk = _find_section(text, SURVIVED_BY_MARKERS, "survivors")
    return _parse_names_from_chunk(chunk) if chunk else []


def extract_preceded_by(text: str) -> list:
    chunk = _find_section(text, PRECEDED_BY_MARKERS, "preceded_by")
    return _parse_names_from_chunk(chunk) if chunk else []


def extract_age_v2(text: str) -> Optional[int]:
    """Improved age extraction. Handles:
    - "age 81"  / "aged 81"
    - "81 years old" / "at the age of 81"
    - "(81)" / "(age 81)"
    - "he was 92" / "she was 92"
    - "in his 85 years"
    - "at the age of ninety-five"  → 95
    """
    # Pattern: "(NN)" where NN is plausible age
    m = re.search(r"\((\d{1,3})\)", text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 115:
            return n
    # Pattern: "age NN", "aged NN", "at the age of NN"
    m = re.search(r"\b(?:at\s+the\s+age\s+of|age[d]?)\s+(\d{1,3})\b",
                  text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 115:
            return n
    # Pattern: "NN years old" / "NN years of age"
    m = re.search(r"\b(\d{1,3})\s+years?\s+(?:old|of\s+age)\b",
                  text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 115:
            return n
    # Pattern: "he was NN" / "she was NN" (stated age at death)
    m = re.search(r"\b(?:he|she|they)\s+was\s+(\d{1,3})\b",
                  text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 18 <= n <= 115:  # minimum 18 to avoid false matches like "he was 5"
            return n
    # Pattern: "in his NN years" / "in her NN years"
    m = re.search(r"\bin\s+(?:his|her|their)\s+(\d{1,3})\s+years\b",
                  text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 18 <= n <= 115:
            return n
    # Pattern: "age of ninety-five" etc. — written-out numbers
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    m = re.search(r"(?:age\s+of|aged?)\s+"
                  r"(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
                  r"(?:[\s\-](one|two|three|four|five|six|seven|eight|nine))?",
                  text, re.IGNORECASE)
    if m:
        tens = word_to_num.get(m.group(1).lower(), 0)
        ones = word_to_num.get((m.group(2) or "").lower(), 0)
        if 1 <= tens + ones <= 115:
            return tens + ones
    return None


# ─── Run against real samples ──────────────────────────────────────────

if __name__ == "__main__":
    d = json.load(open('/tmp/ex.json'))
    for r in d['records']:
        print(f"\n{'='*70}")
        print(f"DECEDENT: {r['decedent']}  death={r['death_date']}")
        excerpt = r['excerpt']
        print(f"  age_extracted: {extract_age_v2(excerpt)}")
        survivors = extract_survivors(excerpt)
        preceded = extract_preceded_by(excerpt)
        print(f"  SURVIVORS ({len(survivors)}):")
        for s in survivors:
            print(f"    - {s['name']}  ({s['relationship']})")
        print(f"  PRECEDED BY ({len(preceded)}):")
        for s in preceded:
            print(f"    - {s['name']}  ({s['relationship']})")
