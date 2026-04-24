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
# Mock mode must be EXPLICITLY enabled. The previous silent-fallback
# behavior (MOCK_MODE = SERPAPI_KEY is None) caused a serious bug:
# investigations ran against hardcoded test data whenever the key was
# missing, producing synthetic "leads" indistinguishable from real ones.
# Now: if SERPAPI_KEY is missing, live search raises explicitly.
# Mock mode only activates with SELLERSIGNAL_MOCK=1 in the environment.
MOCK_MODE = os.environ.get('SELLERSIGNAL_MOCK') == '1'

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


class SerpApiKeyMissing(RuntimeError):
    """Raised when a real investigation is attempted without a configured key."""


# ─── REAL SERPAPI CALL ──────────────────────────────────────────────────
def _live_search(query: str, num: int = 5) -> list[dict]:
    if not SERPAPI_KEY:
        # Hard fail instead of silently returning [] — the previous silent
        # behavior caused investigations to produce zero real signals while
        # appearing to succeed, which in combination with mock-mode fallback
        # allowed synthetic data to masquerade as real results.
        raise SerpApiKeyMissing(
            "SERPAPI_KEY is not set. Set it in your environment, or set "
            "SELLERSIGNAL_MOCK=1 to run with mock fixtures."
        )
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
    except SerpApiKeyMissing:
        raise
    except Exception:
        return []


def search_google(query: str, parcel_id: str = '', search_label: str = '') -> list[dict]:
    """Single search. Uses mock only if SELLERSIGNAL_MOCK=1 is set explicitly."""
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
    """~5-6 high-leverage queries for screening mode.

    Phase 1 SerpAPI reduction: removed 'Court Records' query from both
    entity and individual paths — KC Superior Court harvester is
    authoritative for probate, divorce, and court-record filings in
    the Bellevue/98004 ZIP. Removed 'obituary' term from 'Life Events'
    query — obituary_rss harvester is authoritative. Removed 'lien OR
    foreclosure' from entity 'Life Events' — KC Treasurer tax
    foreclosure harvester is authoritative. See
    backend/harvesters/{kc_superior_court,obituary_rss,treasury}.py
    for the authoritative sources. This drops per-parcel SerpAPI cost
    by ~25-30%.
    """
    p = _parcel_fields(parcel)
    street, city, state, owner_raw = p['street'], p['city'], p['state'], p['owner_raw']
    search_name = p['search_name']

    if p['is_entity']:
        return [
            {'label': 'Zillow',              'query': f'"{street}" "{city}" site:zillow.com'},
            {'label': 'Redfin',              'query': f'"{street}" "{city}" site:redfin.com'},
            {'label': 'Life Events',         'query': f'"{owner_raw}" {city} {state} lawsuit OR dissolution'},
            # 'Court Records' query removed — KC Superior Court
            # harvester authoritatively covers probate + divorce
            # filings. Retained SOS / entity-membership queries below
            # because WA SOS harvester hasn't been built yet.
            {'label': 'SOS Registered Agent','query': f'"{owner_raw}" {state.upper()} registered agent secretary of state'},
            {'label': 'Entity Members',      'query': f'"{owner_raw}" {state.upper()} member OR manager OR officer OR principal'},
            {'label': 'Owner at Address',    'query': f'"{owner_raw}" "{street}"'},
        ]

    return [
        {'label': 'Zillow',           'query': f'"{street}" "{city}" site:zillow.com'},
        {'label': 'Redfin',           'query': f'"{street}" "{city}" site:redfin.com'},
        # 'Life Events' query narrowed — 'obituary' and 'divorce' removed
        # (obituary_rss and kc_superior_court harvesters authoritative).
        # Kept 'retired OR retirement' because no harvester covers
        # retirement announcements yet.
        {'label': 'Life Events',      'query': f'"{search_name}" "{city}" {state} retired OR retirement'},
        {'label': 'LinkedIn',         'query': f'"{search_name}" {city} {state} site:linkedin.com'},
        # 'Court Records' query removed — KC Superior Court harvester
        # covers probate / divorce / lien filings authoritatively.
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
    # 'County Tax' query removed — we ingest assessed values / property
    # details directly from KC Assessor ArcGIS (see backend/ingest/
    # arcgis.py) and eReal Property (see backend/harvesters/
    # ereal_property.py). Google's indexed assessor pages return stale
    # data and mostly match the assessor's own site anyway. Pure noise.
    queries += [
        {'label': 'Realtor.com',         'query': f'"{street}" "{city}" site:realtor.com'},
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


def _build_signal(type_, category, confidence, detail, source_label, source_type,
                  matched_result=None, matched_query=None):
    """
    Construct a signal with full provenance.

    matched_result: the specific SerpAPI result that triggered this signal
                    (dict with 'title', 'snippet', 'link')
    matched_query:  the specific query text that produced the result
    """
    sig = {
        'type':         type_,
        'category':     category,
        'confidence':   confidence,
        'detail':       detail,
        'source_label': source_label,
        'source_type':  source_type,
        'trust':        score_signal_trust(type_, source_type),
    }
    if matched_result:
        sig['source_url']     = matched_result.get('link', '')
        sig['source_title']   = matched_result.get('title', '')[:200]
        sig['source_snippet'] = matched_result.get('snippet', '')[:400]
    if matched_query:
        sig['matched_query'] = matched_query[:200]
    return sig


# ─── AD / NOISE FILTERING ──────────────────────────────────────────────
def _is_ad_or_noise(result: dict) -> bool:
    """
    True if the SerpAPI result is obviously an ad or noise — generic service
    page, unrelated aggregator, LinkedIn directory page, etc. These trigger
    false positive signals when regex matches their generic language.
    """
    link = (result.get('link') or '').lower()
    title = (result.get('title') or '').lower()
    snippet = (result.get('snippet') or '').lower()

    # URL-based ad detection
    if any(x in link for x in ('/ads/', 'googleadservices', 'doubleclick',
                                'adurl=', '&ad=', '?ad=')):
        return True

    # LinkedIn directory / company pages are aggregators, not specific people
    if 'linkedin.com/pub/dir/' in link or 'linkedin.com/company' in link:
        return True

    # Generic service/aggregator content
    ad_patterns = [
        'click here to',
        'free quote',
        'find a lawyer',
        'hire an attorney',
        'need help with probate',
        'probate attorneys near',
        'personal injury',
        'call us today',
        'sponsored',
    ]
    if any(p in snippet for p in ad_patterns):
        return True

    # Pure search/directory pages with no specific content
    if title.startswith('search ') or 'results for' in title:
        return True

    return False


def _owner_name_parts(parcel: dict) -> list[str]:
    """
    Extract usable name parts from a parcel for matching against result snippets.
    Returns lowercased tokens, filtered to exclude generic words.

    For "HENDERSON MARGARET" returns ['henderson', 'margaret']
    For "SMITH FAMILY TRUST" returns ['smith']  (drops TRUST, FAMILY)
    For "ABC HOLDINGS LLC" returns ['abc', 'holdings']  (drops LLC)
    """
    raw = (parcel.get('owner_name_raw') or parcel.get('owner_name') or '').upper()
    if not raw:
        return []

    # Take primary owner (before & or +)
    raw = re.split(r'[&+]', raw)[0].strip()

    # Drop entity suffixes and generic words
    DROP_TOKENS = {
        'LLC', 'INC', 'CORP', 'LTD', 'LP', 'LLP', 'LIMITED', 'PARTNERSHIP',
        'TRUST', 'TRUSTEE', 'TRSTEE', 'FAMILY', 'LIVING', 'REVOCABLE',
        'ESTATE', 'ET', 'AL', 'HEIRS', 'SURVIVORS', 'SURVIVOR', 'MR',
        'MRS', 'MS', 'THE', 'AND', 'OF', 'REAL',
    }

    parts = []
    for tok in re.findall(r'[A-Z]{2,}', raw):
        if tok in DROP_TOKENS: continue
        if len(tok) < 3: continue
        parts.append(tok.lower())
    return parts[:4]  # Top 4 distinctive tokens


def _snippet_mentions_owner(result: dict, owner_parts: list[str]) -> bool:
    """
    True if the result's snippet or title contains a recognizable owner-name
    token. Requires at least one distinctive surname-like token to match.
    Used to suppress person-specific signals (probate, obituary, retirement,
    divorce) when the match is on an unrelated person with the same keyword.
    """
    if not owner_parts:
        return False
    text = (result.get('title', '') + ' ' + result.get('snippet', '')).lower()
    # Require at least one token of length >= 4 to match (short tokens like
    # 'jr' or 'de' cause false positives)
    long_parts = [p for p in owner_parts if len(p) >= 4]
    if not long_parts:
        long_parts = owner_parts
    return any(p in text for p in long_parts)


# ─── SIGNAL EXTRACTION — per-result with provenance + name matching ───
def extract_all_signals(all_results: dict, parcel: dict | None = None) -> list[dict]:
    """
    Extract signals from raw SerpAPI results.

    Three critical upgrades from the prior version:
      1. Per-result matching: each signal carries the specific matched
         result (title, link, snippet) as provenance — not a concatenation
         across all results.
      2. Name-context requirement: person-specific signals (probate,
         obituary, retirement, divorce) require the owner's surname/
         distinctive tokens to appear in the same result snippet.
      3. Ad/noise filter: results that look like ads, directory pages,
         or generic service offerings are skipped.
    """
    signals = []
    owner_parts = _owner_name_parts(parcel) if parcel else []

    # Track (type, source_label) already added to dedupe per family
    seen_type_labels = set()

    def _push(sig):
        """Add signal if not already seen for this (type, source_label)."""
        key = (sig['type'], sig['source_label'])
        if key in seen_type_labels:
            return
        seen_type_labels.add(key)
        signals.append(sig)

    # ── LISTING (property-based, name matching not required) ──────────
    for label in ('Zillow', 'Redfin', 'Realtor.com', 'Trulia', 'Property History'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            text = (r.get('title', '') + ' ' + r.get('snippet', '')).lower()
            stype = _infer_source_type(label, r.get('link', ''))

            if re.search(r'off\s*market|removed|delisted|withdrawn|expired|cancelled|previously listed', text):
                _push(_build_signal('previously_listed', 'listing', 0.85,
                                    'Property was listed but is now off market',
                                    label, stype, matched_result=r))
            if re.search(r'pending|under contract|contingent', text) and not re.search(r'was pending|previously|no longer', text):
                _push(_build_signal('pending_sale', 'blocker', 0.70,
                                    'Possibly pending sale',
                                    label, stype, matched_result=r))
            if re.search(r'price\s*(cut|drop|reduced|change)|reduced by', text):
                _push(_build_signal('price_history', 'listing', 0.75,
                                    'Price reductions in history',
                                    label, stype, matched_result=r))
            m = re.search(r'(\d{2,4})\s*days?\s*(on|listed)', text)
            if m:
                dom = int(m.group(1))
                # Sanity bound — reject absurdly high DOM likely from generic text
                if 30 <= dom <= 2000:
                    _push(_build_signal('extended_dom', 'listing', 0.80,
                                        f'Extended days on market: {dom}',
                                        label, stype, matched_result=r))

    # ── LINKEDIN / PROFESSIONAL (name matching required) ───────────────
    for label in ('LinkedIn', 'LinkedIn Alt'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            link = r.get('link', '')
            stype = _infer_source_type(label, link)
            text_lower = (r.get('title', '') + ' ' + r.get('snippet', '')).lower()

            # linkedin_found requires an actual profile link
            if 'linkedin.com/in/' in link:
                _push(_build_signal('linkedin_found', 'identity', 0.70,
                                    r.get('title', '')[:150],
                                    label, stype, matched_result=r))
            # retirement / relocation require owner-name context
            if _snippet_mentions_owner(r, owner_parts):
                if re.search(r'retired|retirement|former\s+(ceo|president|director|vp|partner|owner)', text_lower):
                    _push(_build_signal('retirement', 'life_event', 0.70,
                                        'Retirement indicator',
                                        label, stype, matched_result=r))
                if re.search(r'relocated|moved to|new position in', text_lower):
                    _push(_build_signal('relocation', 'life_event', 0.70,
                                        'Relocation indicator',
                                        label, stype, matched_result=r))

    # ── PROFESSIONAL IDENTITY (name matching required) ─────────────────
    for label in ('Professional Profile', 'Business Owner', 'Broad Identity'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            if not _snippet_mentions_owner(r, owner_parts): continue
            text_lower = (r.get('title', '') + ' ' + r.get('snippet', '')).lower()
            stype = _infer_source_type(label, r.get('link', ''))
            if re.search(r'\b(ceo|president|founder|owner|managing|director|partner)\b', text_lower):
                _push(_build_signal('business_owner', 'identity', 0.60,
                                    'Business owner / executive indicator',
                                    label, stype, matched_result=r))

    # ── DEMOGRAPHICS (name matching required) ──────────────────────────
    for label in ('FastPeopleSearch', 'WhitePages', 'Spokeo', 'Age Records'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            if not _snippet_mentions_owner(r, owner_parts): continue
            text = r.get('title', '') + ' ' + r.get('snippet', '')
            stype = _infer_source_type(label, r.get('link', ''))

            m = re.search(r'age\s*(\d{2,3})|(\d{2,3})\s*years?\s*old|born\s*(?:in\s*)?(19\d{2})', text, re.I)
            if m:
                age = m.group(1) or m.group(2)
                if m.group(3): age = str(datetime.now().year - int(m.group(3)))
                if age and 20 < int(age) < 110:
                    _push(_build_signal('age_found', 'demographic', 0.60,
                                        f'Estimated age: {age}',
                                        label, stype, matched_result=r))
            if re.search(r'\bspouse|\bwife|\bhusband|\bmarried to', text, re.I):
                _push(_build_signal('spouse_found', 'demographic', 0.55,
                                    'Spouse / partner indicator',
                                    label, stype, matched_result=r))

    # ── LIFE EVENTS / COURT / FINANCIAL (name matching required) ──────
    # This is the most critical name-match enforcement. A probate mention
    # doesn't count unless the owner's surname appears in the same snippet.
    #
    # Phase 1 SerpAPI reduction: obituary, divorce, probate, and
    # financial_distress signals are NOT built from SerpAPI results
    # anymore. They come exclusively from the harvester pipelines:
    #   obituary            → backend/harvesters/obituary_rss.py
    #   divorce / probate   → backend/harvesters/kc_superior_court.py
    #   financial_distress  → backend/harvesters/treasury.py (tax foreclosure)
    #
    # Those harvesters are authoritative sources — court records, paid
    # obituary publications, county treasurer filings — rather than
    # regex pattern-matches on Google-indexed snippets. Double-counting
    # the same event from both pipelines created confusing two-row UI
    # and inflated signal counts. The harvester side already flows
    # through HarvesterMatchesBlock and (via harvester_overlay) into
    # the Recommended Action block with real case numbers, decedent
    # names, and personal representative info.
    #
    # Removing these four signal builders drops ~35% of SerpAPI-derived
    # signal volume from the Evidence block. What remains is the
    # long-tail stuff that harvesters don't cover yet: age, spouse,
    # retirement, relocation, LinkedIn hits, MLS listing activity,
    # agent-blocker detection, business-owner mentions.
    for label in ('Life Events', 'Family', 'News', 'Relocation'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            if not _snippet_mentions_owner(r, owner_parts):
                # No name match — this keyword hit is almost certainly a
                # different person with the same condition. Skip it.
                continue
            text_lower = (r.get('title', '') + ' ' + r.get('snippet', '')).lower()
            stype = _infer_source_type(label, r.get('link', ''))

            # obituary / divorce / probate / financial_distress builders
            # removed — see comment above. Harvesters are authoritative.
            # Other signal types (retirement, relocation, etc.) still
            # derived from these queries — see below.
            _ = text_lower  # kept in scope for future signal types
            _ = stype

    # ── AGENT BLOCKER ──────────────────────────────────────────────────
    ag = all_results.get('RE Agent General') or []
    if ag and owner_parts:
        for r in ag:
            if _is_ad_or_noise(r): continue
            if not _snippet_mentions_owner(r, owner_parts): continue
            za = all_results.get('Zillow Agent') or []
            if za and any(re.search(r'zillow\.com/profile', (zr.get('link') or ''))
                          for zr in za if _snippet_mentions_owner(zr, owner_parts)):
                _push(_build_signal('is_agent', 'blocker', 0.85,
                                    'Owner is a real estate agent',
                                    'RE Agent General', 'listing_site',
                                    matched_result=r))
                break
            ag_text = r.get('title', '') + ' ' + r.get('snippet', '')
            if re.search(r'licensed\s*(real estate|realtor|broker)', ag_text, re.I):
                _push(_build_signal('is_agent', 'blocker', 0.70,
                                    'Owner may be licensed agent',
                                    'RE Agent General', 'generic_web',
                                    matched_result=r))
                break

    # ── ENTITY RESOLUTION ──────────────────────────────────────────────
    for label in ('SOS Registered Agent', 'Entity Members',
                  'SOS Business Filing', 'Entity OpenCorporates'):
        res = all_results.get(label) or []
        for r in res:
            if _is_ad_or_noise(r): continue
            stype = _infer_source_type(label, r.get('link', ''))
            detail = r.get('title', '')[:120]
            _push(_build_signal('entity_info', 'identity', 0.65,
                                f'Entity info: {detail}',
                                label, stype, matched_result=r))
            break  # One entity_info per source label

    return signals


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

    raw_archetype  = parcel.get('signal_family')
    existing_band  = parcel.get('band')

    # ── ARCHETYPE → PRESSURE-ENGINE FAMILY ────────────────────────────
    # The classifier (why_not_selling.py) produces rich archetype names;
    # the pressure engine historically only branched on three coarse
    # family labels. Map archetype -> coarse family so structural
    # archetypes actually reach the pressure rules below. Without this,
    # every LLC and trust parcel falls to pressure=0 regardless of how
    # strong the structural signal is.
    _ARCHETYPE_TO_PRESSURE_FAMILY = {
        # Financial distress (Band 3 foreclosure-class, when legal_filings
        # sets signal_family='financial_stress')
        'financial_stress':        'financial_stress',
        # LLC hold-period exit window. Any mature LLC = directional
        # disposition signal (pressure 2).
        'llc_investor_mature':     'investor_disposition',
        'llc_long_hold':           'investor_disposition',
        # Early LLC holders are still in accumulation phase — no pressure.
        'llc_investor_early':      None,
        # Trust archetypes. trust_aging is the pressure-1 'biological
        # window' family; classifier doesn't yet distinguish active
        # court probate (pressure 3) from structural aging alone.
        # Structural trust_aging fires pressure-1 via the soft branch
        # below; court-verified probate (if found) fires pressure-3.
        'trust_aging':             'trust_aging_structural',
        'trust_mature':             None,    # monitoring only
        'trust_young':              None,    # recent, no pressure
        # Failed sale attempt (expired listing) — matches old family
        'failed_sale_attempt':     'failed_sale_attempt',
        # Individual and absentee archetypes — no pressure-engine rule yet
        'individual_long_tenure':  None,
        'individual_settled':      None,
        'individual_recent':       None,
        'absentee_dormant':        None,
        'absentee_active':         None,
        'estate_heirs':            'estate_heirs_structural',   # soft pressure on estate-named owners
        # Legacy values that already match
        'investor_disposition':    'investor_disposition',
        'divorce_unwinding':       'divorce_unwinding',
    }
    existing_family = _ARCHETYPE_TO_PRESSURE_FAMILY.get(raw_archetype, raw_archetype)

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
    # Structural trust aging and estate naming: no confirmed life event
    # yet, but the archetype itself is a soft indicator that the biological
    # decision window is open.
    if existing_family == 'trust_aging_structural':
        pressure = max(pressure, 1); triggers.append('trust aging — biological decision window')
    if existing_family == 'estate_heirs_structural':
        pressure = max(pressure, 1); triggers.append('estate / heirs on title')
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


def _use_supabase_backend() -> bool:
    """True if Supabase is configured and we should use DB cache instead of flat-file."""
    import os
    return bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_KEY'))


def cache_get(parcel: dict, mode: str):
    """Returns cached result if younger than TTL, else None.

    Uses Supabase when SUPABASE_URL/SERVICE_KEY are set, flat-file otherwise.
    """
    if _use_supabase_backend():
        try:
            from backend.investigation import persistence
            return persistence.cache_get(parcel, mode)
        except Exception as e:
            print(f'[cache_get] persistence fallback to flat-file: {e}')
    # Flat-file fallback
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
    """Persist investigation result.

    Uses Supabase when SUPABASE_URL/SERVICE_KEY are set, flat-file otherwise.
    """
    if _use_supabase_backend():
        try:
            from backend.investigation import persistence
            persistence.cache_put(parcel, mode, result)
            return
        except Exception as e:
            print(f'[cache_put] persistence fallback to flat-file: {e}')
    # Flat-file fallback
    path = _cache_path(_cache_key(parcel, mode))
    with open(path, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'result': result},
                  f, default=str)


def cache_invalidate(parcel: dict):
    """Invalidate all modes for this parcel (on new free-event hit)."""
    if _use_supabase_backend():
        try:
            from backend.investigation import persistence
            pin = parcel.get('pin') or parcel.get('id') or parcel.get('parcel_id')
            if pin:
                persistence.cache_invalidate(pin)
            return
        except Exception as e:
            print(f'[cache_invalidate] persistence fallback to flat-file: {e}')
    # Flat-file fallback
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
    signals = extract_all_signals(all_results, parcel=parcel)

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
