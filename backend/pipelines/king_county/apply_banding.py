"""
SellerSignal v3 — King County apply_banding orchestrator (v2 reference port).

This is the v2 KC-specific banding orchestrator preserved verbatim as a
specification reference. It hardcodes King County paths, KC-specific ZIP
lists, and the v2 sandbox output directory.

STATUS: NOT RUNNABLE IN V3 AS-IS.
The filesystem paths this script reads from (/home/claude/kc-data/,
/home/claude/eastside-tier2/, /home/claude/sellersignal_v2/out/) only
exist in the v2 sandbox. Importing this module is safe — the procedural
body is wrapped in run_98004_banding() and guarded by __main__.

PURPOSE:
  1. Specification — documents exactly how v2 banded the 98004 + Eastside
     Tier-2 inventory to produce the 2026-04-18 14:36 UTC briefing.
  2. Migration target — when v3's KC orchestrator is written against
     Supabase, this file is the diff target. V3 version is correct when
     it produces identical banded output for 98004.

V3 orchestration is deferred. Current focus: test 98004 logic flow end-
to-end in v2 first, then rewrite this to read from Supabase tables and
cover all of King County once the 98004 pipeline is proven.
"""
import json, os, math
from collections import Counter, defaultdict

from backend.pipeline.banding import classify_lead, rank_score, SIGNAL_PROFILES


def run_98004_banding():
    """
    Execute the v2 KC banding flow for 98004 + Eastside Tier-2 ZIPs.
    Requires the v2 sandbox data files at /home/claude/... paths.

    Load everything we have, apply rationality + banding, produce the reranked inventory.
    """
    # ─── LOAD ─────────────────────────────────────────────────────────────
    leads_all = []

    # 98004 failed-sale + financial-stress (from existing pipeline output)
    manifest = json.load(open('/home/claude/sellersignal_v2/out/briefing-manifest.json'))
    for L in manifest['leads']:
        fam = L['signal_family']
        sub = ''
        if fam == 'financial_stress':
            for ev in L.get('supporting_evidence', []):
                d = (ev.get('description') or '').upper()
                if 'TRUSTEE SALE' in d: sub = 'trustee_sale'; break
                if 'DEFAULT' in d: sub = 'nod'; break
                if 'LIS PENDENS' in d: sub = 'lis_pendens'; break
        elif fam == 'failed_sale_attempt':
            # Run the partial rationality scorer against the lead's Zillow-events data
            # to determine if this is a PRIME/CAUTION/REJECT expired listing.
            from backend.pipeline.rationality_index import score_rationality_partial
            from datetime import datetime as _dt

            # Pull the events record for this PIN
            pin = L['parcel_id']
            zillow_events_path = '/home/claude/kc-data/bellevue-98004-zillow-events.json'
            orig_price = latest_price = listing_start = listing_end = None
            try:
                all_events = json.load(open(zillow_events_path))
                evs = all_events.get(pin, [])
                for e in evs:
                    if e['event_type'] == 'listed_for_sale':
                        orig_price = e.get('price')
                        listing_start = _dt.strptime(e['date'], '%Y-%m-%d')
                    elif e['event_type'] == 'price_change':
                        latest_price = e.get('price')
                    elif e['event_type'] == 'listing_removed':
                        listing_end = _dt.strptime(e['date'], '%Y-%m-%d')
                        if latest_price is None:
                            latest_price = e.get('price')
                if latest_price is None:
                    latest_price = orig_price
            except (FileNotFoundError, KeyError):
                pass

            # 98004 luxury SFR median value baseline (computed from owners.json: median $3.12M)
            zip_median_98004 = 3_123_000
            rat = score_rationality_partial(
                orig_price=orig_price,
                latest_price=latest_price,
                listing_start=listing_start,
                listing_end=listing_end,
                zip_median_value=zip_median_98004,
                zip_median_dom=90,
            )
            # Map rationality band to sub-signal used by banding.py
            if rat.score < 4: sub = 'reject'
            elif rat.score < 7: sub = 'caution'
            else: sub = 'prime'
            # Stash the score so we can save it on the output
            L['_rationality_score'] = rat.score
            L['_rationality_flags'] = rat.flags
            L['_rationality_recommendation'] = rat.recommendation
        elif fam == 'investor_disposition':
            # Check supporting evidence for 'overdue' flag
            sub = 'in_window'
            for ev in L.get('supporting_evidence', []):
                d = (ev.get('description') or '').upper()
                if 'OVERDUE' in d: sub = 'overdue'; break
        elif fam == 'death_inheritance':
            sub = 'obit_matched_no_probate'  # default unless probate evidence found
            for ev in L.get('supporting_evidence', []):
                d = (ev.get('description') or '').upper()
                if 'PROBATE' in d: sub = 'probate_filed'; break
        leads_all.append({
            'pin': L['parcel_id'],
            'address': L['address'],
            'zip': '98004',
            'owner': L['current_owner'],
            'value': L['value'] or 0,
            'signal_family': fam,
            'sub_signal': sub,
            'source': 'tier1_pipeline',
            'rationality_score': L.get('_rationality_score'),
            'rationality_flags': L.get('_rationality_flags', []),
            'rationality_recommendation': L.get('_rationality_recommendation'),
        })

    # Eastside Tier-2: silent, trust, dormant across all 5 ZIPs
    EASTSIDE = '/home/claude/eastside-tier2'
    ZIPS = ['98039', '98040', '98033', '98006', '98005']
    zip_labels = {'98039': 'Medina', '98040': 'Mercer Island',
                  '98033': 'Kirkland', '98006': 'Newport/Somerset',
                  '98005': 'Bridle Trails'}

    # Also include 98004 Tier-2 (from earlier build)
    files_98004 = [
        ('/home/claude/kc-data/bellevue-98004-silent-transition.json', 'silent_transition', '98004'),
        ('/home/claude/kc-data/bellevue-98004-trust-aging.json', 'trust_aging', '98004'),
        ('/home/claude/kc-data/bellevue-98004-dormant-absentee.json', 'dormant_absentee', '98004'),
    ]
    for path, fam, z in files_98004:
        if not os.path.exists(path): continue
        data = json.load(open(path))
        for L in data:
            owner = L.get('owner') or ''
            sub = ''
            age = None
            if fam == 'silent_transition':
                age = L.get('est_current_age') or L.get('est_age')
            elif fam == 'trust_aging':
                age = L.get('est_grantor_age')
            elif fam == 'dormant_absentee':
                age = L.get('est_age')
            # Sub-signal bucketing by age
            if age is not None:
                if age >= 80: sub = 'age_80plus' if fam == 'silent_transition' else ('grantor_80plus' if fam == 'trust_aging' else 'oos_aging')
                elif age >= 75: sub = 'age_75_79' if fam == 'silent_transition' else ('grantor_75_79' if fam == 'trust_aging' else 'oos_aging')
                elif age >= 70: sub = 'age_70_74' if fam == 'silent_transition' else ('grantor_65_74' if fam == 'trust_aging' else 'local_aging')
                elif age >= 65: sub = 'age_65_69' if fam == 'silent_transition' else ('grantor_65_74' if fam == 'trust_aging' else 'local_aging')
            # Fix dormant subclassing
            if fam == 'dormant_absentee':
                sub = 'oos_aging' if L.get('out_of_state') else 'local_aging'
            leads_all.append({
                'pin': L['pin'], 'address': L.get('address') or '',
                'zip': z, 'owner': owner,
                'value': L.get('value') or 0,
                'signal_family': fam, 'sub_signal': sub,
                'est_age': age,
                'source': 'tier2_98004',
                'grantor': L.get('grantor') or L.get('grantor_prior_name', ''),
                'mail_street': L.get('mail_street'),
                'mail_city': L.get('mail_city'),
            })

    # Now eastside ZIPs
    for z in ZIPS:
        for signal, fam in [('silent', 'silent_transition'), ('trust', 'trust_aging'), ('dormant', 'dormant_absentee')]:
            path = f'{EASTSIDE}/{z}-{signal}.json'
            if not os.path.exists(path): continue
            data = json.load(open(path))
            for L in data:
                owner = L.get('owner') or ''
                age = L.get('est_age') or L.get('est_grantor_age')
                sub = ''
                if fam == 'silent_transition' and age:
                    sub = 'age_80plus' if age >= 80 else ('age_75_79' if age >= 75 else ('age_70_74' if age >= 70 else 'age_65_69'))
                elif fam == 'trust_aging' and age:
                    sub = 'grantor_80plus' if age >= 80 else ('grantor_75_79' if age >= 75 else 'grantor_65_74')
                elif fam == 'dormant_absentee':
                    sub = 'oos_aging' if L.get('out_of_state') else 'local_aging'
                leads_all.append({
                    'pin': L['pin'], 'address': L.get('address') or '',
                    'zip': z, 'owner': owner,
                    'value': L.get('value') or 0,
                    'signal_family': fam, 'sub_signal': sub,
                    'est_age': age,
                    'source': f'tier2_eastside',
                    'grantor': L.get('grantor', ''),
                    'mail_street': L.get('mail_street'),
                    'mail_city': L.get('mail_city'),
                })

    print(f"Total leads pre-filtering: {len(leads_all):,}")
    print(f"  by source: {Counter(L['source'] for L in leads_all)}")

    # ─── DETECT CONVERGENCE ───────────────────────────────────────────────
    # Same pin with ≥2 signal families = convergent
    by_pin = defaultdict(list)
    for L in leads_all:
        by_pin[L['pin']].append(L)

    convergent_pins = {pin: [L['signal_family'] for L in lst] for pin, lst in by_pin.items() if len(set(L['signal_family'] for L in lst)) >= 2}
    print(f"Convergent parcels (≥2 signal families): {len(convergent_pins)}")

    # ─── STRICT BAND-1 CLASSIFIER + CLUSTER DETECTION (post-critic) ──────
    # Uses rebuild_band_assignments module for strict verified classification.
    from backend.pipeline.rebuild_band_assignments import (
        classify_match_strength, compute_confidence_score, detect_family_clusters
    )

    # Load raw obit→Tier-2 match output
    band1_obit_matches = {}
    band1_path = '/home/claude/sellersignal_v2/out/band1-obit-convergence.json'
    if os.path.exists(band1_path):
        for m in json.load(open(band1_path)):
            pin = m['pin']
            # Apply STRICT classifier to decide tier
            owner_name = m.get('matched_name') if m.get('match_type') == 'owner' else None
            grantor_name = m.get('matched_name') if m.get('match_type') == 'grantor' else None
            cls = classify_match_strength(
                obit_name=m.get('obit_name'),
                owner_name=owner_name,
                grantor_name=grantor_name,
            )
            # Extract surname for cluster detection
            import re as _re
            raw = [t for t in _re.sub(r"[^A-Za-z' ]", " ", m.get('obit_name', '').upper()).split()
                   if t.isalpha() and len(t) >= 2 and t not in {'JR', 'SR', 'II', 'III', 'IV'}]
            surname = raw[-1] if raw else None
            m['match_classification'] = cls
            m['surname'] = surname
            # Only keep non-rejected; prefer stronger over weaker per pin
            if cls['tier'] == 'reject': continue
            tier_rank = {'band1_verified': 0, 'band2_5_convergent': 1}
            if pin not in band1_obit_matches or tier_rank[cls['tier']] < tier_rank[band1_obit_matches[pin]['match_classification']['tier']]:
                band1_obit_matches[pin] = m
        print(f"Strict obit matches: {len(band1_obit_matches)}")
        b1_verified = sum(1 for m in band1_obit_matches.values() if m['match_classification']['tier'] == 'band1_verified')
        b25 = sum(1 for m in band1_obit_matches.values() if m['match_classification']['tier'] == 'band2_5_convergent')
        print(f"  band1_verified (true Band 1):   {b1_verified}")
        print(f"  band2_5_convergent:             {b25}")

    # Detect family clusters across the Band 2.5 matches
    tier25_for_clustering = [m for m in band1_obit_matches.values()
                            if m['match_classification']['tier'] == 'band2_5_convergent']
    clusters = detect_family_clusters(tier25_for_clustering)
    print(f"\nFamily clusters detected: {len(clusters)}")
    cluster_pins = set()
    for c in clusters:
        cluster_pins.update(c['pins'])
        print(f"  {c['cluster_id']:55} | {c['property_count']} props | ${c['total_value']:>12,} | conf {c['confidence_score']} | Band {c['band']}")


    # ─── BAND EACH INDIVIDUAL LEAD ───────────────────────────────────────
    banded = []
    for L in leads_all:
        conv_signals = [s for s in convergent_pins.get(L['pin'], []) if s != L['signal_family']]
        inev, timeline, band, band_label = classify_lead(
            L['signal_family'], L.get('sub_signal', ''),
            rationality=L.get('rationality_score'),
            convergent_signals=conv_signals,
            owner_age=L.get('est_age'),
        )

        # STRICT obit-based band assignment
        obit_match = band1_obit_matches.get(L['pin'])
        cls_tier = obit_match['match_classification']['tier'] if obit_match else None

        if cls_tier == 'band1_verified' and L['signal_family'] in ('silent_transition', 'trust_aging', 'dormant_absentee'):
            band, band_label = 1, 'Band 1 — Verified (strong obit match)'
            inev = max(inev, 0.95)
            timeline = min(timeline, 12)
            L['obit_match'] = obit_match
        elif cls_tier == 'band2_5_convergent' and L['signal_family'] in ('silent_transition', 'trust_aging', 'dormant_absentee'):
            # Band 2.5 only if NOT already in a stronger cluster
            if L['pin'] not in cluster_pins:
                band, band_label = 2.5, 'Band 2.5 — Convergent Event Candidate'
                inev = max(inev, 0.65)
                # Keep original timeline — convergent candidates aren't accelerated
                L['obit_match'] = obit_match

        # Compute confidence score (0-100)
        if obit_match:
            age_est = L.get('est_age')
            obit_age = obit_match.get('obit_age')
            obit_area = obit_match.get('obit_area')
            conf_score, conf_components = compute_confidence_score(
                match_result=obit_match['match_classification'],
                age_estimate=age_est,
                obit_age=obit_age,
                obit_area=obit_area,
                property_zip=L.get('zip'),
                property_city=L.get('zip'),  # proxy; we have zip not city here
                convergent_families=conv_signals,
            )
        else:
            # No obit — confidence derives from signal strength only
            base = 40  # inference-only baseline
            if len(conv_signals) >= 2: base += 30
            elif len(conv_signals) == 1: base += 15
            if L.get('est_age') and L['est_age'] >= 80: base += 15
            elif L.get('est_age') and L['est_age'] >= 75: base += 10
            conf_score = min(base, 85)  # inference-only can't exceed 85; reserve 85-100 for obit-verified
            conf_components = {'signal_base': conf_score}

        # NEW RANK FORMULA: inevitability × (confidence/100) × value
        value = L.get('value') or 0
        new_rank = inev * (conf_score / 100) * (value / 1_000_000)

        banded.append({
            **L,
            'inevitability': inev,
            'timeline_months': timeline,
            'band': band,
            'band_label': band_label,
            'confidence_score': conf_score,
            'confidence_components': conf_components,
            'convergent_families': list(set(conv_signals)),
            'rank_score': new_rank,
            'in_cluster': L['pin'] in cluster_pins,
        })


    # ─── EMIT CLUSTER LEADS as new lead records ──────────────────────────
    for c in clusters:
        # Gather the underlying individual lead records
        members = [L for L in banded if L['pin'] in c['pins']]
        total_value = c['total_value']
        # Cluster inevitability is the MAX of any member (portfolio event is at least as certain as its strongest member)
        cluster_inev = max((m['inevitability'] for m in members), default=0.7)
        cluster_rank = cluster_inev * (c['confidence_score'] / 100) * (total_value / 1_000_000)
        banded.append({
            'pin': f"CLUSTER_{c['cluster_id']}",
            'address': ' + '.join(c['addresses'][:3]) + (f" (+{len(c['addresses'])-3} more)" if len(c['addresses']) > 3 else ''),
            'zip': c['zip'],
            'owner': f"{c['surname']} family — {c['property_count']} properties",
            'value': total_value,
            'signal_family': 'family_event_cluster',
            'sub_signal': f"cluster_{c['property_count']}prop",
            'inevitability': cluster_inev,
            'timeline_months': 12,
            'band': c['band'],
            'band_label': c['band_label'],
            'confidence_score': c['confidence_score'],
            'convergent_families': ['family_cluster'],
            'rank_score': cluster_rank,
            'cluster_data': c,
            'cluster_member_pins': c['pins'],
            'source': 'cluster_rollup',
        })
    print(f"Emitted {len(clusters)} cluster leads")

    # Dedupe: if same pin has multiple entries, keep the one with the best band (lowest number, with REJECT as highest number)
    def band_sort_key(b):
        return (b == 0, b)  # REJECT (0) goes last
    best_by_pin = {}
    for L in banded:
        p = L['pin']
        if p not in best_by_pin:
            best_by_pin[p] = L
        else:
            cur = best_by_pin[p]
            # Prefer better band. Tied band → higher rank_score
            if (band_sort_key(L['band']), -L['rank_score']) < (band_sort_key(cur['band']), -cur['rank_score']):
                best_by_pin[p] = L
    final = list(best_by_pin.values())
    print(f"After dedupe: {len(final):,}")

    # ─── RESULTS ─────────────────────────────────────────────────────────
    # Group by band number (not label, since Band 1 has 3 confidence variants)
    band_num_counts = Counter(L['band'] for L in final)
    band_label_counts = Counter(L['band_label'] for L in final)
    print(f"\nBand distribution:")
    band_order = [
        (1, '🔴 Band 1 — Verified / Portfolio Event'),
        (2, '🟣 Band 2 — Probable + Inevitable'),
        (2.5, '🟡 Band 2.5 — Convergent Event Candidate'),
        (3, '🟠 Band 3 — Imminent + Escapable'),
        (4, '🟢 Band 4 — Long-Cycle Cultivation'),
        (0, '❌ REJECTED'),
    ]
    for num, label in band_order:
        c = band_num_counts.get(num, 0)
        print(f"  {label:55} {c:>5}")

    # Band 1 sub-breakdown
    b1_leads = [L for L in final if L['band'] == 1]
    if b1_leads:
        print(f"\n  Band 1 confidence breakdown:")
        for lbl, c in Counter(L['band_label'] for L in b1_leads).most_common():
            print(f"    {lbl:55} {c:>3}")

    # Expected transitions next year (sum of inevitability-weighted timeline fraction)
    exp_1yr = sum(L['inevitability'] * min(12 / L['timeline_months'], 1.0)
                  for L in final if L['band'] > 0)
    print(f"\nExpected transitions next 12 months from banded inventory: {exp_1yr:.0f}")

    # ─── TOP ENTRIES PER BAND ────────────────────────────────────────────
    final.sort(key=lambda x: (band_sort_key(x['band']), -x['rank_score']))

    for band_num, label in [
        (1, "🔴 BAND 1 — IMMINENT + INEVITABLE"),
        (2, "🟣 BAND 2 — PROBABLE + INEVITABLE"),
        (3, "🟠 BAND 3 — IMMINENT + ESCAPABLE"),
        (4, "🟢 BAND 4 — LONG-CYCLE CULTIVATION"),
    ]:
        band_leads = [L for L in final if L['band'] == band_num]
        if not band_leads:
            print(f"\n{label} — (0 leads)")
            continue
        print(f"\n\n═══ {label} — {len(band_leads)} leads, showing top 12 ═══")
        print(f"{'#':3} {'ZIP':5} {'Address':38} {'Value':>11} {'Inev':>5} {'Tmln':>5} {'Signal'}")
        print("─" * 130)
        for i, L in enumerate(band_leads[:12], 1):
            conv_suffix = f" ⊕ {','.join(f[:6] for f in L['convergent_families'])}" if L['convergent_families'] else ''
            print(f"{i:2}. {L['zip']} {L['address'][:36]:38} ${L['value']:>9,}  {L['inevitability']*100:>3.0f}% {L['timeline_months']:>3}mo  {L['signal_family']}/{L.get('sub_signal', '')[:12]}{conv_suffix}")
            if L['owner']:
                print(f"     {L['owner'][:80]}")
            if L.get('grantor'):
                print(f"     grantor: {L['grantor'][:70]}")
            elif L.get('mail_street'):
                print(f"     mails: {L['mail_street']}, {L.get('mail_city','')}")

    # Save for briefing
    with open('/home/claude/sellersignal_v2/out/banded-inventory.json', 'w') as f:
        json.dump({'leads': final, 'band_counts': dict(band_label_counts),
                   'expected_1yr': round(exp_1yr)}, f, indent=2, default=str)
    print(f"\n✓ Saved to banded-inventory.json")

if __name__ == "__main__":
    run_98004_banding()
