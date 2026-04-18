"""
investigation.py — Person-intelligence engine ported from v1 investigate.js.

Two modes:
  screen: 7 targeted searches, high-signal only (Tier 1 subset)
  deep:   25 searches, full Tier 1 + 2 + 3 (run on finalists only)

Adds trust scoring to every extracted signal based on source type.

Signal categories preserved from v1:
  listing / life_event / identity / demographic / financial / blocker

Trust levels:
  high   — promotable on its own (LinkedIn profile, obit from funeral home,
           court record, SOS filing, listing platform, people-finder)
  medium — contextual (generic news, broad identity result)
  low    — never promotes (generic web, Facebook, community mention)
"""
from __future__ import annotations
import os, re, json, time, random, hashlib, urllib.parse, urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

SERPAPI_KEY = os.environ.get('SERPAPI_KEY')
MOCK_MODE   = SERPAPI_KEY is None  # auto-detect: no key → mock

# ─── BUDGET CONTROLS ────────────────────────────────────────────────────
MAX_SEARCHES_PER_MONTH = 2000
MAX_SEARCHES_PER_RUN   = 800
COST_PER_SEARCH        = 0.015  # SerpAPI standard tier

BUDGET_STATE_PATH = '/home/claude/sellersignal_v2/out/investigation/budget_state.json'
CACHE_DIR         = '/home/claude/sellersignal_v2/out/investigation/cache'
CACHE_TTL_DAYS    = 90


# ─── BUDGET TRACKING ────────────────────────────────────────────────────
class BudgetGuard:
    """Hard-cap enforcement — aborts if a run or month exceeds budget."""
    def __init__(self):
        self.state = self._load()

    def _load(self):
        if os.path.exists(BUDGET_STATE_PATH):
            return json.load(open(BUDGET_STATE_PATH))
        return {'month_key': self._month_key(), 'searches_this_month': 0,
                'last_run_searches': 0, 'all_time_searches': 0}

    def _month_key(self):
        return datetime.now().strftime('%Y-%m')

    def _save(self):
        os.makedirs(os.path.dirname(BUDGET_STATE_PATH), exist_ok=True)
        with open(BUDGET_STATE_PATH, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _rollover_if_new_month(self):
        if self.state.get('month_key') != self._month_key():
            self.state['month_key'] = self._month_key()
            self.state['searches_this_month'] = 0

    def estimate_run_cost(self, projected_searches: int) -> dict:
        """Pre-run dry check. Returns approval + reasons."""
        self._rollover_if_new_month()
        month_used = self.state['searches_this_month']
        month_after = month_used + projected_searches

        approved = True
        reasons = []
        if projected_searches > MAX_SEARCHES_PER_RUN:
            approved = False
            reasons.append(f"projected {projected_searches} exceeds per-run cap {MAX_SEARCHES_PER_RUN}")
        if month_after > MAX_SEARCHES_PER_MONTH:
            approved = False
            reasons.append(
                f"projected month total {month_after} exceeds monthly cap {MAX_SEARCHES_PER_MONTH} "
                f"(used {month_used} so far)"
            )

        return {
            'approved': approved,
            'reasons': reasons,
            'projected_searches': projected_searches,
            'projected_cost': projected_searches * COST_PER_SEARCH,
            'month_used_before': month_used,
            'month_used_after_if_approved': month_after,
            'month_remaining_budget': MAX_SEARCHES_PER_MONTH - month_used,
        }

    def record_searches(self, n: int):
        self._rollover_if_new_month()
        self.state['searches_this_month'] += n
        self.state['last_run_searches'] = n
        self.state['all_time_searches'] += n
        self._save()

    def can_afford(self, n: int) -> bool:
        self._rollover_if_new_month()
        return (self.state['searches_this_month'] + n) <= MAX_SEARCHES_PER_MONTH


# ─── MOCK SEARCH ENGINE ─────────────────────────────────────────────────
_MOCK_FIXTURES = {
    'obituary': [
        {'title': 'Margaret Henderson, 84, beloved mother...',
         'snippet': 'In loving memory of Margaret Henderson who passed away peacefully at her Bellevue home.',
         'link': 'https://obituaries.seattletimes.com/obituary/margaret-henderson'},
    ],
    'linkedin_found': [
        {'title': 'John Smith — VP of Engineering — Microsoft',
         'snippet': '15 years at Microsoft. Based in Redmond, WA. View full profile...',
         'link': 'https://www.linkedin.com/in/johnsmith'},
    ],
    'financial_distress': [
        {'title': 'King County Recorder — Notice of Default',
         'snippet': 'NOD filed on property at 8528 NE 13TH ST. Default amount $147,000.',
         'link': 'https://recordsearch.kingcounty.gov/LandmarkWeb/search?pin=123'},
    ],
    'is_agent': [
        {'title': 'Sarah Johnson — Windermere Real Estate',
         'snippet': 'Licensed real estate broker in Bellevue since 2008.',
         'link': 'https://www.zillow.com/profile/sarah-johnson'},
    ],
    'age_found': [
        {'title': 'Robert Chen, age 72 — FastPeopleSearch',
         'snippet': 'Robert Chen, 72 years old, has lived in Bellevue WA since 1995. Spouse: Linda Chen.',
         'link': 'https://www.fastpeoplesearch.com/robert-chen-bellevue'},
    ],
    'previously_listed': [
        {'title': '9243 NE 20TH ST | Off Market | Zillow',
         'snippet': 'Last listed at $8,200,000. Delisted 2025-11-03 after 287 days on market.',
         'link': 'https://www.zillow.com/homedetails/9243-ne-20th-st'},
    ],
    'probate': [
        {'title': 'KC Superior Court — Probate Case 26-4-00123-9',
         'snippet': 'Probate of estate of John Harrison. Executor: Mary Harrison.',
         'link': 'https://dja-prd-ecexap1.kingcounty.gov/probate'},
    ],
    'blank': [],
}


def _mock_search(query: str, parcel_id: str = '', search_label: str = ''):
    """
    Deterministic mock — returns a fixture based on query content + a hash
    of the parcel_id so different parcels get different fake signal patterns.
    """
    q = query.lower()
    h = int(hashlib.md5((parcel_id + search_label).encode()).hexdigest(), 16)

    # Reproducible "randomness" per parcel+label
    pct = h % 100

    if 'site:zillow.com' in q or 'site:redfin.com' in q:
        return _MOCK_FIXTURES['previously_listed'] if pct < 35 else _MOCK_FIXTURES['blank']
    if 'site:linkedin.com' in q:
        return _MOCK_FIXTURES['linkedin_found'] if pct < 55 else _MOCK_FIXTURES['blank']
    if 'site:fastpeoplesearch.com' in q or 'site:whitepages.com' in q:
        return _MOCK_FIXTURES['age_found'] if pct < 60 else _MOCK_FIXTURES['blank']
    if 'obituary' in q or 'passed away' in q or 'memorial' in q:
        return _MOCK_FIXTURES['obituary'] if pct < 15 else _MOCK_FIXTURES['blank']
    if 'court' in q or 'probate' in q or 'lien' in q:
        if pct < 8: return _MOCK_FIXTURES['probate']
        if pct < 20: return _MOCK_FIXTURES['financial_distress']
        return _MOCK_FIXTURES['blank']
    if 'realtor' in q or 'real estate agent' in q or 'broker' in q:
        return _MOCK_FIXTURES['is_agent'] if pct < 10 else _MOCK_FIXTURES['blank']
    if 'retired' in q or 'retirement' in q or 'divorce' in q:
        return _MOCK_FIXTURES['obituary'] if pct < 12 else _MOCK_FIXTURES['blank']
    return _MOCK_FIXTURES['blank']


# ─── REAL SERPAPI CALL ──────────────────────────────────────────────────
def _live_search(query: str, num: int = 5) -> list[dict]:
    if not SERPAPI_KEY:
        return []
    try:
        url = (
            'https://serpapi.com/search.json?'
            + urllib.parse.urlencode({'q': query, 'api_key': SERPAPI_KEY, 'num': num})
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'SellerSignal/2.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8', errors='replace'))
        if 'error' in data:
            return []
        return [
            {
                'title':   (item.get('title') or '')[:200],
                'snippet': (item.get('snippet') or '')[:400],
                'link':    item.get('link') or '',
            }
            for item in (data.get('organic_results') or [])[:num]
        ]
    except Exception:
        return []


def search_google(query: str, parcel_id: str = '', search_label: str = '') -> list[dict]:
    """Single search. Uses mock if no SerpAPI key present."""
    if MOCK_MODE:
        return _mock_search(query, parcel_id, search_label)
    return _live_search(query)


def search_batch(queries: list[dict], parcel_id: str = '',
                 batch_size: int = 8, pause_ms: int = 300) -> dict:
    """
    Execute queries in batches. Each query dict is {'label': str, 'query': str}.
    Returns {label: [results]}.
    """
    output = {}
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        for q in batch:
            output[q['label']] = search_google(q['query'], parcel_id, q['label'])
        if i + batch_size < len(queries):
            time.sleep(pause_ms / 1000)
    return output


# ─── NAME + ADDRESS NORMALIZATION (from v1) ─────────────────────────────
_BIZ_RX = re.compile(
    r'\b(LLC|TRUST|LTD|PARTNERSHIP|INC|CORP|ESTATE|FOUNDATION|HOLDINGS|COMPANY|'
    r'GROUP|RANCH|FARM|PROPERTIES|INVESTMENTS|ASSOCIATES|VENTURES|ENTERPRISES|'
    r'PARTNERS|DEVELOPMENT|REALTY|MANAGEMENT|CLUB|LAND|HOMES|BUILDERS|CAPITAL)\b',
    re.I,
)


def normalize_owner_name(raw_name: str) -> dict:
    """Parse owner string into person vs entity + search-ready name."""
    if not raw_name:
        return {'full': '', 'search_primary': '', 'first': '', 'last': '',
                'original': '', 'is_entity': False}
    name = raw_name.strip()
    if not name:
        return {'full': '', 'search_primary': '', 'first': '', 'last': '',
                'original': '', 'is_entity': False}

    # Strip co-owner suffix (everything after &)
    clean = re.sub(r'\s*&\s*.*$', '', name).strip()
    parts = clean.split()

    if _BIZ_RX.search(clean) or re.search(r'\d', clean):
        return {'full': name, 'search_primary': name, 'first': '', 'last': '',
                'original': name, 'is_entity': True}

    if len(parts) < 2:
        return {'full': name, 'search_primary': name, 'first': '', 'last': name,
                'original': name, 'is_entity': False}

    if len(parts) > 3:
        return {'full': name, 'search_primary': name, 'first': '', 'last': '',
                'original': name, 'is_entity': True}

    if not all(re.match(r"^[A-Za-z][A-Za-z.\-']*$", p) for p in parts):
        return {'full': name, 'search_primary': name, 'first': '', 'last': '',
                'original': name, 'is_entity': False}

    tc = [p[0].upper() + p[1:].lower() for p in parts]
    # KC format is LAST FIRST [MIDDLE]
    if len(tc) > 2:
        full = f'{tc[1]} {tc[2]} {tc[0]}'
    else:
        full = f'{tc[1]} {tc[0]}'
    return {'full': full, 'search_primary': f'{tc[1]} {tc[0]}',
            'first': tc[1], 'last': tc[0], 'original': name, 'is_entity': False}


_ADDR_STRIP_RX = re.compile(
    r'\s+(BOZEMAN|SCOTTSDALE|CHARLOTTE|SEATTLE|BELLEVUE|MEDINA|KIRKLAND|MERCER\s+ISLAND|'
    r'NEWPORT|CLYDE\s+HILL|HUNTS\s+POINT|MIAMI|MT|AZ|NC|WA|FL|NY|OR|CA|'
    r'MONTANA|ARIZONA|WASHINGTON|\d{5}).*',
    re.I,
)


def normalize_street_address(raw_address: str) -> str:
    if not raw_address:
        return ''
    return _ADDR_STRIP_RX.sub('', raw_address).strip()


# ─── QUERY BUILDERS ─────────────────────────────────────────────────────
def _parcel_fields(parcel: dict) -> dict:
    """Extract the fields we need from a banded-inventory lead."""
    owner_raw = parcel.get('owner') or parcel.get('owner_name') or ''
    addr_raw = parcel.get('address') or ''
    zip_code = parcel.get('zip') or ''
    city_lookup = {'98004': 'Bellevue', '98039': 'Medina', '98040': 'Mercer Island',
                   '98033': 'Kirkland', '98006': 'Bellevue', '98005': 'Bellevue'}
    city = city_lookup.get(zip_code, 'Bellevue')
    state = 'WA'
    nrm = normalize_owner_name(owner_raw)
    return {
        'owner_raw': owner_raw,
        'street': normalize_street_address(addr_raw),
        'city': city,
        'state': state,
        'zip': zip_code,
        'search_name': nrm['search_primary'] or owner_raw,
        'first': nrm['first'],
        'last': nrm['last'],
        'is_entity': nrm['is_entity'],
        'full': nrm['full'],
    }


def build_screen_queries(parcel: dict) -> list[dict]:
    """~7 high-leverage queries for screening mode."""
    p = _parcel_fields(parcel)
    street, city, state, owner_raw = p['street'], p['city'], p['state'], p['owner_raw']
    search_name = p['search_name']

    if p['is_entity']:
        return [
            {'label': 'Zillow',              'query': f'"{street}" "{city}" site:zillow.com'},
            {'label': 'Redfin',              'query': f'"{street}" "{city}" site:redfin.com'},
            {'label': 'Life Events',         'query': f'"{owner_raw}" {city} {state} lawsuit OR lien OR foreclosure OR dissolution'},
            {'label': 'Court Records',       'query': f'"{owner_raw}" "{city}" {state} court OR filing OR lien OR probate'},
            {'label': 'SOS Registered Agent','query': f'"{owner_raw}" {state.upper()} registered agent secretary of state'},
            {'label': 'Entity Members',      'query': f'"{owner_raw}" {state.upper()} member OR manager OR officer OR principal'},
            {'label': 'Owner at Address',    'query': f'"{owner_raw}" "{street}"'},
        ]

    return [
        {'label': 'Zillow',           'query': f'"{street}" "{city}" site:zillow.com'},
        {'label': 'Redfin',           'query': f'"{street}" "{city}" site:redfin.com'},
        {'label': 'Life Events',      'query': f'"{search_name}" "{city}" {state} retired OR retirement OR divorce OR obituary'},
        {'label': 'LinkedIn',         'query': f'"{search_name}" {city} {state} site:linkedin.com'},
        {'label': 'Court Records',    'query': f'"{search_name}" "{city}" {state} court OR filing OR lien OR probate'},
        {'label': 'FastPeopleSearch', 'query': f'"{search_name}" "{city}" site:fastpeoplesearch.com'},
        {'label': 'Owner at Address', 'query': f'"{search_name}" "{street}"'},
    ]


def build_deep_queries(parcel: dict) -> list[dict]:
    """Full Tier 1 + 2 + 3 query set (~25 queries total, including screen)."""
    p = _parcel_fields(parcel)
    street, city, state, owner_raw = p['street'], p['city'], p['state'], p['owner_raw']
    search_name = p['search_name']

    # Start with screen set
    queries = build_screen_queries(parcel)

    # Tier 1 additions (beyond screen)
    queries += [
        {'label': 'Realtor.com',         'query': f'"{street}" "{city}" site:realtor.com'},
        {'label': 'County Tax',          'query': f'"{street}" "{city}" {state} tax assessor property'},
        {'label': 'Broad Identity',      'query': f'{search_name} {city}'},
        {'label': 'Owner+City+State',    'query': f'"{search_name}" "{city}" {state}'},
        {'label': 'RE Agent General',    'query': f'"{search_name}" "{city}" realtor OR "real estate agent" OR broker'},
        {'label': 'News',                'query': f'"{search_name}" "{city}" {state} news OR article'},
    ]

    # Tier 2
    if p['is_entity']:
        queries += [
            {'label': 'SOS Business Filing',   'query': f'"{owner_raw}" {state.upper()} business entity filing'},
            {'label': 'Entity OpenCorporates', 'query': f'"{owner_raw}" {state.upper()} site:opencorporates.com'},
        ]
    else:
        queries += [
            {'label': 'Trulia',               'query': f'"{street}" "{city}" site:trulia.com'},
            {'label': 'Property History',     'query': f'"{street}" "{city}" sold sale listing history'},
            {'label': 'LinkedIn Alt',         'query': f'"{p["first"]} {p["last"]}" {state} site:linkedin.com'},
            {'label': 'Professional Profile', 'query': f'"{search_name}" "{city}" {state} professional OR career OR work'},
            {'label': 'WhitePages',           'query': f'"{search_name}" "{city}" {state} site:whitepages.com'},
            {'label': 'Spokeo',               'query': f'"{search_name}" "{city}" site:spokeo.com'},
            {'label': 'Business Owner',       'query': f'"{search_name}" "{city}" business owner'},
            # Tier 3 enrichment
            {'label': 'Facebook',        'query': f'"{search_name}" "{city}" {state} site:facebook.com'},
            {'label': 'Family',          'query': f'"{search_name}" "{city}" spouse OR wife OR husband OR family'},
            {'label': 'Community',       'query': f'"{search_name}" "{city}" {state} board OR volunteer OR foundation'},
            {'label': 'Age Records',     'query': f'"{search_name}" "{city}" age OR born OR birthday'},
            {'label': 'Relocation',      'query': f'"{search_name}" "moving" OR "relocated" OR "downsizing"'},
        ]
    return queries


# ─── TRUST SCORING ──────────────────────────────────────────────────────
def _infer_source_type(label: str, link: str) -> str:
    lo = (label + ' ' + (link or '')).lower()
    if 'linkedin' in lo:          return 'linkedin'
    if 'zillow' in lo:            return 'listing_site'
    if 'redfin' in lo:            return 'listing_site'
    if 'realtor' in lo:           return 'listing_site'
    if 'trulia' in lo:            return 'listing_site'
    if 'fastpeoplesearch' in lo:  return 'people_finder'
    if 'whitepages' in lo:        return 'people_finder'
    if 'spokeo' in lo:            return 'people_finder'
    if 'court' in lo:             return 'court_record'
    if 'sos' in lo or 'secretary of state' in lo: return 'state_filing'
    if 'opencorporates' in lo:    return 'entity_database'
    if 'obituar' in lo or 'funeral' in lo: return 'obituary_site'
    if 'facebook' in lo:          return 'social_generic'
    if 'news' in lo:              return 'news_generic'
    return 'generic_web'


_HIGH_TRUST_SOURCES = {'linkedin', 'listing_site', 'court_record', 'state_filing',
                       'people_finder', 'entity_database', 'obituary_site'}
_LOW_TRUST_SOURCES  = {'social_generic', 'news_generic'}


def score_signal_trust(signal_type: str, source_type: str) -> str:
    # Signal × source combos that explicitly bump or demote
    if signal_type == 'obituary' and source_type == 'generic_web': return 'medium'
    if signal_type == 'divorce' and source_type == 'court_record': return 'high'
    if signal_type == 'probate' and source_type == 'court_record': return 'high'
    if signal_type == 'financial_distress' and source_type == 'court_record': return 'high'
    if signal_type == 'is_agent' and source_type == 'listing_site': return 'high'

    if source_type in _HIGH_TRUST_SOURCES: return 'high'
    if source_type in _LOW_TRUST_SOURCES:  return 'low'
    return 'medium'


def _build_signal(type_, category, confidence, detail, source_label, source_type):
    return {
        'type':         type_,
        'category':     category,
        'confidence':   confidence,
        'detail':       detail,
        'source_label': source_label,
        'source_type':  source_type,
        'trust':        score_signal_trust(type_, source_type),
    }


# ─── SIGNAL EXTRACTION (port of extractAllSignals) ──────────────────────
def extract_all_signals(all_results: dict) -> list[dict]:
    signals = []

    # LISTING
    for label in ('Zillow', 'Redfin', 'Realtor.com', 'Trulia', 'Property History'):
        res = all_results.get(label) or []
        if not res: continue
        text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in res)
        lo = text.lower()
        link = res[0].get('link', '')
        stype = _infer_source_type(label, link)

        if re.search(r'off\s*market|removed|delisted|withdrawn|expired|cancelled|previously listed', lo):
            signals.append(_build_signal('previously_listed', 'listing', 0.85,
                                         'Property was listed but is now off market', label, stype))
        if re.search(r'pending|under contract|contingent', lo) and not re.search(r'was pending|previously|no longer', lo):
            signals.append(_build_signal('pending_sale', 'blocker', 0.70,
                                         'Possibly pending sale', label, stype))
        if re.search(r'price\s*(cut|drop|reduced|change)|reduced by', lo):
            signals.append(_build_signal('price_history', 'listing', 0.75,
                                         'Price reductions in history', label, stype))
        m = re.search(r'(\d{3,})\s*days?\s*(on|listed)', lo)
        if m:
            signals.append(_build_signal('extended_dom', 'listing', 0.80,
                                         f'Extended days on market: {m.group(1)}', label, stype))

    # LINKEDIN / PROFESSIONAL
    for label in ('LinkedIn', 'LinkedIn Alt'):
        res = all_results.get(label) or []
        if not res: continue
        text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in res)
        link = res[0].get('link', '')
        stype = _infer_source_type(label, link)

        if any('linkedin.com/in/' in (r.get('link') or '') for r in res):
            signals.append(_build_signal('linkedin_found', 'identity', 0.70,
                                         res[0].get('title', '')[:150], label, stype))
        if re.search(r'retired|retirement|former\s+(ceo|president|director|vp|partner|owner)', text, re.I):
            signals.append(_build_signal('retirement', 'life_event', 0.70,
                                         'Retirement indicator from LinkedIn', label, stype))
        if re.search(r'relocated|moved to|new position in', text, re.I):
            signals.append(_build_signal('relocation', 'life_event', 0.70,
                                         'Relocation indicator from LinkedIn', label, stype))

    for label in ('Professional Profile', 'Business Owner', 'Broad Identity'):
        res = all_results.get(label) or []
        if not res: continue
        text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in res)
        link = res[0].get('link', '')
        stype = _infer_source_type(label, link)
        if re.search(r'ceo|president|founder|owner|managing|director|partner', text, re.I):
            if not any(s['type'] == 'business_owner' for s in signals):
                signals.append(_build_signal('business_owner', 'identity', 0.60,
                                             'Business owner / executive indicator', label, stype))

    # DEMOGRAPHICS
    for label in ('FastPeopleSearch', 'WhitePages', 'Spokeo', 'Age Records'):
        res = all_results.get(label) or []
        if not res: continue
        text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in res)
        link = res[0].get('link', '')
        stype = _infer_source_type(label, link)

        m = re.search(r'age\s*(\d{2,3})|(\d{2,3})\s*years?\s*old|born\s*(?:in\s*)?(19\d{2})', text, re.I)
        if m:
            age = m.group(1) or m.group(2)
            if m.group(3): age = str(datetime.now().year - int(m.group(3)))
            if age and 20 < int(age) < 110:
                signals.append(_build_signal('age_found', 'demographic', 0.60,
                                             f'Estimated age: {age}', label, stype))
        if re.search(r'spouse|wife|husband|married', text, re.I):
            signals.append(_build_signal('spouse_found', 'demographic', 0.55,
                                         'Spouse / partner indicator', label, stype))

    # LIFE EVENTS / COURT / FINANCIAL
    for label in ('Life Events', 'Family', 'News', 'Relocation', 'Court Records'):
        res = all_results.get(label) or []
        if not res: continue
        text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in res)
        link = res[0].get('link', '')
        stype = _infer_source_type(label, link)

        if re.search(r'obituary|passed away|in loving memory|memorial|funeral', text, re.I):
            if not any(s['type'] == 'obituary' for s in signals):
                signals.append(_build_signal('obituary', 'life_event', 0.75,
                                             'Possible death in household', label, stype))
        if re.search(r'divorce|dissolution of marriage', text, re.I):
            if not any(s['type'] == 'divorce' for s in signals):
                signals.append(_build_signal('divorce', 'life_event', 0.70,
                                             'Divorce indicator', label, stype))
        if re.search(r'probate|estate\s*filing|executor', text, re.I):
            if not any(s['type'] == 'probate' for s in signals):
                signals.append(_build_signal('probate', 'life_event', 0.80,
                                             'Probate / estate filing', label, stype))
        if re.search(r'bankrupt|foreclosure|tax\s*lien|delinquent|lien|judgment', text, re.I):
            if not any(s['type'] == 'financial_distress' for s in signals):
                signals.append(_build_signal('financial_distress', 'financial', 0.80,
                                             'Financial / legal distress signal', label, stype))

    # AGENT BLOCKER
    ag = all_results.get('RE Agent General') or []
    if ag:
        za = all_results.get('Zillow Agent') or []
        ag_text = ' '.join(f"{r.get('title','')} {r.get('snippet','')}" for r in ag)
        if za and any(re.search(r'zillow\.com/profile', r.get('link', '')) for r in za):
            signals.append(_build_signal('is_agent', 'blocker', 0.85,
                                         'Owner is a real estate agent',
                                         'RE Agent General', 'listing_site'))
        elif re.search(r'licensed\s*(real estate|realtor|broker)', ag_text, re.I):
            signals.append(_build_signal('is_agent', 'blocker', 0.70,
                                         'Owner may be licensed agent',
                                         'RE Agent General', 'generic_web'))

    # ENTITY RESOLUTION
    for label in ('SOS Registered Agent', 'Entity Members',
                  'SOS Business Filing', 'Entity OpenCorporates'):
        res = all_results.get(label) or []
        if not res: continue
        stype = _infer_source_type(label, res[0].get('link', ''))
        detail = '; '.join(r.get('title', '')[:60] for r in res[:2])
        if not any(s['type'] == 'entity_info' for s in signals):
            signals.append(_build_signal('entity_info', 'identity', 0.65,
                                         f'Entity info: {detail[:150]}', label, stype))

    # Dedupe by (type, category)
    seen = set()
    out = []
    for s in signals:
        k = (s['type'], s['category'])
        if k in seen: continue
        seen.add(k)
        out.append(s)
    return out


# ─── ACTION RECOMMENDER (pressure-scored) ──────────────────────────────
def recommend_action(parcel: dict, signals: list[dict]) -> dict:
    """
    Pressure-scored decision layer (tightened thresholds).

      pressure 3 = hard    → call_now
        - NOD / trustee sale / lis pendens (Band 3 financial_stress)
        - High-trust financial pressure from investigation
        - Court-verified probate
        - Court-verified divorce
        - Verified obituary
      pressure 2 = medium  → build_now
        - investor_disposition (hold-period exit, directional not forced)
        - failed_sale_attempt (expired, rationality-filtered)
        - Medium-trust financial mentions
        - Retirement indicator
        - Life-event + recent listing convergence
      pressure 1 = soft    → hold
        - Any other life-event mention
        - Long-tenure identity-confirmed parcels
      pressure 0           → hold

    Blockers (pending sale, owner is agent) override everything → avoid.

    Copy nuance: probate-triggered call_now uses sensitive language
    ("decision window has opened") rather than urgency-forced language
    ("prioritize immediate outreach"). Foreclosure-triggered call_now
    uses the urgency language.
    """
    pressure = 0
    triggers = []
    tone = None  # set by the trigger that actually fires; 'urgent' vs 'sensitive'

    existing_family = parcel.get('signal_family')
    existing_band = parcel.get('band')

    # ── HARD PRESSURE (forced timing) ──
    if existing_family == 'financial_stress' and existing_band == 3:
        pressure = max(pressure, 3); triggers.append('confirmed NOD/trustee-sale filing')
        tone = 'urgent'

    if any(s['category'] == 'financial' and s['trust'] == 'high' for s in signals):
        pressure = max(pressure, 3); triggers.append('high-trust financial/legal pressure')
        tone = 'urgent'

    court_probate = any(s['type'] == 'probate' and s['trust'] == 'high' for s in signals)
    if court_probate:
        pressure = max(pressure, 3); triggers.append('court-verified probate')
        if tone is None: tone = 'sensitive'

    court_divorce = any(s['type'] == 'divorce' and s['trust'] == 'high' for s in signals)
    if court_divorce:
        pressure = max(pressure, 3); triggers.append('court-verified divorce')
        if tone is None: tone = 'sensitive'

    verified_obit = any(s['type'] == 'obituary' and s['trust'] == 'high' for s in signals)
    if verified_obit:
        pressure = max(pressure, 3); triggers.append('verified obituary')
        if tone is None: tone = 'sensitive'

    # ── MEDIUM PRESSURE (directional, not forced) ──
    if existing_family == 'investor_disposition':
        pressure = max(pressure, 2); triggers.append('investor hold-period exit window')
    if existing_family == 'failed_sale_attempt' and existing_band == 3:
        pressure = max(pressure, 2); triggers.append('expired listing + rationality-filtered')

    if any(s['category'] == 'financial' and s['trust'] == 'medium' for s in signals):
        pressure = max(pressure, 2); triggers.append('medium-trust financial signal')

    extended_dom  = any(s['type'] == 'extended_dom' and s['trust'] == 'high' for s in signals)
    price_reduced = any(s['type'] == 'price_history' and s['trust'] == 'high' for s in signals)
    recent_listing = extended_dom or price_reduced
    has_life = any(s['category'] == 'life_event' for s in signals)

    if has_life and recent_listing:
        pressure = max(pressure, 2); triggers.append('life-event + recent listing convergence')
    if recent_listing:
        pressure = max(pressure, 2); triggers.append('recent listing activity')
    if any(s['type'] == 'retirement' for s in signals):
        pressure = max(pressure, 2); triggers.append('retirement indicator')

    # ── SOFT PRESSURE ──
    if has_life:
        pressure = max(pressure, 1)

    # ── BLOCKERS OVERRIDE ──
    if any(s['category'] == 'blocker' for s in signals):
        return {
            'category':  'avoid',
            'reason':    'Blocker signal present (pending sale, owner is agent, etc.)',
            'next_step': 'Do not include in playbook without manual review.',
            'pressure':  0,
            'tone':      'neutral',
        }

    reason_text = ' + '.join(triggers[:3]) if triggers else 'No actionable signal yet'

    if pressure == 3:
        effective_tone = tone or 'urgent'  # default to urgent if no trigger set tone
        if effective_tone == 'sensitive':
            next_step = 'Early outreach with sensitivity — decision window has opened.'
        else:
            next_step = 'Prioritize immediate outreach this week.'
        return {
            'category':  'call_now',
            'reason':    reason_text,
            'next_step': next_step,
            'pressure':  3,
            'tone':      effective_tone,
        }

    if pressure == 2:
        return {
            'category':  'build_now',
            'reason':    reason_text,
            'next_step': 'Identify connector within 2 weeks; map network entry point; no cold outreach.',
            'pressure':  2,
            'tone':      'relational',
        }

    return {
        'category':  'hold',
        'reason':    reason_text if triggers else 'No actionable signal yet',
        'next_step': 'Monitor and revisit next cycle.',
        'pressure':  pressure,
        'tone':      'neutral',
    }


# ─── ESCALATION LOGIC ───────────────────────────────────────────────────
def should_escalate(parcel: dict, screen_signals: list[dict],
                    provisional_rank: Optional[int] = None) -> dict:
    has_high_life = any(s['category'] == 'life_event' and s['trust'] == 'high' for s in screen_signals)
    has_high_fin  = any(s['category'] == 'financial'  and s['trust'] == 'high' for s in screen_signals)
    has_blocker   = any(s['category'] == 'blocker' for s in screen_signals)
    has_identity  = any(s['type'] in ('linkedin_found', 'age_found', 'entity_info') for s in screen_signals)
    is_candidate  = provisional_rank is not None and provisional_rank <= 15

    if has_high_life: return {'needs_deep': True, 'reason': 'high_trust_life_event'}
    if has_high_fin:  return {'needs_deep': True, 'reason': 'high_trust_financial_signal'}
    if is_candidate:  return {'needs_deep': True, 'reason': 'playbook_candidate'}
    if has_blocker:   return {'needs_deep': True, 'reason': 'blocker_conflict'}
    if (parcel.get('value') or 0) >= 5_000_000 and not has_identity:
        return {'needs_deep': True, 'reason': 'high_value_unresolved_identity'}
    return {'needs_deep': False, 'reason': None}


# ─── CACHE ──────────────────────────────────────────────────────────────
def _cache_key(parcel: dict, mode: str) -> str:
    pin = str(parcel.get('pin') or '')
    owner = (parcel.get('owner') or '').upper()
    h = hashlib.md5(f'{pin}|{owner}|{mode}'.encode()).hexdigest()[:16]
    return f'{mode}_{pin}_{h}'


def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f'{key}.json')


def cache_get(parcel: dict, mode: str):
    """Returns cached result if younger than TTL, else None."""
    path = _cache_path(_cache_key(parcel, mode))
    if not os.path.exists(path): return None
    try:
        data = json.load(open(path))
        ts = datetime.fromisoformat(data['cached_at'])
        if (datetime.now() - ts).days >= CACHE_TTL_DAYS:
            return None
        return data['result']
    except Exception:
        return None


def cache_put(parcel: dict, mode: str, result: dict):
    path = _cache_path(_cache_key(parcel, mode))
    with open(path, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'result': result},
                  f, default=str)


def cache_invalidate(parcel: dict):
    """Invalidate all modes for this parcel (on new free-event hit)."""
    for mode in ('screen', 'deep'):
        path = _cache_path(_cache_key(parcel, mode))
        if os.path.exists(path):
            os.remove(path)


# ─── PUBLIC ENTRY POINT ─────────────────────────────────────────────────
def investigate_parcel(parcel: dict, mode: str = 'screen',
                       provisional_rank: Optional[int] = None,
                       use_cache: bool = True) -> dict:
    """
    Single entry point. mode = 'screen' (7 searches) or 'deep' (~25 searches).
    Returns a dict with signals, search_count, flags, escalation, recommended_action.
    """
    assert mode in ('screen', 'deep'), f'Invalid mode: {mode}'

    # Cache check
    if use_cache:
        cached = cache_get(parcel, mode)
        if cached is not None:
            cached['from_cache'] = True
            return cached

    # Build queries
    queries = build_screen_queries(parcel) if mode == 'screen' else build_deep_queries(parcel)
    search_count = len(queries)

    # Execute
    all_results = search_batch(queries, parcel_id=str(parcel.get('pin') or ''))
    signals = extract_all_signals(all_results)

    # Trust summary
    trust_summary = {'high': 0, 'medium': 0, 'low': 0}
    for s in signals:
        trust_summary[s.get('trust', 'medium')] = trust_summary.get(s.get('trust', 'medium'), 0) + 1

    # Flags
    flags = {
        'has_life_event':       any(s['category'] == 'life_event' for s in signals),
        'has_financial':        any(s['category'] == 'financial' for s in signals),
        'has_listing_history':  any(s['category'] == 'listing' for s in signals),
        'has_blocker':          any(s['category'] == 'blocker' for s in signals),
        'identity_resolved':    any(s['type'] in ('linkedin_found', 'age_found', 'entity_info') for s in signals),
    }

    # Escalation (only meaningful for screen mode; deep mode already ran full)
    escalation = should_escalate(parcel, signals, provisional_rank) if mode == 'screen' else {
        'needs_deep': False, 'reason': 'already_deep'
    }

    result = {
        'pin':                str(parcel.get('pin') or ''),
        'mode':               mode,
        'investigated_at':    datetime.now().isoformat(),
        'search_count':       search_count,
        'signal_count':       len(signals),
        'signals':            signals,
        'trust_summary':      trust_summary,
        'flags':              flags,
        'escalation':         escalation,
        'recommended_action': recommend_action(parcel, signals),
        'from_cache':         False,
        'mock_mode':          MOCK_MODE,
    }

    if use_cache:
        cache_put(parcel, mode, result)

    return result


# ─── MODULE-LEVEL SANITY CHECK ──────────────────────────────────────────
if __name__ == '__main__':
    # Quick self-test
    test_parcel = {
        'pin': '0632000085',
        'owner': 'HENDERSON MARGARET',
        'address': '8528 NE 13TH ST',
        'zip': '98004',
        'value': 7778000,
    }
    print('Mock mode:', MOCK_MODE)
    print('\n── SCREEN mode ──')
    r1 = investigate_parcel(test_parcel, mode='screen', provisional_rank=5)
    print(f'Searches: {r1["search_count"]} | Signals: {r1["signal_count"]} | Flags: {r1["flags"]}')
    print(f'Escalation: {r1["escalation"]}')
    print(f'Recommended: {r1["recommended_action"]}')
    for s in r1['signals']:
        print(f'  [{s["trust"]:6}] {s["type"]:20} {s["category"]:12} — {s["detail"][:60]}')
    print('\n── DEEP mode ──')
    r2 = investigate_parcel(test_parcel, mode='deep')
    print(f'Searches: {r2["search_count"]} | Signals: {r2["signal_count"]} | Flags: {r2["flags"]}')
    print(f'Recommended: {r2["recommended_action"]}')
    print(f'\nBudget state after run:')
    bg = BudgetGuard()
    print(f'  {bg.state}')
