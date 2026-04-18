"""
Dossier compiler — assembles all available context per banded lead,
ready to feed to the synthesis layer (Claude API in prod, inline here).

Output per lead (JSON):
  {
    'pin': ..., 'address': ..., 'value': ...,
    'signal': { family, sub, inevitability, timeline, band },
    'owner': { name, tokens, type: individual|trust|llc, ... },
    'grantor': { name, ... } | None,  # for trust_aging
    'tenure': { years, purchase_date, purchase_price },
    'deed_chain': [ { date, seller, buyer, price, reason }, ... ],
    'mailing': { street, city, differs_from_property: bool },
    'obit_match': { name, date, age, context, confidence } | None,
    'convergent_families': [...],
    'neighborhood': { zip, street_peer_count, avg_value, turnover_rate },
  }

The dossier is what the synthesis layer reasons over. The richer the dossier,
the better the synthesized output.
"""
import json, os, re
from datetime import datetime
from collections import defaultdict

TODAY = datetime(2026, 4, 18)


def load_banded_inventory():
    return json.load(open('/home/claude/sellersignal_v2/out/banded-inventory.json'))


def load_deed_chains_for_pins(pins):
    """Load deed chains for the target pins. Tries 98004 cache first."""
    chains = {}
    # 98004 cache
    path = '/home/claude/kc-data/bellevue-98004-deed-chain.json'
    if os.path.exists(path):
        data = json.load(open(path))
        for pin in pins:
            if pin in data:
                chains[pin] = data[pin]
    # For Eastside ZIPs that aren't cached, need to extract from EXTR_RPSale.
    # For dossier prototype, operate only on what's cached for now.
    return chains


def load_mailing_for_pins(pins):
    out = {}
    path = '/home/claude/kc-data/bellevue-98004-mailing.json'
    if os.path.exists(path):
        data = json.load(open(path))
        for pin in pins:
            if pin in data:
                out[pin] = data[pin]
    return out


def classify_owner_type(name):
    if not name: return 'unknown'
    up = name.upper()
    if any(tag in up for tag in ['TRUST', 'TRS', 'TRUSTEE']): return 'trust'
    if any(tag in up for tag in ['LLC', 'INC', 'CORP', 'LP', 'LTD', 'PS']): return 'entity'
    return 'individual'


def compile_neighborhood_peers(target_lead, all_leads, radius_street_match=True):
    """
    How many other leads sit on the same street?
    Indicates cohort pressure / clustering signal.
    """
    if not target_lead.get('address'): return {}
    addr = target_lead['address']
    # Extract street name (skip house number)
    parts = addr.split()
    if len(parts) < 2: return {}
    street = ' '.join(parts[1:])  # e.g., "HUNTS POINT RD"

    peers = []
    for L in all_leads:
        if L['pin'] == target_lead['pin']: continue
        if L['zip'] != target_lead['zip']: continue
        other = L.get('address') or ''
        if street in other:
            peers.append(L)
    if not peers: return {}
    vals = [p.get('value', 0) for p in peers if p.get('value')]
    return {
        'street': street,
        'peer_count': len(peers),
        'peer_avg_value': sum(vals) / max(len(vals), 1) if vals else None,
        'peer_band1_count': sum(1 for p in peers if p.get('band') == 1),
        'peer_band2_count': sum(1 for p in peers if p.get('band') == 2),
    }


def compile_dossier(lead, deed_chain, mailing, all_leads):
    """Assemble a single lead into a full dossier dict."""
    pin = lead['pin']

    chain = deed_chain.get(pin, [])

    # Parse current owner + type
    owner_name = lead.get('owner') or ''
    owner_type = classify_owner_type(owner_name)

    # Grantor (if trust)
    grantor = lead.get('grantor') or None

    # Tenure details — from most recent non-zero-price sale (skipping quit claims)
    tenure_info = None
    if chain:
        for d in reversed(chain):
            if d.get('price', 0) > 100_000:  # real sale, not a $1 quit claim
                dt = datetime.strptime(d['date'], '%Y-%m-%d')
                tenure_info = {
                    'years': round((TODAY - dt).days / 365.25, 1),
                    'purchase_date': d['date'],
                    'purchase_price': d['price'],
                    'buyer': d.get('buyer'),
                }
                break

    # Mailing
    mail = mailing.get(pin, {})
    prop_addr = (lead.get('address') or '').upper()
    mail_street = (mail.get('mail_street') or '').upper()
    differs = mail_street and mail_street not in prop_addr and prop_addr not in mail_street

    dossier = {
        'pin': pin,
        'address': lead.get('address'),
        'city': lead.get('city') or '',
        'zip': lead.get('zip'),
        'value': lead.get('value'),
        'signal': {
            'family': lead.get('signal_family'),
            'sub': lead.get('sub_signal'),
            'inevitability': lead.get('inevitability'),
            'timeline_months': lead.get('timeline_months'),
            'band': lead.get('band'),
            'band_label': lead.get('band_label'),
            'rank_score': lead.get('rank_score'),
        },
        'owner': {
            'name': owner_name,
            'type': owner_type,
        },
        'grantor': {'name': grantor} if grantor else None,
        'tenure': tenure_info,
        'deed_chain_summary': [
            {'date': d['date'], 'seller': d['seller'], 'buyer': d['buyer'], 'price': d.get('price')}
            for d in chain[-5:]  # last 5 events max
        ],
        'mailing': {
            'street': mail.get('mail_street'),
            'city': mail.get('mail_city'),
            'differs_from_property': bool(differs),
            'out_of_state': mail.get('mail_city') and 'WA' not in (mail.get('mail_city') or '').upper(),
        },
        'obit_match': lead.get('obit_match'),
        'convergent_families': lead.get('convergent_families', []),
        'neighborhood': compile_neighborhood_peers(lead, all_leads),
        'estimated_age': lead.get('est_age'),
        'rationality': {
            'score': lead.get('rationality_score'),
            'flags': lead.get('rationality_flags', []),
            'recommendation': lead.get('rationality_recommendation'),
        } if lead.get('rationality_score') is not None else None,
    }
    return dossier


def run():
    inv = load_banded_inventory()
    leads = inv['leads']
    print(f"Loaded {len(leads)} banded leads")

    # Pick cohort: Band 1 + top 10 Band 2 by rank_score
    band1 = [L for L in leads if L.get('band') == 1]
    band2_top = sorted([L for L in leads if L.get('band') == 2],
                       key=lambda x: -x.get('rank_score', 0))[:10]
    cohort = band1 + band2_top
    print(f"Synthesis cohort: Band 1 ({len(band1)}) + top 10 Band 2 = {len(cohort)}")

    pins = [L['pin'] for L in cohort]
    deed_chain = load_deed_chains_for_pins(pins)
    mailing = load_mailing_for_pins(pins)

    dossiers = []
    for L in cohort:
        d = compile_dossier(L, deed_chain, mailing, leads)
        dossiers.append(d)

    out_path = '/home/claude/sellersignal_v2/out/synthesis-cohort-dossiers.json'
    with open(out_path, 'w') as f:
        json.dump(dossiers, f, indent=2, default=str)
    print(f"Saved {len(dossiers)} dossiers to {out_path}")

    # Quick preview of dossier quality
    print("\n═══ Dossier preview: top Band 1 lead ═══")
    if band1:
        top_b1 = max(band1, key=lambda x: x.get('rank_score', 0))
        d = compile_dossier(top_b1, deed_chain, mailing, leads)
        print(json.dumps(d, indent=2, default=str)[:2500])

    return dossiers


if __name__ == "__main__":
    run()
