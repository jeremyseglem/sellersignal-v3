"""
Multi-cutoff backtest — the All Souls calibration pilot.

For each T_0 in [2016, 2017, 2018, 2019, 2021]:
  1. Rebuild feature vector for every 98004 parcel as of that date (from deed chain only — mailing address at historical date isn't available)
  2. Check: did the parcel sell in the 24 months AFTER T_0?
  3. Compute per-signal lift = P(sold | signal) / P(sold | all)

Training: 2016-2019 (pre-Covid, rate environment similar to 2024-2026)
Holdout:  2021 (predicts 2023 sales — post-Covid normalizing market)

Signals tested (deed-derivable only, no mailing-address-dependent):
  - Owner type at T_0
  - Tenure bucket at T_0
  - Deed-chain events in prior 24mo: estate origin, quit claim, rapid turnover
  - Owner-type transitions in prior 5yr: indiv→trust, indiv→llc, trust→indiv
  - Value bucket (current, used as proxy since historical value not available)

What's NOT tested (needs historical mailing data we don't have):
  - Absentee status
  - Portfolio clustering
  - Dormant absentee signal family

Output: backtest-multi-cutoff.json with per-T_0 lifts and stability comparison.
"""
import csv, json, re, os, time
from datetime import datetime, timedelta
from collections import defaultdict, Counter

SALES_CSV = '/home/claude/kc-data/EXTR_RPSale.csv'
OWNER_DB = '/home/claude/kc-data/bellevue-98004-owners.json'
OUT_PATH = '/home/claude/sellersignal_v2/out/backtest-multi-cutoff.json'

# Cutoff dates + 24-month forward windows
CUTOFFS = [
    ('2016-01-01', 'training'),
    ('2017-01-01', 'training'),
    ('2018-01-01', 'training'),
    ('2019-01-01', 'training'),
    ('2021-01-01', 'holdout'),   # predicts 2023 sales — normalized post-Covid
]
FORWARD_MONTHS = 24

# Helpers from existing backtest
def classify_owner(name):
    if not name or len(name) < 3: return 'unknown'
    n = name.upper()
    if re.search(r'\bCITY OF\b|\bCOUNTY OF\b|\bSTATE OF\b|\bSCHOOL\b|\bCHURCH\b|\bHOA\b|\bHOMEOWNERS\b', n): return 'gov'
    if re.search(r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR', n): return 'estate'
    if re.search(r'\bTRUST\b|\bTTEES?\b|\bTTEE\b', n): return 'trust'
    if re.search(r'\bLLC\b|\bCORP\b|\bINC\b|\bLP\b|\bPARTNERSHIP\b|\bHOLDINGS\b|\bPROPERTIES\b|\bINVESTMENTS\b|\bVENTURES\b', n): return 'llc'
    return 'individual'


def tenure_bucket(years):
    if years is None: return 'unknown'
    if years < 2: return '0-2yr'
    if years < 5: return '2-5yr'
    if years < 10: return '5-10yr'
    if years < 15: return '10-15yr'
    if years < 20: return '15-20yr'
    if years < 30: return '20-30yr'
    return '30+yr'


def value_bucket(v):
    if not v or v < 500_000: return 'under_500k'
    if v < 1_000_000: return '500k_1m'
    if v < 3_000_000: return '1m_3m'
    if v < 5_000_000: return '3m_5m'
    if v < 10_000_000: return '5m_10m'
    return '10m_plus'


# ── STEP 1: Load 98004 parcel set ────────────────────────────────────
t_start = time.time()
print(f"[{datetime.now():%H:%M:%S}] Loading 98004 parcel set...")
owners = json.load(open(OWNER_DB))
# PIN format in owners: zero-padded 10 digits
target_pins = set(owners.keys())
# Current value lookup (used as proxy for historical value)
value_lookup = {pin: o.get('value', 0) or 0 for pin, o in owners.items()}
print(f"  {len(target_pins):,} parcels")


# ── STEP 2: Stream deed chain for these parcels ──────────────────────
print(f"[{datetime.now():%H:%M:%S}] Streaming EXTR_RPSale (2.4M rows, filtering to 98004)...")
sales_by_pin = defaultdict(list)
with open(SALES_CSV, encoding='latin-1') as f:
    rdr = csv.DictReader(f)
    for row in rdr:
        pin = f"{row['Major'].strip().zfill(6)}{row['Minor'].strip().zfill(4)}"
        if pin not in target_pins: continue
        try:
            dt = datetime.strptime(row['DocumentDate'].strip(), '%m/%d/%Y')
        except ValueError:
            continue
        try:
            price = int(row['SalePrice'])
        except (ValueError, TypeError):
            price = 0
        sales_by_pin[pin].append({
            'date': dt,
            'buyer': (row.get('BuyerName') or '').strip(),
            'seller': (row.get('SellerName') or '').strip(),
            'price': price,
            'instrument': (row.get('SaleInstrument') or '').strip(),
            'reason': (row.get('SaleReason') or '').strip(),
        })
for pin in sales_by_pin:
    sales_by_pin[pin].sort(key=lambda s: s['date'])
n_with_history = sum(1 for p in target_pins if sales_by_pin.get(p))
print(f"  {n_with_history:,} / {len(target_pins):,} parcels have deed history  ({time.time()-t_start:.0f}s)")


# ── STEP 3: Feature reconstruction per T_0 ───────────────────────────
def build_features_at(T_0):
    """For each target parcel, compute its feature vector as of T_0 from deed chain only."""
    forward_end = T_0 + timedelta(days=FORWARD_MONTHS * 30)
    features = {}
    for pin in target_pins:
        chain = sales_by_pin.get(pin, [])
        pre = [s for s in chain if s['date'] <= T_0]
        post_window = [s for s in chain if T_0 < s['date'] <= forward_end]

        if not pre:
            # No deed history before T_0; tenure unknown. Still include but flag.
            owner_at = ''
            owner_type = 'unknown'
            tenure_yrs = None
        else:
            last_pre = pre[-1]
            owner_at = last_pre['buyer']
            owner_type = classify_owner(owner_at)
            tenure_yrs = (T_0 - last_pre['date']).days / 365.25

        if owner_type == 'gov':
            continue

        # Deed-chain event signals (pre-T_0 only)
        recent_window = T_0 - timedelta(days=730)
        five_yr = T_0 - timedelta(days=365*5)
        recent_pre = [s for s in pre if s['date'] >= recent_window]

        sig_estate_origin = bool(pre) and bool(re.search(
            r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR',
            pre[-1]['seller'].upper()))
        sig_quit_claim_24 = any(
            s['instrument']=='3' or 'QUIT' in s['reason'].upper() or (0 < s['price'] < 10000)
            for s in recent_pre)
        sig_rapid_turnover = len(recent_pre) >= 3

        sig_indiv_to_trust = sig_indiv_to_llc = sig_trust_to_indiv = False
        if len(pre) >= 2 and pre[-1]['date'] >= five_yr:
            t_last = classify_owner(pre[-1]['buyer'])
            t_prev = classify_owner(pre[-2]['buyer'])
            if t_prev == 'individual' and t_last == 'trust': sig_indiv_to_trust = True
            elif t_prev == 'individual' and t_last == 'llc': sig_indiv_to_llc = True
            elif t_prev == 'trust' and t_last == 'individual': sig_trust_to_indiv = True

        # Derived v2 signal families (deed-only subset):
        sig_silent_transition = (owner_type == 'individual' and
                                 tenure_yrs is not None and tenure_yrs >= 20)
        sig_trust_aging = (owner_type == 'trust' and
                           tenure_yrs is not None and tenure_yrs >= 10)
        sig_investor_disposition = (owner_type == 'llc' and
                                    tenure_yrs is not None and tenure_yrs >= 5)

        # Outcome: any sale in forward window, excluding intra-family transfers
        #   (excise-exempt transfers under $10k are noise, not real sales)
        real_sales_in_window = [s for s in post_window if s['price'] >= 100_000]
        sold = len(real_sales_in_window) > 0

        features[pin] = {
            'owner_type': owner_type,
            'tenure_bucket': tenure_bucket(tenure_yrs),
            'tenure_yrs': tenure_yrs,
            'value_bucket': value_bucket(value_lookup.get(pin, 0)),
            'sig_estate_origin': sig_estate_origin,
            'sig_quit_claim_24mo': sig_quit_claim_24,
            'sig_rapid_turnover_24mo': sig_rapid_turnover,
            'sig_indiv_to_trust_5yr': sig_indiv_to_trust,
            'sig_indiv_to_llc_5yr': sig_indiv_to_llc,
            'sig_trust_to_indiv_5yr': sig_trust_to_indiv,
            'sig_silent_transition': sig_silent_transition,
            'sig_trust_aging': sig_trust_aging,
            'sig_investor_disposition': sig_investor_disposition,
            'sold_in_window': sold,
        }
    return features


def compute_lifts(features, min_n=20):
    """Per-segment lift vs base rate."""
    n = len(features)
    if n == 0: return None
    n_sold = sum(1 for f in features.values() if f['sold_in_window'])
    base = n_sold / n if n else 0

    def seg_stat(predicate):
        seg = [f for f in features.values() if predicate(f)]
        if len(seg) < min_n: return None
        s = sum(1 for f in seg if f['sold_in_window'])
        r = s / len(seg)
        lift = r / base if base > 0 else 0
        return {'n': len(seg), 'sold': s, 'rate': r, 'lift': lift}

    out = {
        'n_parcels': n,
        'n_sold': n_sold,
        'base_rate': base,
        'owner_type': {
            t: seg_stat(lambda f, tt=t: f['owner_type']==tt)
            for t in ['individual','trust','llc','estate','unknown']
        },
        'tenure': {
            b: seg_stat(lambda f, bb=b: f['tenure_bucket']==bb)
            for b in ['0-2yr','2-5yr','5-10yr','10-15yr','15-20yr','20-30yr','30+yr','unknown']
        },
        'value': {
            b: seg_stat(lambda f, bb=b: f['value_bucket']==bb)
            for b in ['under_500k','500k_1m','1m_3m','3m_5m','5m_10m','10m_plus']
        },
        'deed_signals': {
            sig: seg_stat(lambda f, ss=sig: f[ss])
            for sig in ['sig_estate_origin','sig_quit_claim_24mo','sig_rapid_turnover_24mo',
                        'sig_indiv_to_trust_5yr','sig_indiv_to_llc_5yr','sig_trust_to_indiv_5yr']
        },
        'v2_signals': {
            sig: seg_stat(lambda f, ss=sig: f[ss])
            for sig in ['sig_silent_transition','sig_trust_aging','sig_investor_disposition']
        },
    }
    return out


# ── STEP 4: Run for each cutoff ──────────────────────────────────────
print(f"\n[{datetime.now():%H:%M:%S}] Running backtest at each cutoff...")
results = {}
for cutoff_str, fold in CUTOFFS:
    T_0 = datetime.strptime(cutoff_str, '%Y-%m-%d')
    t1 = time.time()
    feats = build_features_at(T_0)
    lifts = compute_lifts(feats)
    if not lifts:
        print(f"  T_0={cutoff_str}: no parcels — skipped")
        continue
    results[cutoff_str] = {
        'fold': fold,
        'T_0': cutoff_str,
        'forward_window_end': (T_0 + timedelta(days=FORWARD_MONTHS*30)).strftime('%Y-%m-%d'),
        **lifts,
    }
    br = lifts['base_rate'] * 100
    print(f"  T_0={cutoff_str} ({fold:8}) n={lifts['n_parcels']:>4} "
          f"sold={lifts['n_sold']:>4} base={br:.2f}%  ({time.time()-t1:.1f}s)")


# ── STEP 5: Stability comparison — training avg vs holdout ───────────
print(f"\n[{datetime.now():%H:%M:%S}] Computing stability comparison...")
training = [r for r in results.values() if r['fold'] == 'training']
holdout = [r for r in results.values() if r['fold'] == 'holdout']

def avg_lift(runs, category, subcategory):
    lifts = []
    for r in runs:
        s = r.get(category, {}).get(subcategory)
        if s and s.get('lift'):
            lifts.append(s['lift'])
    return sum(lifts) / len(lifts) if lifts else None


stability = {}
for category in ['owner_type', 'tenure', 'value', 'deed_signals', 'v2_signals']:
    subs = set()
    for r in training + holdout:
        subs.update(r.get(category, {}).keys())
    stability[category] = {}
    for sub in subs:
        tr_avg = avg_lift(training, category, sub)
        ho = holdout[0].get(category, {}).get(sub) if holdout else None
        ho_lift = ho['lift'] if ho else None
        if tr_avg is not None and ho_lift is not None:
            stability[category][sub] = {
                'training_avg_lift': round(tr_avg, 3),
                'holdout_lift': round(ho_lift, 3),
                'holdout_n': ho['n'] if ho else 0,
                'holdout_sold': ho['sold'] if ho else 0,
                'drift': round(ho_lift - tr_avg, 3),
            }

# Save
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, 'w') as f:
    json.dump({
        'zip': '98004',
        'cutoffs': CUTOFFS,
        'forward_months': FORWARD_MONTHS,
        'per_cutoff': results,
        'stability': stability,
        'generated_at': datetime.now().isoformat(),
    }, f, indent=2, default=str)

print(f"\n✓ {OUT_PATH}")
print(f"  Total time: {time.time()-t_start:.0f}s\n")

# ── STEP 6: Human-readable summary ───────────────────────────────────
print("═══ STABILITY SUMMARY — training (2016-2019) vs holdout (2021) ═══\n")

def show_cat(name, subcat_filter=None):
    print(f"── {name} ──")
    print(f"  {'signal':<28} {'train lift':>11} {'holdout':>8}  {'drift':>6}  {'n(hold)':>7}")
    for sub, s in sorted(stability.get(name, {}).items(), key=lambda x: -(x[1].get('training_avg_lift') or 0)):
        if subcat_filter and sub not in subcat_filter: continue
        if s['training_avg_lift'] is None: continue
        print(f"  {sub:<28} {s['training_avg_lift']:>10.2f}x {s['holdout_lift']:>7.2f}x  {s['drift']:>+6.2f}  {s['holdout_n']:>7}")
    print()

show_cat('owner_type', {'individual','trust','llc','estate'})
show_cat('tenure', {'0-2yr','5-10yr','15-20yr','20-30yr','30+yr'})
show_cat('deed_signals')
show_cat('v2_signals')

# Final top-line number
if training and holdout:
    tr_base = sum(r['base_rate'] for r in training) / len(training)
    ho_base = holdout[0]['base_rate']
    print(f"Base rates: training avg = {tr_base*100:.2f}%  holdout = {ho_base*100:.2f}%")
