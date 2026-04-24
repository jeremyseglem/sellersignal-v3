"""
King County eReal Property HTML parser.

Parses the public eReal Property detail page at:
    https://blue.kingcounty.com/Assessor/eRealProperty/Detail.aspx
        ?ParcelNbr=<10-digit-pin>

Returns a structured dict with:
    - parcel:         owner_name, site address, jurisdiction, property
                      type, legal
    - building:       year_built, year_renovated, sqft (total finished),
                      bedrooms, full_baths, three_quarter_baths,
                      half_baths, grade, condition
    - sales:          list of recorded transfers (excise, recording,
                      date, price, seller, buyer, instrument, reason)

Tested against Richards parcel 1802000050 (2026-04-24). The HTML is
ASP.NET-generated with GridView tables; labels live in <td> with
font-weight:bold and values in the following <td>. We extract these
as label->value pairs via regex rather than a full DOM parse, both
because we don't need to touch most of the page and because the HTML
has mild inconsistencies (some fields wrapped in <span id="...">
auto-generated control IDs).

This module is a pure function of the HTML body. No I/O.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from typing import Optional

PARSER_VERSION = "1.0.0"

# ─── Label extraction ─────────────────────────────────────────────────

# Matches label cells (bold <td>) followed by value cells. Captures the
# label and the value text.
_LABEL_VALUE_RE = re.compile(
    r'<td[^>]*style="[^"]*font-weight:\s*bold[^"]*"[^>]*>\s*([^<]+?)\s*</td>\s*'
    r'<td[^>]*>(.*?)</td>',
    re.S | re.I,
)


def _strip(raw: str) -> str:
    """Strip HTML, decode entities, collapse whitespace."""
    if not raw:
        return ""
    t = re.sub(r'<[^>]+>', ' ', raw)
    t = unescape(t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _extract_label_values(html: str) -> dict[str, str]:
    """
    Scan label-value pairs across the entire page body. Labels collide
    on common names (e.g. "Jurisdiction" appears in parcel AND permit
    sections) — this returns the FIRST occurrence of each label, which
    matches the parcel section's position at the top of the page.

    For labels that legitimately repeat (unlikely) the caller should
    instead scan section-by-section.
    """
    pairs: dict[str, str] = {}
    for m in _LABEL_VALUE_RE.finditer(html):
        label = _strip(m.group(1)).rstrip(':').strip()
        value = _strip(m.group(2))
        if label and label not in pairs:
            pairs[label] = value
    return pairs


# ─── Sales history parsing ────────────────────────────────────────────

# The sales history GridView has 8 columns in a known order. Rather
# than relying on the GridView's class names (which vary between rows
# and alternating rows), we find the SALES HISTORY anchor and pull
# tr rows that have 8 cells, matching the column count.
_SALES_TR_RE = re.compile(
    r'<tr[^>]*class="GridView(?:Alternating)?RowStyle"[^>]*>(.*?)</tr>',
    re.S | re.I,
)
_CELL_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.S | re.I)


def _parse_date(s: str) -> Optional[date]:
    """Parse 'M/D/YYYY' (the assessor's format) -> date."""
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_price(s: str) -> Optional[int]:
    """Parse '$900,000.00' -> 900000. None for empty / unparseable / 0."""
    if not s:
        return None
    cleaned = re.sub(r'[^\d.]', '', s)
    if not cleaned:
        return None
    try:
        v = int(float(cleaned))
        # Treat 0-dollar transfers as None for the price field but keep
        # the record (quit-claims, gifts, etc. often have no stated price).
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_int(s: str) -> Optional[int]:
    if not s:
        return None
    cleaned = re.sub(r'[^\d]', '', s)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _classify_arms_length(instrument: str, reason: str) -> Optional[bool]:
    """
    Heuristic: was this a genuine open-market sale?

    Returns:
      - True  for Statutory Warranty Deed with reason='None' (default open-market)
      - False for quit claims, gifts, estate distributions, divorces, trustee deeds
      - None  for genuinely ambiguous cases (empty instrument, unknown reason)

    Non-arms-length sales have distorted prices — the $900K on the
    Richards parcel was arms-length; a $0 quit-claim from a family
    trust to an heir is not. For signal-family logic this matters.
    """
    i = (instrument or '').strip().upper()
    r = (reason or '').strip().upper()

    if not i:
        return None

    if 'QUIT' in i and 'CLAIM' in i:
        return False
    if 'TRUSTEE' in i or 'TRUSTEES' in i:
        return False
    if 'GIFT' in r or 'ESTATE' in r or 'DIVORCE' in r or 'TRUST' in r:
        return False
    if 'STATUTORY WARRANTY' in i:
        # Default arms-length unless reason says otherwise
        return r in ('', 'NONE', 'NONE SPECIFIED', 'N/A')

    # Unknown instrument — don't guess
    return None


def parse_sales_history(html: str) -> list[dict]:
    """
    Extract sales from the SALES HISTORY section. Returns a list of
    dicts, ordered as they appear on the page (most recent first).

    Each dict has:
      excise_number, recording_number, sale_date, sale_price,
      seller_name, buyer_name, instrument, sale_reason, is_arms_length
    """
    # Find the SALES HISTORY anchor. The label varies in exact casing
    # so we match loosely.
    m = re.search(r'SALES\s+HISTORY', html, re.I)
    if not m:
        return []

    # Walk forward, collecting tr rows until we hit the next section
    # anchor (REVIEW HISTORY, PERMIT HISTORY, or end of form).
    tail = html[m.end():]
    end_m = re.search(
        r'(REVIEW\s+HISTORY|PERMIT\s+HISTORY|REVIEW_HIST|PERMIT_HIST)',
        tail, re.I,
    )
    block = tail[:end_m.start()] if end_m else tail[:50000]

    out: list[dict] = []
    for row_match in _SALES_TR_RE.finditer(block):
        cells = [_strip(c) for c in _CELL_RE.findall(row_match.group(1))]
        # Expected 8 cells: excise, recording, date, price, seller,
        # buyer, instrument, reason. GridView may have other rows with
        # different counts (header, pager) — those have been filtered by
        # the row-style regex already, but cell count is a safety check.
        if len(cells) != 8:
            continue
        excise, recording, date_s, price_s, seller, buyer, instrument, reason = cells
        out.append({
            'excise_number':    excise or None,
            'recording_number': recording or None,
            'sale_date':        _parse_date(date_s),
            'sale_price':       _parse_price(price_s),
            'seller_name':      seller or None,
            'buyer_name':       buyer or None,
            'instrument':       instrument or None,
            'sale_reason':      reason or None,
            'is_arms_length':   _classify_arms_length(instrument, reason),
        })
    return out


# ─── Top-level parser ────────────────────────────────────────────────

def parse_ereal_detail(html: str, pin: str) -> dict:
    """
    Parse the full eReal Property detail page. Returns:
      {
        'pin':        str,
        'parcel':     { owner_name, site_address, jurisdiction,
                        property_type, ... },
        'building':   { year_built, year_renovated, sqft, bedrooms,
                        full_baths, three_quarter_baths, half_baths,
                        grade, condition },
        'sales':      [ ... ],
        'parser_version': str,
      }

    Any section missing returns as an empty dict / list, not an error.
    The page occasionally renders with sections blanked out for unusual
    parcels (condos without building details, for instance); callers
    should check for populated fields before assuming completeness.
    """
    labels = _extract_label_values(html)

    parcel = {
        'owner_name':     labels.get('Name'),
        'site_address':   labels.get('Site Address'),
        'jurisdiction':   labels.get('Jurisdiction'),
        'property_type':  labels.get('Property Type'),
        'residential_area': labels.get('Residential Area'),
        'levy_code':      labels.get('Levy Code'),
        'quarter_section': labels.get('Quarter-Section-Township-Range'),
    }

    # Sqft is "Total Finished Area"; bedrooms/baths are direct
    building = {
        'year_built':      _parse_int(labels.get('Year Built', '')),
        'year_renovated':  _parse_int(labels.get('Year Renovated', '')),
        'sqft':            _parse_int(labels.get('Total Finished Area', '')),
        'bedrooms':        _parse_int(labels.get('Bedrooms', '')),
        'full_baths':      _parse_int(labels.get('Full Baths', '')),
        'three_quarter_baths': _parse_int(labels.get('3/4 Baths', '')),
        'half_baths':      _parse_int(labels.get('1/2 Baths', '')),
        'grade':           labels.get('Grade'),
        'condition':       labels.get('Condition'),
        'stories':         _parse_int(labels.get('Stories', '')),
        'living_units':    _parse_int(labels.get('Living Units', '')),
    }

    sales = parse_sales_history(html)

    return {
        'pin':     pin,
        'parcel':  parcel,
        'building': building,
        'sales':   sales,
        'parser_version': PARSER_VERSION,
    }
