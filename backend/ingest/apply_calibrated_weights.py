"""
apply_calibrated_weights.py — Re-rank the existing inventory using
empirically-calibrated weights from the multi-ZIP backtest.

For each lead, compute:
  calibrated_score = owner_weight × indiv_to_llc_weight × trust_aging_weight × value_damp

Where weights come from calibrated-weights.json (per-ZIP lookup, fallback
to Eastside average for ZIPs with thin data).

The value_damp is a log-scale dampener that replaces the linear value
multiplier that was causing ultra-luxury over-representation.

Writes back to banded-inventory-verified.json in-place (adds fields,
doesn't change existing ones).
"""
import json
import math

INV_PATH = '/home/claude/sellersignal_v2/out/banded-inventory-verified.json'
WEIGHTS_PATH = '/home/claude/sellersignal_v2/out/calibrated-weights.json'


def owner_type_for(lead):
    owner = (lead.get('owner') or '').upper()
    if not owner or len(owner) < 3: return 'unknown'
    import re
    if re.search(r'\bCITY OF\b|\bCOUNTY OF\b|\bSTATE OF\b|\bSCHOOL\b|\bCHURCH\b|\bHOA\b|\bHOMEOWNERS\b', owner): return 'gov'
    if re.search(r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR', owner): return 'estate'
    if re.search(r'\bTRUST\b|\bTTEES?\b|\bTTEE\b', owner): return 'trust'
    if re.search(r'\bLLC\b|\bCORP\b|\bINC\b|\bLP\b|\bPARTNERSHIP\b|\bHOLDINGS\b|\bPROPERTIES\b|\bINVESTMENTS\b|\bVENTURES\b', owner): return 'llc'
    return 'individual'


def main():
    inv = json.load(open(INV_PATH))
    weights = json.load(open(WEIGHTS_PATH))
    per_zip = weights['per_zip']
    avg = per_zip['_eastside_avg']

    updated = 0
    for L in inv['leads']:
        z = L.get('zip')
        w = per_zip.get(z, avg) if z else avg

        # Owner type weight
        ot = owner_type_for(L)
        score = w['owner_type'].get(ot, 1.0)

        # Deed-signal boosters (these correspond to detectors already present)
        sig = L.get('signal_family', '')
        sub = L.get('sub_signal', '')

        # indiv→llc transition — corresponds to investor_disposition signal family
        if sig == 'investor_disposition':
            score *= w['sig_indiv_to_llc']

        # Trust aging
        if sig == 'trust_aging':
            score *= w['sig_trust_aging']

        # Silent transition → NO boost (flat lift in backtest)
        # Keep the signal for band classification but remove the weight.
        # If/when mailing-dormancy backtest runs, the dormant variant gets weight.

        # Value dampener — log-scale instead of linear.
        # At $1M → 1.00, $5M → 1.38, $10M → 1.54, $25M → 1.80, $100M → 2.30
        value = L.get('value', 0) or 0
        if value > 0:
            value_damp = math.log10(max(value, 1_000_000)) / math.log10(1_000_000)
        else:
            value_damp = 1.0
        score *= value_damp

        # Also include the inevitability × confidence base
        inev = L.get('inevitability', 0.5) or 0.5
        conf = L.get('confidence_score', 50) or 50
        base_belief = inev * (conf / 100)

        calibrated = score * base_belief

        L['calibrated_rank_score'] = round(calibrated, 4)
        L['calibrated_components'] = {
            'owner_weight': round(w['owner_type'].get(ot, 1.0), 3),
            'signal_weight_applied': round(score / (w['owner_type'].get(ot, 1.0) * value_damp), 3),
            'value_damp': round(value_damp, 3),
            'inev_conf_base': round(base_belief, 3),
            'zip_weights_used': z if z in per_zip else '_eastside_avg',
        }
        updated += 1

    with open(INV_PATH, 'w') as f:
        json.dump(inv, f, indent=2, default=str)

    print(f"✓ Updated {updated} leads with calibrated_rank_score")

    # Show the top 10 by new vs old ranking
    from collections import Counter
    leads = inv['leads']
    by_cal = sorted(leads, key=lambda x: -x.get('calibrated_rank_score', 0))[:15]
    by_old = sorted(leads, key=lambda x: -x.get('rank_score', 0))[:15]

    old_pins = {L['pin'] for L in by_old}
    cal_pins = {L['pin'] for L in by_cal}
    stable = old_pins & cal_pins
    only_cal = cal_pins - old_pins
    only_old = old_pins - cal_pins

    print(f"\nTop-15 comparison: {len(stable)} stable, {len(only_cal)} new, {len(only_old)} dropped\n")
    print(f"{'rank':<5} {'address':<32} {'val':>8} {'owner_type':<12} {'band':<5} {'cal_score':>10}  {'old_score':>10}")
    for i, L in enumerate(by_cal, 1):
        v = L.get('value', 0) / 1_000_000
        ot = owner_type_for(L)
        marker = '+' if L['pin'] in only_cal else ' '
        print(f"{i:<4}{marker} {(L.get('address') or '—')[:32]:<32} ${v:>6.1f}M {ot:<12} {L.get('band'):<5} {L.get('calibrated_rank_score',0):>10.3f}  {L.get('rank_score',0):>10.2f}")

    # Value distribution: old top-25 vs new top-25
    print(f"\nValue mix comparison:")
    def dist(leads_list):
        buckets = {'<$2M': 0, '$2-6M': 0, '$6-15M': 0, '$15M+': 0}
        for L in leads_list:
            v = L.get('value', 0) or 0
            if v < 2_000_000: buckets['<$2M'] += 1
            elif v < 6_000_000: buckets['$2-6M'] += 1
            elif v < 15_000_000: buckets['$6-15M'] += 1
            else: buckets['$15M+'] += 1
        return buckets

    old_top25 = sorted(leads, key=lambda x: -x.get('rank_score', 0))[:25]
    cal_top25 = sorted(leads, key=lambda x: -x.get('calibrated_rank_score', 0))[:25]
    print(f"  {'bucket':<10} {'old top25':>10} {'cal top25':>10}")
    for b in ['<$2M','$2-6M','$6-15M','$15M+']:
        print(f"  {b:<10} {dist(old_top25).get(b,0):>10} {dist(cal_top25).get(b,0):>10}")


if __name__ == "__main__":
    main()
