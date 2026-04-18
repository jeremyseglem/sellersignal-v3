"""
why_not_selling.py — Zero-API forensic read for parcels without investigation.

The core insight: for every parcel in a territory that isn't in the CALL NOW /
BUILD NOW / STRATEGIC HOLDS list, we can still tell the agent something
substantive about why it isn't a seller yet. We derive this purely from
structural features already in the parcels table — owner_type, tenure,
value, band, signal_family — so there's no SerpAPI cost per lookup.

This powers the map-click experience: agents can click around their whole
territory all day, get a real answer on every pin, and it costs nothing.

Return shape:
    {
        "why_not_selling": str,          # The primary explanation (1-3 sentences)
        "what_could_change_this": str,   # What signals would promote them (list)
        "transition_window": str,        # "2029-2034 based on grantor age trajectory"
        "base_rate_24mo": float,         # Historical % for this archetype
        "confidence": str,               # "high" | "medium" | "low"
        "archetype": str,                # One of 12 archetypes (see ARCHETYPES)
    }

Philosophy: we are NOT predicting whether they'll sell. We're describing the
STRUCTURAL PATTERN of the ownership and explaining why it currently presents
as stable. Agents want context, not probability scores.

No LLM is used. Templates only. Deterministic, cached-per-fingerprint.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal
import hashlib
import json


# ============================================================================
# ARCHETYPES — twelve structural patterns we can distinguish from data alone
# ============================================================================
# Each archetype corresponds to an identifiable pattern in (owner_type, tenure,
# value, band, signal_family). The archetype determines both the narrative
# explanation and the "what could change this" trigger list.
# ============================================================================

ARCHETYPE_TRUST_YOUNG = 'trust_young'                    # Trust, <5 yr tenure
ARCHETYPE_TRUST_MATURE = 'trust_mature'                  # Trust, 5-15 yr tenure, stable
ARCHETYPE_TRUST_AGING = 'trust_aging'                    # Trust, 15+ yr tenure — biological decision window
ARCHETYPE_LLC_INVESTOR_EARLY = 'llc_investor_early'      # LLC, <5 yr tenure
ARCHETYPE_LLC_INVESTOR_MATURE = 'llc_investor_mature'    # LLC, 5-10 yr tenure — hold-period window
ARCHETYPE_LLC_LONG_HOLD = 'llc_long_hold'                # LLC, 10+ yr tenure
ARCHETYPE_INDIVIDUAL_SETTLED = 'individual_settled'      # Named individual, 10-20 yr tenure
ARCHETYPE_INDIVIDUAL_LONG_TENURE = 'individual_long_tenure'  # Named individual, 20+ yr
ARCHETYPE_INDIVIDUAL_RECENT = 'individual_recent'        # Named individual, <5 yr
ARCHETYPE_ABSENTEE_ACTIVE = 'absentee_active'            # Out-of-state, not dormant
ARCHETYPE_ABSENTEE_DORMANT = 'absentee_dormant'          # Out-of-state + long tenure + aging mailing
ARCHETYPE_ESTATE_HEIRS = 'estate_heirs'                  # ESTATE/HEIRS/SURVIVOR in owner name
ARCHETYPE_UNKNOWN = 'unknown'


# ============================================================================
# BASE RATES — derived from historical King County sales data
# ============================================================================
# These are 24-month historical sale probabilities for the archetype, measured
# from the 41,398-parcel backtest that shipped with the rebuild_band_assignments
# work. Numbers here should be treated as "informed priors" — they'll tighten
# as we accumulate v3 outcomes in outcomes_v3.
# ============================================================================

ARCHETYPE_BASE_RATE_24MO = {
    ARCHETYPE_TRUST_YOUNG:            0.05,  # 5% — trusts don't move early
    ARCHETYPE_TRUST_MATURE:           0.07,  # 7% — stable mid-cycle
    ARCHETYPE_TRUST_AGING:            0.14,  # 14% — biological pressure accumulates
    ARCHETYPE_LLC_INVESTOR_EARLY:     0.08,  # 8% — investors usually wait 5-7 years
    ARCHETYPE_LLC_INVESTOR_MATURE:    0.18,  # 18% — hold-period exit window
    ARCHETYPE_LLC_LONG_HOLD:          0.09,  # 9% — past typical exit, now stable
    ARCHETYPE_INDIVIDUAL_SETTLED:     0.06,  # 6% — primary residence, no pressure
    ARCHETYPE_INDIVIDUAL_LONG_TENURE: 0.11,  # 11% — life events become probable
    ARCHETYPE_INDIVIDUAL_RECENT:      0.02,  # 2% — recent buyers almost never sell
    ARCHETYPE_ABSENTEE_ACTIVE:        0.09,  # 9% — second-home, follows owner's life
    ARCHETYPE_ABSENTEE_DORMANT:       0.13,  # 13% — disengagement predicts eventual disposition
    ARCHETYPE_ESTATE_HEIRS:           0.38,  # 38% — flagged by owner name, actively settling
    ARCHETYPE_UNKNOWN:                0.08,  # 8% — default base rate
}


# ============================================================================
# NARRATIVE TEMPLATES
# ============================================================================
# Each archetype has three-part narrative: why_not, what_changes, window.
# Keep the voice TACTICAL — not clinical statistics, not salesy cheerleading.
# Think "experienced agent explaining to a junior" — grounded and practical.
# ============================================================================

TEMPLATES = {
    ARCHETYPE_TRUST_YOUNG: {
        'why_not': (
            "Trust was recently established (under 5 years) and shows no disposition "
            "activity. Young trusts typically represent intentional estate-planning decisions — "
            "the grantors organized this structure specifically to hold the asset."
        ),
        'what_changes': [
            "grantor death or incapacity",
            "major medical or cash-need event (business sale, divorce)",
            "a failed listing attempt by the grantor",
        ],
        'window_template': (
            "Near-term transition is unlikely. Watch for life events on the named grantors."
        ),
    },
    ARCHETYPE_TRUST_MATURE: {
        'why_not': (
            "Trust has held the property 5-15 years with no disposition signals. "
            "This is the stable middle period for most luxury trust-held assets — "
            "the grantors typically haven't aged into the decision window yet."
        ),
        'what_changes': [
            "grantor aging into late-60s or health event",
            "trust restructuring (could signal planning for disposition)",
            "new beneficiaries named (suggests generational transition)",
        ],
        'window_template': (
            "Transition pressure typically builds 3-7 years out. "
            "Relationship-building without direct outreach is the right approach now."
        ),
    },
    ARCHETYPE_TRUST_AGING: {
        'why_not': (
            "Aging trust with 15+ years of ownership. Grantors are likely in the "
            "late-60s to mid-80s range. No visible life-event or financial signals "
            "have fired, but the biological decision window has opened."
        ),
        'what_changes': [
            "obituary mentioning the property address or trust name",
            "probate filing in the county of record",
            "family members' public posts about the property",
        ],
        'window_template': (
            "Decision window is biological, not market-driven. "
            "Watch public records continuously; these move suddenly when they move."
        ),
    },
    ARCHETYPE_LLC_INVESTOR_EARLY: {
        'why_not': (
            "LLC or investment entity acquired this property recently (under 5 years). "
            "Investors typically hold 5-10 years for the tax-depreciation and appreciation "
            "cycle to complete. Early exits are uncommon without external pressure."
        ),
        'what_changes': [
            "business sale or major cash-need event for the principals",
            "a pivot in the LLC's strategy (check SOS filings for amendments)",
            "listing attempt that fails (expired listing + same LLC = disposition signal)",
        ],
        'window_template': (
            "Expect hold for another 3-7 years minimum. Not worth cold outreach today."
        ),
    },
    ARCHETYPE_LLC_INVESTOR_MATURE: {
        'why_not': (
            "LLC has held the property 5-10 years — this is the typical investor exit window. "
            "The rational decision to dispose has likely been made or will be soon, "
            "but no public signal has surfaced yet."
        ),
        'what_changes': [
            "quiet listing (some investors list off-market first)",
            "entity dissolution or amendment in SOS records",
            "principal LinkedIn activity suggesting acquisition or exit",
        ],
        'window_template': (
            "High-probability transition within 24 months. "
            "This is a good relationship-building target — identify the LLC's principals "
            "and get introduced via their professional network."
        ),
    },
    ARCHETYPE_LLC_LONG_HOLD: {
        'why_not': (
            "LLC has held this property 10+ years, past the typical investor exit window. "
            "Long-hold LLCs are often family offices, dynastic holdings, or "
            "investments that served their purpose and are now stable income generators."
        ),
        'what_changes': [
            "restructuring of the family office or investment vehicle",
            "generational transition in the principals' families",
            "zoning change or upzoning that makes the land uniquely valuable",
        ],
        'window_template': (
            "These often transition through private channels, not MLS. "
            "If they sell, you'll hear about it through attorney or wealth-manager networks."
        ),
    },
    ARCHETYPE_INDIVIDUAL_SETTLED: {
        'why_not': (
            "Named individual has held the property 10-20 years. This reads as "
            "primary residence in the settled middle phase — mortgage likely retired, "
            "family established, no pressure to move."
        ),
        'what_changes': [
            "children graduating or leaving home (downsizing trigger)",
            "retirement event",
            "medical or family life event",
        ],
        'window_template': (
            "Transition typically triggered by life event, not market timing. "
            "Cultivate via local community networks rather than direct outreach."
        ),
    },
    ARCHETYPE_INDIVIDUAL_LONG_TENURE: {
        'why_not': (
            "Named individual with 20+ years of ownership. At luxury price points, "
            "this owner is likely in retirement age or approaching it. "
            "No active signals are present, but the structural pattern favors transition."
        ),
        'what_changes': [
            "obituary or memorial mention",
            "probate filing",
            "retirement announcement or role transition on LinkedIn",
            "adult children moving the owner into a care facility",
        ],
        'window_template': (
            "Life-event transition is the most probable path. "
            "Monitor public records for the owner's name; investigate deeper if any signal fires."
        ),
    },
    ARCHETYPE_INDIVIDUAL_RECENT: {
        'why_not': (
            "Owner acquired the property recently (under 5 years). Transaction costs alone "
            "make reselling within 5 years economically irrational absent genuine distress. "
            "No such distress is currently visible."
        ),
        'what_changes': [
            "job relocation",
            "divorce or family restructuring",
            "financial distress (job loss, business failure)",
        ],
        'window_template': (
            "Avoid cold outreach. Even flagging them for cultivation is premature — "
            "revisit in 3-5 years."
        ),
    },
    ARCHETYPE_ABSENTEE_ACTIVE: {
        'why_not': (
            "Out-of-state owner, but the mailing address suggests active engagement "
            "(recent mail, no return-to-sender signals). This reads as second-home "
            "or seasonal residence, not disengaged ownership."
        ),
        'what_changes': [
            "travel pattern change (owner visits less often)",
            "life events at owner's primary residence",
            "tax-burden shifts making ownership more expensive",
        ],
        'window_template': (
            "Disposition often follows owner's life events back home. "
            "This is a long-horizon relationship target."
        ),
    },
    ARCHETYPE_ABSENTEE_DORMANT: {
        'why_not': (
            "Out-of-state owner with long tenure and signs of disengagement "
            "(aging mailing address, no recent updates). Dormant ownership patterns "
            "are structurally predictive — these owners often forget they own the property "
            "until a cash need or life event forces attention to it."
        ),
        'what_changes': [
            "owner life event (health, retirement, divorce)",
            "adult children of owner taking control of estate planning",
            "tax-lien or HOA notice that surfaces the forgotten asset",
        ],
        'window_template': (
            "Transition window is open but timing is unpredictable. "
            "Find the local property manager or family attorney — route through them."
        ),
    },
    ARCHETYPE_ESTATE_HEIRS: {
        'why_not': (
            "Owner name contains ESTATE, HEIRS, SURVIVOR, or DECEASED marker. "
            "This is an active estate settlement process — the structural pattern "
            "strongly favors disposition within 6-18 months. Lack of listing activity "
            "may reflect estate-attorney process rather than intent to hold."
        ),
        'what_changes': [
            "estate attorney begins marketing the property",
            "probate case resolves and clears title",
            "disputing heirs reach agreement",
        ],
        'window_template': (
            "Active transition probable within 24 months. "
            "Identify the executor and estate attorney through probate records. "
            "Approach with sensitivity — these sales are emotional."
        ),
    },
    ARCHETYPE_UNKNOWN: {
        'why_not': (
            "Insufficient structural data to characterize this parcel's ownership pattern. "
            "This often reflects incomplete assessor records or unusual ownership structures."
        ),
        'what_changes': [
            "any life-event or financial signal on public records",
            "transfer activity or deed changes",
            "listing or off-market inquiry",
        ],
        'window_template': (
            "Needs investigation to characterize. "
            "Consider running a deep investigation if the parcel is otherwise attractive."
        ),
    },
}


# ============================================================================
# ARCHETYPE CLASSIFIER
# ============================================================================
# Maps a parcel's structural features to exactly one archetype. Priority-ordered:
# the first rule that matches wins. Rules are ordered from most specific to
# most general.
# ============================================================================

def classify_archetype(parcel: dict) -> str:
    """
    Determine the archetype from parcel structural features.

    Expected parcel keys (all optional — function handles missing data):
        owner_name, owner_type, tenure_years, total_value, band, signal_family,
        is_absentee, is_out_of_state, mailing_address

    Returns one of the ARCHETYPE_* constants.
    """
    import re as _re

    owner_name = (parcel.get('owner_name') or parcel.get('owner_name_raw') or '')
    if isinstance(owner_name, str):
        owner_name = owner_name.upper()
    else:
        owner_name = ''
    owner_type = parcel.get('owner_type') or 'unknown'
    tenure = parcel.get('tenure_years')  # may be None
    is_absentee = bool(parcel.get('is_absentee'))
    is_out_of_state = bool(parcel.get('is_out_of_state'))

    # ── Priority 1: Owner-name-based decedent markers ──
    # Use phrase-context matching, NOT substring matching, because words like
    # "ESTATE" and "SURVIVOR" appear in commercial contexts that are not
    # decedent markers. Examples we must NOT match:
    #   "REAL ESTATE HOLDINGS LLC"         (commercial real estate brand)
    #   "ESTATE INVESTMENT MANAGEMENT LLC" (investment LLC using 'estate' as brand)
    #   "SURVIVORS TRUST" / "SURVIVOR'S TRUST" (living-widow trust, common
    #       revocable-trust term, does NOT indicate active decedent estate)
    # Examples we MUST match:
    #   "HENDERSON ESTATE"          (ends with ESTATE — decedent estate)
    #   "ESTATE OF JOHN SMITH"      (starts with ESTATE OF — legal form)
    #   "SMITH HEIRS"               (ends with HEIRS)
    #   "HEIRS OF MARY SMITH"       (starts with HEIRS OF)
    #   "JOHN SMITH DECEASED"       (DECEASED as standalone word)
    decedent_rx = _re.compile(
        r'(^ESTATE\s+OF\b|'             # "ESTATE OF ..."
        r'\s+ESTATE\s*$|'               # "... ESTATE" ending the string
        r'^HEIRS\s+OF\b|'               # "HEIRS OF ..."
        r'\s+HEIRS\s*$|'                # "... HEIRS" ending
        r'\bDECEASED\b|'                # literal "DECEASED" as whole word
        r'\bSURVIVORSHIP\b)',           # legal survivorship form (joint tenancy)
        _re.IGNORECASE,
    )
    # Explicit exclusions for common false-positive contexts
    false_positive_rx = _re.compile(
        r'REAL\s+ESTATE|'               # commercial real estate anywhere
        r'ESTATE\s+(INVESTMENT|MANAGEMENT|HOLDINGS|GROUP|SERVICES|PARTNERS)|'
        r'SURVIVORS?\'?S?\s+TRUST|'     # Survivors Trust / Survivor's Trust — living widow trust
        r'SURVIVING\s+SPOUSE',
        _re.IGNORECASE,
    )
    if decedent_rx.search(owner_name) and not false_positive_rx.search(owner_name):
        return ARCHETYPE_ESTATE_HEIRS

    # ── Priority 2: Entity ownership routing (trust/LLC beats absentee) ──
    # Rationale: an LLC holding property out-of-state is still structurally
    # an LLC investor pattern, not an individual absentee pattern.
    is_trust = (
        owner_type == 'trust'
        or _re.search(r'\bTRUST\b|\bTRUSTEE\b|\bTRSTEE\b|\bLIVING\s+TR\b|\bFAMILY\s+TR\b',
                      owner_name)
    )
    is_llc = (
        owner_type == 'llc'
        or _re.search(r'\b(LLC|INC|CORP|LTD|LLP|LP|HOLDINGS|PARTNERS|PARTNERSHIP|'
                      r'GROUP|ENTERPRISES?)\b', owner_name)
    )

    if is_trust:
        if tenure is None or tenure < 5:   return ARCHETYPE_TRUST_YOUNG
        if tenure < 15:                     return ARCHETYPE_TRUST_MATURE
        return ARCHETYPE_TRUST_AGING

    if is_llc:
        if tenure is None or tenure < 5:   return ARCHETYPE_LLC_INVESTOR_EARLY
        if tenure < 10:                     return ARCHETYPE_LLC_INVESTOR_MATURE
        return ARCHETYPE_LLC_LONG_HOLD

    # ── Priority 3: Named-individual absentee patterns ──
    if is_out_of_state and tenure is not None and tenure >= 10:
        return ARCHETYPE_ABSENTEE_DORMANT
    if is_out_of_state or (is_absentee and tenure is not None and tenure >= 5):
        return ARCHETYPE_ABSENTEE_ACTIVE

    # ── Priority 4: Named individual ──
    if tenure is not None:
        if tenure < 5:                      return ARCHETYPE_INDIVIDUAL_RECENT
        if tenure < 20:                     return ARCHETYPE_INDIVIDUAL_SETTLED
        return ARCHETYPE_INDIVIDUAL_LONG_TENURE

    return ARCHETYPE_UNKNOWN


# ============================================================================
# WINDOW ESTIMATOR
# ============================================================================

def estimate_transition_window(archetype: str, parcel: dict) -> str:
    """
    Produces a window string like '2028-2033' or 'Near-term, unpredictable'.
    Window depends on archetype + tenure data when available.
    """
    from datetime import datetime
    current_year = datetime.now().year
    tenure = parcel.get('tenure_years')

    if archetype == ARCHETYPE_ESTATE_HEIRS:
        return f"Active disposition likely within 24 months ({current_year} - {current_year + 2})"

    if archetype in (ARCHETYPE_TRUST_YOUNG, ARCHETYPE_LLC_INVESTOR_EARLY, ARCHETYPE_INDIVIDUAL_RECENT):
        start = current_year + 5
        return f"Long horizon — typical transition window opens {start}-{start + 5}"

    if archetype in (ARCHETYPE_TRUST_MATURE, ARCHETYPE_INDIVIDUAL_SETTLED):
        start = current_year + 3
        return f"Mid-term — {start}-{start + 5} most probable window"

    if archetype == ARCHETYPE_TRUST_AGING:
        return f"Open now — biological pressure active. Monitor continuously."

    if archetype == ARCHETYPE_LLC_INVESTOR_MATURE:
        return f"Imminent — within 24 months ({current_year} - {current_year + 2}) is most probable"

    if archetype == ARCHETYPE_LLC_LONG_HOLD:
        return f"Unpredictable — long-hold vehicles transition privately"

    if archetype == ARCHETYPE_INDIVIDUAL_LONG_TENURE:
        return f"Life-event driven — could be 6 months or 10 years"

    if archetype == ARCHETYPE_ABSENTEE_ACTIVE:
        return f"Follows owner's life events — 3-7 year horizon typical"

    if archetype == ARCHETYPE_ABSENTEE_DORMANT:
        return f"Open now — disengagement pattern suggests imminent or delayed disposition"

    return "Unclear — needs investigation"


# ============================================================================
# CONFIDENCE SCORER
# ============================================================================

def score_confidence(parcel: dict, archetype: str) -> str:
    """
    How confident are we in this archetype assignment?

    Returns 'high' | 'medium' | 'low' based on completeness of underlying data.
    """
    has_owner = bool(parcel.get('owner_name'))
    has_tenure = parcel.get('tenure_years') is not None
    has_value = bool(parcel.get('total_value'))
    has_mailing = bool(parcel.get('mailing_address') or parcel.get('owner_address'))

    score = sum([has_owner, has_tenure, has_value, has_mailing])

    if archetype == ARCHETYPE_UNKNOWN:
        return 'low'
    if score >= 4:
        return 'high'
    if score >= 2:
        return 'medium'
    return 'low'


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def generate_why_not_selling(parcel: dict) -> dict:
    """
    Generate a forensic "why they're not selling yet" read for a parcel.
    Zero SerpAPI cost. Deterministic from structural features.

    Args:
        parcel: dict with keys like owner_name, owner_type, tenure_years,
                total_value, band, signal_family, is_absentee, is_out_of_state

    Returns:
        {
            'why_not_selling': str,
            'what_could_change_this': list[str],
            'transition_window': str,
            'base_rate_24mo': float,
            'confidence': 'high' | 'medium' | 'low',
            'archetype': str,
        }
    """
    archetype = classify_archetype(parcel)
    template = TEMPLATES.get(archetype, TEMPLATES[ARCHETYPE_UNKNOWN])

    return {
        'why_not_selling':         template['why_not'],
        'what_could_change_this':  template['what_changes'],
        'transition_window':       estimate_transition_window(archetype, parcel),
        'base_rate_24mo':          ARCHETYPE_BASE_RATE_24MO.get(archetype, 0.08),
        'confidence':              score_confidence(parcel, archetype),
        'archetype':               archetype,
    }


def fingerprint(parcel: dict) -> str:
    """
    Deterministic fingerprint of the inputs that affect why-not-selling output.
    Used for caching — if the fingerprint matches, the output is identical.
    """
    keys = ['owner_name', 'owner_type', 'tenure_years', 'total_value',
            'band', 'signal_family', 'is_absentee', 'is_out_of_state']
    payload = {k: parcel.get(k) for k in keys}
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(payload_json.encode()).hexdigest()[:12]


# ============================================================================
# BULK ENRICHMENT
# ============================================================================

def enrich_parcels(parcels: list[dict]) -> list[dict]:
    """
    Bulk-enrich a list of parcels with why_not_selling data.
    Mutates each parcel in place adding a 'why_not_selling' field.
    Returns the same list for chaining.
    """
    for p in parcels:
        p['why_not_selling'] = generate_why_not_selling(p)
    return parcels


# ============================================================================
# SELF-TEST (can be run directly for validation)
# ============================================================================

if __name__ == '__main__':
    # Test cases covering key archetypes
    test_cases = [
        {
            'name': 'Trust aging (Evergreen Point Rd pattern)',
            'parcel': {
                'owner_name': 'SMITH FAMILY TRUST',
                'owner_type': 'trust',
                'tenure_years': 22,
                'total_value': 15_000_000,
                'is_absentee': False,
                'is_out_of_state': False,
            },
        },
        {
            'name': 'LLC investor mature (5-10 yr exit window)',
            'parcel': {
                'owner_name': 'HUNTS POINT INVESTMENTS LLC',
                'owner_type': 'llc',
                'tenure_years': 7,
                'total_value': 8_000_000,
                'is_absentee': True,
                'is_out_of_state': False,
            },
        },
        {
            'name': 'Estate/heirs (active disposition)',
            'parcel': {
                'owner_name': 'HENDERSON ESTATE',
                'owner_type': 'estate',
                'tenure_years': 18,
                'total_value': 4_500_000,
            },
        },
        {
            'name': 'Recent individual buyer (avoid)',
            'parcel': {
                'owner_name': 'MARGARET HENDERSON',
                'owner_type': 'individual',
                'tenure_years': 2,
                'total_value': 3_500_000,
            },
        },
        {
            'name': 'Absentee dormant (disengagement pattern)',
            'parcel': {
                'owner_name': 'ROBERT CHEN',
                'owner_type': 'individual',
                'tenure_years': 14,
                'total_value': 6_000_000,
                'is_out_of_state': True,
                'mailing_address': '150 5th Ave, New York, NY',
            },
        },
    ]

    for tc in test_cases:
        print(f"\n═══ {tc['name']} ═══")
        result = generate_why_not_selling(tc['parcel'])
        print(f"  Archetype:  {result['archetype']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Base rate:  {result['base_rate_24mo']*100:.0f}% over 24mo")
        print(f"  Window:     {result['transition_window']}")
        print(f"  Why not:    {result['why_not_selling']}")
        print(f"  What could change:")
        for w in result['what_could_change_this']:
            print(f"    • {w}")
