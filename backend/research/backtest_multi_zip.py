"""
Multi-ZIP backtest — replicate the 98004 calibration across all six Eastside ZIPs.

For each ZIP:
  - Load parcel set (residential, $500k+)
  - Stream deed chain from EXTR_RPSale
  - At each cutoff (2016-2019 train, 2021 holdout): reconstruct features, compute lifts
  - Compute top-N precision using training-period lifts as scoring weights

Output: per-ZIP calibration + cross-ZIP stability table.
"""
import csv, json, re, os, time
from datetime import datetime, timedelta
from collections import defaultdict

SALES_CSV = '/home/claude/kc-data/EXTR_RPSale.csv'
OUT_PATH = '/home/claude/sellersignal_v2/out/backtest-multi-zip.json'

# 98004 already has an owner DB, others have just the parcel dict from ArcGIS pull
ZIP_PARCEL_FILES = {
    '98004': '/home/claude/kc-data/bellevue-98004-owners.json',
    '98039': '/home/claude/kc-data/eastside-98039-parcels.json',
    '98040': '/home/claude/kc-data/eastside-98040-parcels.json',
    '98033': '/home/claude/kc-data/eastside-98033-parcels.json',
    '98006': '/home/claude/kc-data/eastside-98006-parcels.json',
    '98005': '/home/claude/kc-data/eastside-98005-parcels.json',
}

CUTOFFS = [
    ('2016-01-01', 'training'),
    ('2017-01-01', 'training'),
    ('2018-01-01', 'training'),
    ('2019-01-01', 'training'),
    ('2021-01-01', 'holdout'),
]
FORWARD_DAYS = 730


def classify_owner(name):
    if not name or len(name) < 3: return 'unknown'
    n = name.upper()
    if re.search(r'\bCITY OF\b|\bCOUNTY OF\b|\bSTATE OF\b|\bSCHOOL\b|\bCHURCH\b|\bHOA\b|\bHOMEOWNERS\b', n): return 'gov'
    if re.search(r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR', n): return 'estate'
    if re.search(r'\bTRUST\b|\bTTEES?\b|\bTTEE\b', n): return 'trust'
    if re.search(r'\bLLC\b|\bCORP\b|\bINC\b|\bLP\b|\bPARTNERSHIP\b|\bHOLDINGS\b|\bPROPERTIES\b|\bINVESTMENTS\b|\bVENTURES\b', n): return 'llc'
    return 'individual'


# ── Load all parcel sets and value lookups ────────────────────────────
print(f"[{datetime.now():%H:%M:%S}] Loading parcel sets...")
all_pins = set()
zip_of_pin = {}
value_of_pin = {}

for z, path in ZIP_PARCEL_FILES.items():
    data = json.load(open(path))
    for pin, rec in data.items():
        all_pins.add(pin)
        zip_of_pin[pin] = z
        value_of_pin[pin] = rec.get('value', 0) or 0
    print(f"  {z}: {sum(1 for p in zip_of_pin if zip_of_pin[p]==z):,} parcels")
print(f"  total: {len(all_pins):,} parcels across six Eastside ZIPs")


# ── Stream deed chain once for all parcels ────────────────────────────
print(f"\n[{datetime.now():%H:%M:%S}] Streaming EXTR_RPSale...")
t1 = time.time()
sales_by_pin = defaultdict(list)
with open(SALES_CSV, encoding='latin-1') as f:
    rdr = csv.DictReader(f)
    for row in rdr:
        pin = f"{row['Major'].strip().zfill(6)}{row['Minor'].strip().zfill(4)}"
        if pin not in all_pins: continue
        try: dt = datetime.strptime(row['DocumentDate'].strip(), '%m/%d/%Y')
        except ValueError: continue
        try: price = int(row['SalePrice'])
        except (ValueError, TypeError): price = 0
        sales_by_pin[pin].append({
            'date': dt,
            'buyer': (row.get('BuyerName') or '').strip(),
            'seller': (row.get('SellerName') or '').strip(),
            'price': price,
            'instrument': (row.get('SaleInstrument') or '').strip(),
            'reason': (row.get('SaleReason') or '').strip(),
        })
for p in sales_by_pin: sales_by_pin[p].sort(key=lambda s: s['date'])
print(f"  {sum(1 for p in all_pins if sales_by_pin.get(p)):,} / {len(all_pins):,} parcels have deed history  ({time.time()-t1:.0f}s)")


# ── Feature reconstruction ────────────────────────────────────────────
def build_features_for_zip(zip_target, T_0):
    forward_end = T_0 + timedelta(days=FORWARD_DAYS)
    feats = {}
    for pin in all_pins:
        if zip_of_pin.get(pin) != zip_target: continue
        chain = sales_by_pin.get(pin, [])
        pre = [s for s in chain if s['date'] <= T_0]
        post = [s for s in chain if T_0 < s['date'] <= forward_end and s['price'] >= 100_000]

        if not pre:
            owner_type = 'unknown'; tenure_yrs = None
        else:
            owner_type = classify_owner(pre[-1]['buyer'])
            tenure_yrs = (T_0 - pre[-1]['date']).days / 365.25
        if owner_type == 'gov': continue

        five_yr = T_0 - timedelta(days=365*5)
        sig_indiv_to_llc = sig_indiv_to_trust = False
        if len(pre) >= 2 and pre[-1]['date'] >= five_yr:
            t_last = classify_owner(pre[-1]['buyer'])
            t_prev = classify_owner(pre[-2]['buyer'])
            if t_prev == 'individual' and t_last == 'llc': sig_indiv_to_llc = True
            elif t_prev == 'individual' and t_last == 'trust': sig_indiv_to_trust = True

        sig_trust_aging = (owner_type == 'trust' and tenure_yrs is not None and tenure_yrs >= 10)
        sig_silent_transition = (owner_type == 'individual' and tenure_yrs is not None and tenure_yrs >= 20)

        feats[pin] = {
            'owner_type': owner_type,
            'tenure_yrs': tenure_yrs,
            'sig_indiv_to_llc': sig_indiv_to_llc,
            'sig_indiv_to_trust': sig_indiv_to_trust,
            'sig_trust_aging': sig_trust_aging,
            'sig_silent_transition': sig_silent_transition,
            'sold': len(post) > 0,
            'value': value_of_pin.get(pin, 0),
        }
    return feats


def seg(feats, pred, min_n=15):
    s = [f for f in feats.values() if pred(f)]
    if len(s) < min_n: return None
    sold = sum(1 for f in s if f['sold'])
    rate = sold / len(s)
    return {'n': len(s), 'sold': sold, 'rate': rate}


def score(f, weights):
    """Simple multiplicative score using training-period lifts."""
    s = weights['owner_type'].get(f['owner_type'], 1.0)
    if f['sig_indiv_to_llc']:     s *= weights['sig_indiv_to_llc']
    if f['sig_indiv_to_trust']:   s *= weights['sig_indiv_to_trust']
    if f['sig_trust_aging']:      s *= weights['sig_trust_aging']
    return s


# ── Run per ZIP ───────────────────────────────────────────────────────
print(f"\n[{datetime.now():%H:%M:%S}] Per-ZIP backtest...")
per_zip = {}

for z in ZIP_PARCEL_FILES.keys():
    t_zip = time.time()
    print(f"\n══ {z} ══")
    per_cutoff = {}
    for cutoff_str, fold in CUTOFFS:
        T_0 = datetime.strptime(cutoff_str, '%Y-%m-%d')
        feats = build_features_for_zip(z, T_0)
        if not feats:
            continue
        n = len(feats)
        n_sold = sum(1 for f in feats.values() if f['sold'])
        base = n_sold / n if n else 0

        lifts = {}
        # Owner type
        for t in ['individual','trust','llc','estate']:
            r = seg(feats, lambda f, tt=t: f['owner_type']==tt)
            if r: lifts[f'owner_{t}'] = {**r, 'lift': r['rate']/base if base else 0}
        # Deed signals
        for sig in ['sig_indiv_to_llc','sig_indiv_to_trust','sig_trust_aging','sig_silent_transition']:
            r = seg(feats, lambda f, ss=sig: f[ss])
            if r: lifts[sig] = {**r, 'lift': r['rate']/base if base else 0}

        per_cutoff[cutoff_str] = {
            'fold': fold, 'n': n, 'sold': n_sold,
            'base_rate': base, 'lifts': lifts,
        }

    # Compute training-period average weights for this ZIP
    tr_runs = [c for c in per_cutoff.values() if c['fold'] == 'training']
    def avg(key):
        vals = [c['lifts'].get(key, {}).get('lift') for c in tr_runs]
        vals = [v for v in vals if v is not None]
        return sum(vals)/len(vals) if vals else 1.0

    weights = {
        'owner_type': {
            'individual': avg('owner_individual'),
            'trust':      avg('owner_trust'),
            'llc':        avg('owner_llc'),
            'estate':     avg('owner_estate'),
            'unknown':    1.0,
        },
        'sig_indiv_to_llc':    avg('sig_indiv_to_llc'),
        'sig_indiv_to_trust':  avg('sig_indiv_to_trust'),
        'sig_trust_aging':     avg('sig_trust_aging'),
    }

    # Top-N precision at 2021 holdout using those weights
    T_0 = datetime(2021,1,1)
    feats_holdout = build_features_for_zip(z, T_0)
    scored = [(pin, score(f, weights), f['sold']) for pin, f in feats_holdout.items()]
    scored.sort(key=lambda x: -x[1])
    n = len(scored)
    n_sold = sum(1 for _,_,s in scored if s)
    base = n_sold / n if n else 0

    topN = {}
    for nk in [10, 25, 50, 100]:
        if n < nk: continue
        top = scored[:nk]
        sold = sum(1 for _,_,s in top if s)
        prec = sold / nk
        topN[nk] = {'precision': prec, 'lift': prec/base if base else 0, 'sold': sold}

    per_zip[z] = {
        'per_cutoff': per_cutoff,
        'weights_learned': weights,
        'holdout_topN': topN,
        'holdout_n': n,
        'holdout_sold': n_sold,
        'holdout_base_rate': base,
    }

    # Brief console
    tr_avg_base = sum(c['base_rate'] for c in tr_runs) / len(tr_runs) if tr_runs else 0
    ho_base = per_cutoff.get('2021-01-01', {}).get('base_rate', 0)
    llc_tr = avg('owner_llc'); llc_ho = per_cutoff.get('2021-01-01', {}).get('lifts', {}).get('owner_llc', {}).get('lift', 0)
    print(f"  training base rate: {tr_avg_base*100:.2f}% · holdout base: {ho_base*100:.2f}%")
    print(f"  LLC owner lift: train={llc_tr:.2f}x · holdout={llc_ho:.2f}x")
    print(f"  indiv→LLC 5yr lift: train={avg('sig_indiv_to_llc'):.2f}x")
    if 25 in topN:
        t25 = topN[25]
        print(f"  2021 holdout TOP 25: {t25['precision']*100:.1f}% precision ({t25['lift']:.2f}x base)")
    print(f"  ({time.time()-t_zip:.1f}s)")


# ── Save ──────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, 'w') as f:
    json.dump({
        'zips': list(ZIP_PARCEL_FILES.keys()),
        'cutoffs': CUTOFFS,
        'forward_days': FORWARD_DAYS,
        'per_zip': per_zip,
        'generated_at': datetime.now().isoformat(),
    }, f, indent=2, default=str)

# ── Cross-ZIP summary ─────────────────────────────────────────────────
print(f"\n{'═'*70}")
print(f"CROSS-ZIP STABILITY SUMMARY — 2021 HOLDOUT (predicting 2023 sales)")
print(f"{'═'*70}")
print(f"\n{'ZIP':<7} {'n':>6} {'base':>7} {'LLC lift':>10} {'i→LLC':>8} {'Top25 prec':>11} {'Top25 lift':>11} {'Top50 prec':>11}")
for z in ZIP_PARCEL_FILES.keys():
    d = per_zip.get(z, {})
    ho = d.get('per_cutoff', {}).get('2021-01-01', {})
    if not ho: print(f"  {z}: no holdout data"); continue
    base = ho['base_rate']
    llc = ho['lifts'].get('owner_llc', {}).get('lift', 0)
    illc = ho['lifts'].get('sig_indiv_to_llc', {}).get('lift', 0)
    t25 = d['holdout_topN'].get(25, {})
    t50 = d['holdout_topN'].get(50, {})
    print(f"{z:<7} {ho['n']:>6,} {base*100:>6.2f}% {llc:>9.2f}x {illc:>7.2f}x "
          f"{t25.get('precision',0)*100:>10.1f}% {t25.get('lift',0):>10.2f}x "
          f"{t50.get('precision',0)*100:>10.1f}%")

print(f"\n✓ {OUT_PATH}")
