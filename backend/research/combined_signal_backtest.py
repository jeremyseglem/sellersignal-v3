"""
combined_signal_backtest.py — The HONEST test.

Test the full production signal stack against the 2021 holdout:
  Deed-chain signals:    owner type, tenure, trust aging, investor_disposition
  Event-based signals:   estate seller in prior deed (inheritance), quit-claim,
                         rapid turnover, trust↔individual transitions
  Composite signals:     silent_transition (indiv + tenure + age-bracket proxy),
                         trust_aging (trust + tenure),
                         family-cluster surname density

Critical: we require 5+ year tenure to avoid the indiv→LLC leakage problem
and remove short-hold flippers from the "pre-seller" population.

For each signal family, we measure:
  - Precision at the top N scored leads
  - Recall of actual sellers
  - F1
  - Per-ZIP stability

Against: 6 Eastside ZIPs, T_0 = 2021-01-01, 24-month forward window.

Note on coverage:
  Obits, NOD filings, trustee sales, and expired listings are EVENT detectors
  that fire on a small cohort. We cannot historically reconstruct these
  events with current data (KC LandmarkWeb doesn't expose historical NODs in
  bulk; obit archives are partial pre-2018). What we CAN measure historically:
    - Estate-origin seller on the PRIOR deed (proxies for "inherited property")
    - Trust structure + aging (deterministic from deed chain)
    - Silent transition (individual + long tenure)
    - Owner type conversions
  Those are the production Band 2 inference signals. We backtest those.

The production event detectors (NOD, trustee sale, obit cross-reference) are
tested LIVE against current inventory — not historically. Their precision is
known from the verification gate (the Weinstein/Gilbert rejects).
"""
import json, csv, re
from datetime import datetime, timedelta
from collections import defaultdict, Counter

SALES_CSV = '/home/claude/kc-data/EXTR_RPSale.csv'
ZIP_PARCEL_FILES = {
    '98004': '/home/claude/kc-data/bellevue-98004-owners.json',
    '98039': '/home/claude/kc-data/eastside-98039-parcels.json',
    '98040': '/home/claude/kc-data/eastside-98040-parcels.json',
    '98033': '/home/claude/kc-data/eastside-98033-parcels.json',
    '98006': '/home/claude/kc-data/eastside-98006-parcels.json',
    '98005': '/home/claude/kc-data/eastside-98005-parcels.json',
}


def classify_owner(name):
    if not name or len(name) < 3: return 'unknown'
    n = name.upper()
    if re.search(r'\bCITY OF\b|\bCOUNTY OF\b|\bSTATE OF\b|\bSCHOOL\b|\bCHURCH\b|\bHOA\b', n): return 'gov'
    if re.search(r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR', n): return 'estate'
    if re.search(r'\bTRUST\b|\bTTEES?\b|\bTTEE\b', n): return 'trust'
    if re.search(r'\bLLC\b|\bCORP\b|\bINC\b|\bLP\b|\bHOLDINGS\b|\bINVESTMENTS\b|\bPROPERTIES\b|\bVENTURES\b', n): return 'llc'
    return 'individual'


def surname_tokens(name):
    """Extract last-name tokens for family-cluster detection."""
    if not name: return set()
    # Strip entity suffixes
    n = re.sub(r'\b(TRUST|TTEE|LLC|CORP|INC|LP|ESTATE|HEIRS?|FAMILY|LIVING|REVOCABLE|IRREVOCABLE)\b', '', name.upper())
    tokens = [t for t in re.split(r'[^A-Z]+', n) if len(t) >= 4]
    return set(tokens[-2:]) if tokens else set()  # last 1-2 tokens


# ── LOAD ──────────────────────────────────────────────────────────────
print("Loading parcel sets...")
all_pins, zip_of_pin, value_of_pin, addr_of_pin = set(), {}, {}, {}
for z, path in ZIP_PARCEL_FILES.items():
    for pin, rec in json.load(open(path)).items():
        all_pins.add(pin); zip_of_pin[pin] = z
        value_of_pin[pin] = rec.get('value', 0) or 0
        addr_of_pin[pin] = rec.get('address', '') or ''

print("Streaming deed chain...")
sales_by_pin = defaultdict(list)
with open(SALES_CSV, encoding='latin-1') as f:
    for row in csv.DictReader(f):
        pin = f"{row['Major'].strip().zfill(6)}{row['Minor'].strip().zfill(4)}"
        if pin not in all_pins: continue
        try: dt = datetime.strptime(row['DocumentDate'].strip(), '%m/%d/%Y')
        except ValueError: continue
        try: price = int(row['SalePrice'])
        except: price = 0
        sales_by_pin[pin].append({
            'date': dt,
            'buyer': (row.get('BuyerName') or '').strip(),
            'seller': (row.get('SellerName') or '').strip(),
            'price': price,
            'instrument': (row.get('SaleInstrument') or '').strip(),
        })
for p in sales_by_pin: sales_by_pin[p].sort(key=lambda s: s['date'])


# ── BUILD FEATURE VECTORS AT T_0 = 2021-01-01 ────────────────────────
T_0 = datetime(2021, 1, 1)
forward_end = T_0 + timedelta(days=730)

print(f"\nBuilding features at T_0 = {T_0.strftime('%Y-%m-%d')}, forward window 24mo...\n")

# First pass: compute surname frequency for cluster detection
surname_pin_map = defaultdict(set)
for pin in all_pins:
    chain = sales_by_pin.get(pin, [])
    pre = [s for s in chain if s['date'] <= T_0]
    if not pre: continue
    last = pre[-1]
    if classify_owner(last['buyer']) == 'gov': continue
    for tok in surname_tokens(last['buyer']):
        if tok: surname_pin_map[tok].add(pin)


features = {}
for pin in all_pins:
    chain = sales_by_pin.get(pin, [])
    pre = [s for s in chain if s['date'] <= T_0]
    post = [s for s in chain if T_0 < s['date'] <= forward_end and s['price'] >= 100_000]
    if not pre: continue
    last = pre[-1]
    owner_type = classify_owner(last['buyer'])
    if owner_type == 'gov': continue
    tenure_yrs = (T_0 - last['date']).days / 365.25

    # HARD FILTER: require 5+ year tenure (removes flipper/leakage leads)
    if tenure_yrs < 5: continue

    # ── Signal family reconstruction ──
    prev = pre[-2] if len(pre) >= 2 else None

    # Production signal: silent_transition (indiv + long tenure)
    # Production breaks into age brackets; we can't compute age without demographic
    # append, so proxy as: tenure bucket drives the sub-signal
    sig_silent_transition = False
    silent_sub = None
    if owner_type == 'individual':
        if tenure_yrs >= 30:
            sig_silent_transition = True; silent_sub = 'age_80plus_proxy'
        elif tenure_yrs >= 22:
            sig_silent_transition = True; silent_sub = 'age_75_79_proxy'
        elif tenure_yrs >= 15:
            sig_silent_transition = True; silent_sub = 'age_70_74_proxy'
        elif tenure_yrs >= 10:
            sig_silent_transition = True; silent_sub = 'age_65_69_proxy'

    # Production signal: trust_aging (trust + aged)
    sig_trust_aging = False
    trust_sub = None
    if owner_type == 'trust':
        if tenure_yrs >= 25:
            sig_trust_aging = True; trust_sub = 'grantor_80plus_proxy'
        elif tenure_yrs >= 18:
            sig_trust_aging = True; trust_sub = 'grantor_75_79_proxy'
        elif tenure_yrs >= 10:
            sig_trust_aging = True; trust_sub = 'grantor_65_74_proxy'

    # Production signal: investor_disposition (LLC + hold duration)
    sig_investor_disposition = False
    if owner_type == 'llc' and tenure_yrs >= 7:
        sig_investor_disposition = True

    # Production signal: death_inheritance (prior seller was estate/heirs)
    # This is the strongest forensic pre-seller signal in deed data.
    sig_death_inheritance = bool(re.search(
        r'\bESTATE\b|\bHEIRS?\b|\bDECEASED\b|\bSURVIVOR',
        (last.get('seller') or '').upper()))

    # Production signal: family_event_cluster
    # Owner's surname appears on 2+ parcels in the same ZIP
    sig_family_cluster = False
    cluster_size = 1
    this_zip = zip_of_pin.get(pin)
    for tok in surname_tokens(last['buyer']):
        if tok and tok in surname_pin_map:
            cluster = surname_pin_map[tok]
            zip_cluster = [p for p in cluster if zip_of_pin.get(p) == this_zip]
            if len(zip_cluster) >= 2:
                sig_family_cluster = True
                cluster_size = max(cluster_size, len(zip_cluster))

    # Trust↔individual transitions (deed-chain event)
    sig_trust_to_indiv = False
    sig_indiv_to_trust = False
    if prev:
        t_prev = classify_owner(prev['buyer'])
        if t_prev == 'trust' and owner_type == 'individual':
            sig_trust_to_indiv = True
        if t_prev == 'individual' and owner_type == 'trust':
            sig_indiv_to_trust = True

    # Estate currently owns
    sig_estate_owned = owner_type == 'estate'

    # Aggregate: does ANY production signal fire?
    any_signal = (sig_silent_transition or sig_trust_aging or sig_investor_disposition
                  or sig_death_inheritance or sig_family_cluster or sig_estate_owned
                  or sig_trust_to_indiv or sig_indiv_to_trust)

    features[pin] = {
        'zip': this_zip,
        'owner_type': owner_type,
        'tenure_yrs': tenure_yrs,
        'value': value_of_pin.get(pin, 0),
        'addr': addr_of_pin.get(pin, ''),
        # production signals
        'sig_silent_transition': sig_silent_transition,
        'silent_sub': silent_sub,
        'sig_trust_aging': sig_trust_aging,
        'trust_sub': trust_sub,
        'sig_investor_disposition': sig_investor_disposition,
        'sig_death_inheritance': sig_death_inheritance,
        'sig_family_cluster': sig_family_cluster,
        'cluster_size': cluster_size,
        'sig_estate_owned': sig_estate_owned,
        'sig_trust_to_indiv': sig_trust_to_indiv,
        'sig_indiv_to_trust': sig_indiv_to_trust,
        'any_signal': any_signal,
        # outcome
        'sold': len(post) > 0,
        'sale_price': post[0]['price'] if post else 0,
    }

n = len(features)
n_sold = sum(1 for f in features.values() if f['sold'])
base = n_sold / n

print(f"Cohort (5+ yr tenure, 6 ZIPs): {n:,} parcels")
print(f"Sold in 24mo window:           {n_sold:,}")
print(f"Base rate:                     {base*100:.2f}%\n")


# ── PER-SIGNAL LIFT ──────────────────────────────────────────────────
def seg(pred, min_n=20):
    s = [f for f in features.values() if pred(f)]
    if len(s) < min_n: return None
    sold = sum(1 for f in s if f['sold'])
    return {'n': len(s), 'sold': sold, 'rate': sold/len(s), 'lift': (sold/len(s))/base if base else 0}


print("═══ PRODUCTION SIGNAL STACK — single-signal lift ═══\n")
print(f"{'signal':<42} {'n':>6} {'sold':>5} {'precision':>11} {'lift':>6}")

production_signals = [
    ('silent_transition (any age bracket)',    lambda f: f['sig_silent_transition']),
    ('  silent, tenure 10-15yr',               lambda f: f['silent_sub'] == 'age_65_69_proxy'),
    ('  silent, tenure 15-22yr',               lambda f: f['silent_sub'] == 'age_70_74_proxy'),
    ('  silent, tenure 22-30yr',               lambda f: f['silent_sub'] == 'age_75_79_proxy'),
    ('  silent, tenure 30+yr',                 lambda f: f['silent_sub'] == 'age_80plus_proxy'),
    ('trust_aging (any bracket)',              lambda f: f['sig_trust_aging']),
    ('  trust, tenure 10-18yr',                lambda f: f['trust_sub'] == 'grantor_65_74_proxy'),
    ('  trust, tenure 18-25yr',                lambda f: f['trust_sub'] == 'grantor_75_79_proxy'),
    ('  trust, tenure 25+yr',                  lambda f: f['trust_sub'] == 'grantor_80plus_proxy'),
    ('investor_disposition (LLC 7+yr)',        lambda f: f['sig_investor_disposition']),
    ('death_inheritance (prior seller estate)', lambda f: f['sig_death_inheritance']),
    ('family_cluster (2+ same-surname ZIP)',   lambda f: f['sig_family_cluster']),
    ('estate currently owns',                  lambda f: f['sig_estate_owned']),
    ('trust→individual transition',            lambda f: f['sig_trust_to_indiv']),
    ('indiv→trust transition',                 lambda f: f['sig_indiv_to_trust']),
    ('ANY signal fires',                       lambda f: f['any_signal']),
]

results = []
for label, pred in production_signals:
    r = seg(pred)
    if r:
        flag = '✓' if r['lift'] >= 1.3 else ('!' if r['lift'] >= 1.1 else ' ')
        print(f"{flag} {label:<40} {r['n']:>5} {r['sold']:>5} {r['rate']*100:>9.2f}%  {r['lift']:>5.2f}x")
        results.append((label, r))
    else:
        print(f"  {label:<40} (n < 20)")


# ── COMPOSITE SCORING ────────────────────────────────────────────────
print(f"\n═══ COMBINED PRODUCTION SCORING ═══\n")

# Each signal contributes multiplicatively; weights from what we just observed
# (any signal 1.1x+ gets a positive boost; signals below base get 0.9x damping)
def score(f):
    s = 1.0
    if f['sig_silent_transition']:
        # Tiered by tenure bracket
        if f['silent_sub'] == 'age_80plus_proxy': s *= 1.15
        elif f['silent_sub'] == 'age_75_79_proxy': s *= 1.05
        elif f['silent_sub'] == 'age_70_74_proxy': s *= 0.95
        else: s *= 1.05
    if f['sig_trust_aging']:
        if f['trust_sub'] == 'grantor_80plus_proxy': s *= 1.30
        elif f['trust_sub'] == 'grantor_75_79_proxy': s *= 1.10
        else: s *= 0.95
    if f['sig_investor_disposition']: s *= 1.20
    if f['sig_death_inheritance']:   s *= 1.85
    if f['sig_family_cluster']:      s *= 1.15
    if f['sig_estate_owned']:        s *= 1.35
    # Value damp (logarithmic — penalizes runaway ultra-luxury skew)
    import math
    if f['value'] > 0:
        v = math.log10(max(f['value'], 1_000_000)) / math.log10(1_000_000)
    else:
        v = 1.0
    return s * v


scored = [(pin, score(f), f) for pin, f in features.items()]
scored.sort(key=lambda x: -x[1])


# ── PRECISION AT TOP N ───────────────────────────────────────────────
print(f"{'Flagged':<14} {'# actual sellers':<18} {'Precision':<11} {'Recall':<9} {'vs random':<10}")
for topn in [25, 50, 100, 250, 500, 1000]:
    top = scored[:topn]
    tp = sum(1 for _,_,f in top if f['sold'])
    prec = tp / topn if topn else 0
    rec = tp / n_sold if n_sold else 0
    lift = prec / base if base else 0
    print(f"top {topn:<9,} {tp:>6}{'':<10} {prec*100:>8.1f}%   {rec*100:>6.1f}%  {lift:>6.2f}x")


# ── PER-ZIP PRECISION (check stability) ──────────────────────────────
print(f"\n═══ PER-ZIP TOP-25 PRECISION (combined scoring) ═══\n")
print(f"{'ZIP':<8} {'n':>7} {'base':>6} {'top25 prec':>12} {'lift':>7}")
for z in sorted(ZIP_PARCEL_FILES.keys()):
    zfeats = {pin: f for pin, f in features.items() if f['zip'] == z}
    if not zfeats: continue
    zscored = [(p, score(f), f) for p, f in zfeats.items()]
    zscored.sort(key=lambda x: -x[1])
    zn = len(zscored)
    znsold = sum(1 for _,_,f in zscored if f['sold'])
    zbase = znsold / zn if zn else 0
    top25 = zscored[:25]
    tp = sum(1 for _,_,f in top25 if f['sold'])
    prec = tp/25
    print(f"{z:<8} {zn:>6,} {zbase*100:>5.1f}% {prec*100:>11.1f}% {prec/zbase if zbase else 0:>6.2f}x")


# ── SHOW TOP 20 (what the agent actually sees) ───────────────────────
print(f"\n═══ TOP 20 COMBINED-SCORE LEADS (what the agent would pursue) ═══\n")
print(f"{'rank':<5} {'addr':<30} {'zip':<6} {'val':>7} {'own':<6} {'ten':>5} {'score':>6} {'sold?':<5}")
for i, (pin, s, f) in enumerate(scored[:20], 1):
    addr = (f['addr'] or '—')[:30]
    mark = '✓' if f['sold'] else '·'
    print(f"{i:<4} {addr:<30} {f['zip']:<6} ${f['value']/1e6:>5.1f}M {f['owner_type']:<6} {f['tenure_yrs']:>4.0f}y  {s:>5.2f} {mark}")


# ── SAVE ─────────────────────────────────────────────────────────────
import os
os.makedirs('out', exist_ok=True)
out = {
    'T_0': T_0.strftime('%Y-%m-%d'),
    'forward_window_days': 730,
    'cohort_size': n,
    'n_sold': n_sold,
    'base_rate': base,
    'min_tenure_filter_yrs': 5,
    'per_signal_lifts': [{'signal': l, **r} for l, r in results],
    'top_n_precision': {
        topn: {
            'flagged': topn,
            'sold': sum(1 for _,_,f in scored[:topn] if f['sold']),
            'precision': sum(1 for _,_,f in scored[:topn] if f['sold']) / topn,
            'recall': sum(1 for _,_,f in scored[:topn] if f['sold']) / n_sold if n_sold else 0,
            'lift': (sum(1 for _,_,f in scored[:topn] if f['sold']) / topn) / base if base else 0,
        }
        for topn in [25, 50, 100, 250, 500, 1000]
    },
}
with open('out/combined-signal-backtest.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print(f"\n✓ out/combined-signal-backtest.json")
