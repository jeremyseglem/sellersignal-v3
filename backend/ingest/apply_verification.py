"""
Patch apply_banding.py to read verification status and demote unverified/rejected
obit matches. Run this AFTER apply_banding.py has produced banded-inventory.json.

Rules:
  - verification_status='no_match' AND only signal is obit → REJECT (drop from inventory)
  - verification_status='no_match' AND property has other strong signals → demote to Band 2 or lower
  - verification_status='confirmed_*' → Band 1A (upgrade)
  - verification_status='unverified' → leave as Band 2.5

Produces: banded-inventory-verified.json
"""
import json, os

VERIFICATION_PATH = '/home/claude/sellersignal_v2/out/obit-verification-results.json'
INV_PATH = '/home/claude/sellersignal_v2/out/banded-inventory.json'

inv = json.load(open(INV_PATH))
ver = json.load(open(VERIFICATION_PATH))

# Build verification lookup by (pin, obit_name)
ver_lookup = {}
for r in ver['results']:
    key = (r['pin'], r.get('obit_name'))
    ver_lookup[key] = r

updates = {'upgraded_to_1A': 0, 'demoted_from_25': 0, 'rejected': 0, 'left_as_25': 0, 'cluster_dissolved': 0}
updated_leads = []

# First pass: individual leads
for L in inv['leads']:
    if L.get('signal_family') == 'family_event_cluster':
        # Handle cluster re-evaluation separately below
        updated_leads.append(L)
        continue

    obit = L.get('obit_match')
    if not obit:
        updated_leads.append(L)
        continue

    obit_name = obit.get('obit_name')
    key = (L['pin'], obit_name)
    v = ver_lookup.get(key)
    if not v:
        updated_leads.append(L)
        continue

    status = v['verification_status']
    L['verification_status'] = status
    L['verification_detail'] = v.get('verification_detail', {})
    if 'survivors_parsed' in v:
        L['survivors_parsed'] = v['survivors_parsed']

    if status.startswith('confirmed'):
        L['band'] = 1
        L['band_label'] = 'Band 1A — Verified (survivor/grantor match confirmed)'
        L['inevitability'] = 0.97
        L['timeline_months'] = 9
        L['confidence_score'] = min(L.get('confidence_score', 0) + 30, 100)
        updates['upgraded_to_1A'] += 1
        updated_leads.append(L)
    elif status == 'no_match':
        # Obit explicitly fails; demote. If there are no other strong signals,
        # reject entirely. Otherwise drop to Band 2 on the underlying inference.
        if L.get('signal_family') in ('silent_transition', 'trust_aging', 'dormant_absentee'):
            # Underlying inference signal still valid → recompute band without obit boost
            L['band'] = 2  # treat as regular inference (was artificially 2.5 b/c of obit)
            L['band_label'] = 'Band 2 — Probable + Inevitable (obit rejected)'
            L['inevitability'] = min(L.get('inevitability', 0.6), 0.65)
            L['confidence_score'] = max(L.get('confidence_score', 0) - 20, 25)
            L['obit_match_rejected'] = True
            updates['demoted_from_25'] += 1
            updated_leads.append(L)
        else:
            # No alternate signal; reject
            updates['rejected'] += 1
            # drop from inventory (do not append)
    else:  # unverified
        updates['left_as_25'] += 1
        updated_leads.append(L)

# Second pass: clusters — dissolve any cluster whose members all got rejected
cluster_leads = [L for L in updated_leads if L.get('signal_family') == 'family_event_cluster']
non_cluster = [L for L in updated_leads if L.get('signal_family') != 'family_event_cluster']
final_leads = list(non_cluster)

for cl in cluster_leads:
    cl_pins = cl.get('cluster_member_pins', [])
    # Check if any member had verification=no_match
    any_rejected = False
    all_rejected = True
    for pin in cl_pins:
        # Find the verification result for this pin
        for key, v in ver_lookup.items():
            if key[0] == pin and v['verification_status'] == 'no_match':
                any_rejected = True
            if key[0] == pin and v['verification_status'].startswith('confirmed'):
                all_rejected = False
    if any_rejected and all_rejected:
        # All cluster members verified as no_match → dissolve
        cl['band'] = 0  # rejected
        cl['band_label'] = 'REJECTED — cluster dissolved on verification'
        cl['verification_status'] = 'all_members_rejected'
        updates['cluster_dissolved'] += 1
        # Don't add to final leads
    else:
        final_leads.append(cl)

# Re-count bands
from collections import Counter
band_counts = Counter(L['band'] for L in final_leads)

output = {
    'leads': final_leads,
    'band_counts_by_num': {str(k): v for k, v in sorted(band_counts.items(), key=lambda x: (x[0] == 0, x[0]))},
    'expected_1yr': inv.get('expected_1yr'),
    'verification_updates': updates,
    'verification_summary': ver['summary'],
}
with open('/home/claude/sellersignal_v2/out/banded-inventory-verified.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"Verification-corrected inventory saved: {len(final_leads):,} leads")
print(f"\nUpdates:")
for k, v in updates.items():
    print(f"  {k:30} {v}")
print(f"\nFinal band distribution:")
for band_num, count in sorted(band_counts.items(), key=lambda x: (x[0] == 0, x[0])):
    print(f"  Band {band_num}: {count}")
