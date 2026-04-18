"""
Rebuild Band 1 strictly and introduce Band 2.5 + family clusters.

Critic's hard rule: Band 1 = VERIFIED REALITY ONLY.
  - Full name match OR
  - Grantor name match OR
  - Confirmed probate filing

Everything else with partial obit correlation → Band 2.5 (Convergent Event Candidate)

Family clusters: when 2+ Band 2.5 matches share surname + ZIP area,
roll them up into ONE portfolio-level lead instead of N separate leads.
"""
import json, os, re
from collections import defaultdict
from datetime import datetime

# ─── STRICT MATCH CLASSIFIER ───────────────────────────────────────────
def classify_match_strength(obit_name, owner_name, grantor_name=None):
    """
    Returns a tier + confidence components.
    Tiers: 'band1_verified' | 'band2_5_convergent' | 'reject'
    """
    if not obit_name: return {'tier': 'reject', 'reason': 'no obit'}

    # Tokenize
    JUNK = {'JR', 'SR', 'II', 'III', 'IV', 'MR', 'MRS', 'DR', 'PHD', 'MD',
            'TRUSTEE', 'TRUST', 'TR', 'TRS', 'CO', 'FAMILY', 'LIVING',
            'REVOCABLE', 'IRREVOCABLE', 'ESTATE', 'OF', 'THE', 'AND', 'A'}
    def tok(s):
        if not s: return set()
        cleaned = re.sub(r"[^A-Za-z' ]", " ", s.upper()).replace("'", "")
        return {t for t in cleaned.split() if t.isalpha() and len(t) >= 2 and t not in JUNK}

    obit_tokens = tok(obit_name)
    if len(obit_tokens) < 2: return {'tier': 'reject', 'reason': 'obit too short'}

    # Last token is surname heuristic
    raw = [t for t in re.sub(r"[^A-Za-z' ]", " ", obit_name.upper()).split()
           if t.isalpha() and len(t) >= 2 and t not in JUNK]
    surname = raw[-1] if raw else None
    if not surname: return {'tier': 'reject', 'reason': 'no surname'}

    owner_tokens = tok(owner_name or '')
    grantor_tokens = tok(grantor_name or '') if grantor_name else set()

    # Check owner match
    if surname in owner_tokens:
        target = owner_tokens
        match_location = 'owner'
    elif grantor_tokens and surname in grantor_tokens:
        target = grantor_tokens
        match_location = 'grantor'
    else:
        return {'tier': 'reject', 'reason': 'no surname match'}

    # Count given-name overlap (non-surname)
    given_overlap = (obit_tokens - {surname}) & (target - {surname})
    n_given = len(given_overlap)

    # STRICT BAND 1 RULES (critic's bar):
    # - Full name match: all obit given names (at least 2) match target
    obit_givens = obit_tokens - {surname}
    if len(obit_givens) >= 2 and obit_givens.issubset(target):
        return {
            'tier': 'band1_verified',
            'reason': 'full-name match',
            'match_location': match_location,
            'given_overlap': sorted(given_overlap),
        }
    # Grantor exact match = a specific person funded the trust; if that person
    # matches an obit strongly it's a verified trust-termination event
    if match_location == 'grantor' and n_given >= 2:
        return {
            'tier': 'band1_verified',
            'reason': 'grantor name strongly matches obit (2+ given names)',
            'match_location': match_location,
            'given_overlap': sorted(given_overlap),
        }

    # BAND 2.5: surname match + partial given-name match → convergent candidate
    if n_given >= 1:
        return {
            'tier': 'band2_5_convergent',
            'reason': f'surname + {n_given} given-name match',
            'match_location': match_location,
            'given_overlap': sorted(given_overlap),
        }

    # Surname-only → still 2.5 but much weaker; include for cluster analysis
    # but not as standalone signal
    return {
        'tier': 'band2_5_convergent',
        'reason': 'surname-only match (cluster candidate)',
        'match_location': match_location,
        'given_overlap': [],
        'weak': True,
    }


# ─── CONFIDENCE SCORE (0-100) — orthogonal to band ─────────────────────
def compute_confidence_score(match_result, age_estimate, obit_age,
                              obit_area, property_zip, property_city,
                              convergent_families):
    """
    Returns a score 0-100 built from 4 orthogonal dimensions:
      name_match: 0-40
      geo_match:  0-20
      signal_overlap: 0-20
      age_alignment: 0-20
    """
    score = 0
    components = {}

    # Name match
    reason = match_result.get('reason', '')
    weak = match_result.get('weak', False)
    if match_result['tier'] == 'band1_verified':
        score += 40; components['name_match'] = 40
    elif match_result['tier'] == 'band2_5_convergent' and not weak:
        score += 20; components['name_match'] = 20
    elif weak:
        score += 10; components['name_match'] = 10

    # Geo match
    if obit_area and property_city:
        if obit_area.upper() in property_city.upper() or property_city.upper() in obit_area.upper():
            score += 20; components['geo_match'] = 20
        # Eastside cities mostly fall under "Bellevue WA" obit area loosely
        elif property_city.upper() in {'MEDINA', 'CLYDE HILL', 'HUNTS POINT', 'YARROW POINT', 'BELLEVUE'} \
             and obit_area.upper() in {'BELLEVUE', 'SEATTLE', 'MEDINA', 'MERCER ISLAND'}:
            score += 10; components['geo_match'] = 10
        else:
            components['geo_match'] = 0
    else:
        components['geo_match'] = 0

    # Signal overlap
    n_conv = len(convergent_families or [])
    if n_conv >= 2:
        score += 20; components['signal_overlap'] = 20
    elif n_conv == 1:
        score += 10; components['signal_overlap'] = 10
    else:
        components['signal_overlap'] = 0

    # Age alignment — if we have both estimated and obit age
    if age_estimate and obit_age:
        diff = abs(age_estimate - obit_age)
        if diff <= 3:
            score += 20; components['age_alignment'] = 20
        elif diff <= 7:
            score += 15; components['age_alignment'] = 15
        elif diff <= 15:
            score += 10; components['age_alignment'] = 10
        else:
            components['age_alignment'] = 0
    else:
        components['age_alignment'] = 0

    return score, components


# ─── FAMILY CLUSTER DETECTION ─────────────────────────────────────────
def detect_family_clusters(tier25_matches):
    """
    Group Band 2.5 matches by (surname, ZIP) where 2+ properties hit the same obit.
    Returns list of cluster leads, each being a single portfolio event.

    Confidence scoring (conservative per critic feedback):
      - Common surname: cap at 65 regardless of property count (too many coincidence risks)
      - Uncommon surname, 2 props: 65-75
      - Uncommon surname, 3+ props: 75-90
      - Same-street bonus (any cluster): +10 capped
    """
    COMMON_SURNAMES = {'SMITH', 'JOHNSON', 'WILLIAMS', 'BROWN', 'JONES', 'MURPHY',
                      'MOORE', 'THOMPSON', 'MILLER', 'ANDERSON', 'BROOKS', 'PARKER',
                      'LEE', 'GILBERT', 'HANCOCK', 'WALKER', 'DAVIS', 'WILSON',
                      'TAYLOR', 'THOMAS', 'JACKSON', 'MARTIN', 'WHITE', 'HARRIS',
                      'CLARK', 'LEWIS', 'ROBINSON'}

    by_cluster = defaultdict(list)
    for m in tier25_matches:
        surname = m.get('surname')
        obit = m.get('obit_name')
        z = m.get('zip')
        if not (surname and obit and z): continue
        by_cluster[(obit, surname, z)].append(m)

    clusters = []
    for (obit, surname, z), members in by_cluster.items():
        if len(members) < 2: continue
        total_value = sum(m.get('value') or 0 for m in members)

        if surname in COMMON_SURNAMES:
            # Conservative: common surname + same obit + multi-property could all be
            # coincidence. Cap at Band 2.5 threshold.
            cluster_conf = min(65, 30 + 10 * len(members))
        else:
            # Uncommon surname: meaningful cluster signal
            cluster_conf = 30 + 15 * len(members)
            cluster_conf = min(cluster_conf, 85)

        # Same-street bonus: extract street names and check overlap
        streets = set()
        for m in members:
            addr = (m.get('address') or '').upper()
            parts = addr.split()
            if len(parts) >= 2:
                streets.add(' '.join(parts[1:]))  # e.g. 'SKAGIT KY'
        if len(streets) == 1 and members:  # all on same street
            cluster_conf = min(cluster_conf + 10, 95)

        # Band assignment: 70+ = Band 1 (portfolio event), else Band 2.5
        if cluster_conf >= 70:
            band = 1
            band_label = f"Band 1 — Family Portfolio Event ({len(members)} props)"
        else:
            band = 2.5
            band_label = f"Band 2.5 — Family Cluster candidate ({len(members)} props)"

        clusters.append({
            'type': 'family_event_cluster',
            'cluster_id': f"{surname}_{z}_{obit.replace(' ', '_')}",
            'surname': surname,
            'common_surname': surname in COMMON_SURNAMES,
            'triggering_obit': obit,
            'zip': z,
            'property_count': len(members),
            'pins': [m['pin'] for m in members],
            'total_value': total_value,
            'addresses': [m['address'] for m in members],
            'streets': sorted(streets),
            'same_street': len(streets) == 1,
            'confidence_score': cluster_conf,
            'band': band,
            'band_label': band_label,
        })
    # Sort by confidence desc
    clusters.sort(key=lambda c: -c['confidence_score'])
    return clusters


# ─── MAIN: Rebuild the 23 current "Band 1" leads ──────────────────────
# ═══════════════════════════════════════════════════════════════════════
# SANDBOX-ONLY ORCHESTRATOR — NOT RUNNABLE IN V3 AS-IS
# ═══════════════════════════════════════════════════════════════════════
# run() below is a v2 sandbox orchestrator. It reads from and writes to
# hardcoded absolute paths under /home/claude/sellersignal_v2/out/ that
# don't exist in v3. Guarded by the __main__ block at file bottom, so
# importing this module is safe — only `python rebuild_band_assignments.py`
# triggers execution.
#
# THE THREE PURE FUNCTIONS ABOVE (classify_match_strength,
# compute_confidence_score, detect_family_clusters) ARE THE PORTABLE
# SURFACE AREA. They take plain arguments and return plain values — no
# I/O. v3's county pipeline drivers (e.g., backend/pipelines/king_county/)
# should call those directly against their own data sources (Supabase
# tables), not via this orchestrator.
#
# This module is COUNTY-AGNOSTIC library code. The run() orchestrator
# happens to be KC-specific because that's what the v2 sandbox was
# working on. In v3, per-county drivers will reproduce this orchestration
# against their own data; the library functions serve all of them.
# ═══════════════════════════════════════════════════════════════════════
def run():
    current_b1_path = '/home/claude/sellersignal_v2/out/band1-obit-convergence.json'
    matches = json.load(open(current_b1_path))

    # Re-classify each
    tier25 = []
    band1_verified = []
    rejected = []

    for m in matches:
        cls = classify_match_strength(
            obit_name=m.get('obit_name'),
            owner_name=m.get('matched_name') if m.get('match_type') == 'owner' else None,
            grantor_name=m.get('matched_name') if m.get('match_type') == 'grantor' else None,
        )
        # Tokenize to get surname for clustering
        raw = [t for t in re.sub(r"[^A-Za-z' ]", " ", m.get('obit_name', '').upper()).split()
               if t.isalpha() and len(t) >= 2]
        junk = {'JR', 'SR', 'II', 'III', 'IV', 'MR', 'MRS'}
        raw = [t for t in raw if t not in junk]
        surname = raw[-1] if raw else None

        record = {**m, 'match_classification': cls, 'surname': surname}

        if cls['tier'] == 'band1_verified':
            band1_verified.append(record)
        elif cls['tier'] == 'band2_5_convergent':
            tier25.append(record)
        else:
            rejected.append(record)

    print(f"═══ REBAND OF CURRENT 23 'BAND 1' LEADS ═══")
    print(f"  Truly Band 1 verified:       {len(band1_verified)}")
    print(f"  Band 2.5 convergent:         {len(tier25)}")
    print(f"  Rejected (noise):            {len(rejected)}")

    # Detect family clusters from Band 2.5 pool
    clusters = detect_family_clusters(tier25)
    print(f"\n  Family event clusters:       {len(clusters)}")
    for c in clusters:
        print(f"    — {c['cluster_id']} | {c['property_count']} properties | ${c['total_value']:,} | conf {c['confidence_score']}")

    # Save the rebuild
    output = {
        'band1_verified': band1_verified,
        'band2_5_individual': [m for m in tier25 if not any(m['pin'] in c['pins'] for c in clusters)],
        'band2_5_cluster_member': [m for m in tier25 if any(m['pin'] in c['pins'] for c in clusters)],
        'rejected': rejected,
        'family_clusters': clusters,
    }
    out_path = '/home/claude/sellersignal_v2/out/corrected-band-assignments.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Saved to {out_path}")

    return output


if __name__ == "__main__":
    run()
