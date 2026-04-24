"""
Parcel-state tag derivation.

Reads facts from parcels_v3 columns and derives boolean "situational tags"
that the lead card can surface to an agent. No promotion logic — pure
descriptive tags. A parcel can have any number of these fire.

Current tags:
  - HIGH EQUITY  : owner has a multi-bagger on implied equity (current
                   value / last sale price >= 4) AND has held long enough
                   (>= 10 years) for that to be real appreciation rather
                   than market noise.
  - DEEP TENURE  : tenure_years >= 30 (bought before 1996).
  - LEGACY HOLD  : tenure_years >= 40 (bought before 1986). Higher-signal
                   tier above DEEP TENURE because the age distribution at
                   40+ yr narrows to owners with a high probability of
                   near-term life change. We don't have age data directly
                   (no senior-exemption feed), so this is the best proxy.
  - MATURE LLC   : owner_type == 'llc' AND tenure_years >= 5. Typical
                   investor exit-window trigger. NOTE: currently returns
                   zero on 98004 because the ingest layer misclassifies
                   some LLCs as 'individual' (e.g. "Bellevue I Llp
                   Wallace/scott" shows owner_type='individual'). The tag
                   logic is correct; the owner_type data has a separate
                   bug to fix in Option 2 (ingest cleanup).

DELIBERATELY NOT IMPLEMENTED TODAY:
  - ABSENTEE OOS : requires owner_address / owner_state columns, which
                   are NULL for all parcels in parcels_v3 today. Ingest
                   cleanup is required before this tag can fire. See
                   signal_registry.py's absentee_oos_disposition family
                   for the documented data availability gap.
  - HIGH LAND / UNDERVALUED BUILDING / GROSS TEARDOWN : require
                   land_value and building_value, also NULL for all
                   sampled parcels. Same Option 2 cleanup required.

Tags are a pure function of parcel columns — no DB lookups, no I/O.
Callers should batch-load parcels once and call derive_tags(parcel) per
row. The function signature matches what's already available on a
parcels_v3 row dict.
"""
from __future__ import annotations

# Thresholds — chosen from empirical distribution in 98004 on 2026-04-23.
# See the session journal entry for how these were calibrated.
# Any change here should be accompanied by a prod re-check of the
# resulting tag distribution (target: each tag fires on <= 15-20% of
# parcels to stay differentiating).

HIGH_EQUITY_MULT_THRESHOLD    = 6.0   # total_value / last_transfer_price.
                                      # Calibrated on 98004 on 2026-04-23:
                                      # 4.0 fired on 46% of leads (too noisy).
                                      # 6.0 narrows to ~20-25% — genuinely
                                      # differentiating tier. In a long-held
                                      # Bellevue market, 4x multipliers are
                                      # ambient; 6x requires both decade-plus
                                      # tenure AND above-market appreciation.
HIGH_EQUITY_MIN_TENURE_YEARS  = 10.0  # must have held long enough for
                                      # appreciation to be real, not just
                                      # a renovation or bubble year
DEEP_TENURE_YEARS             = 30.0
LEGACY_HOLD_YEARS             = 40.0
MATURE_LLC_MIN_TENURE_YEARS   = 5.0


def _fmt_dollars(v: float) -> str:
    """
    Format dollar amounts with the threshold switch at $1M so the
    human-readable description doesn't show 'Implied 11.7x appreciation
    since last sale ($1870K → $21.8M)' where the unit inconsistency makes
    the ratio harder to read. With this, the example becomes
    '($1.9M → $21.8M)'.
    """
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _safe_float(v) -> float:
    """None, '', or non-numeric → 0.0. Never raises."""
    if v is None or v == '':
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def derive_tags(parcel: dict) -> list[dict]:
    """
    Given a parcel dict (as returned from parcels_v3 queries, optionally
    enriched with arms-length fields from the parcel_last_arms_length_v3
    view), return a list of tag dicts. Each tag has:
        label       : short uppercase string for the lead card badge
        kind        : machine-readable identifier
        description : one-line "why this matters" for tooltip/dossier
        rank        : integer sort key (higher = stronger signal,
                      so frontend can order badges consistently)

    Returns an empty list if nothing fires. Never returns None.

    Optional enrichment (from parcel_last_arms_length_v3 view):
        last_arms_length_price : most recent arms-length sale price
        last_arms_length_date  : ISO date of that sale (str or date)
    When these are present, they override parcels_v3.last_transfer_price
    and parcels_v3.last_transfer_date for the HIGH EQUITY calculation.
    Fixes the common case where the recorded "last transfer" was a $0
    trust move or quit-claim, making the naive equity-ratio meaningless
    (infinite or zero). See Han parcel 3394100120 for the canonical
    example: last transfer is 2015 trust move at $0, but actual last
    arms-length was $810K in 2013.

    The function is intentionally conservative: every tag requires
    nonzero values on the columns it depends on, so a parcel with
    sparse ingest data simply doesn't fire rather than producing a
    false-positive.
    """
    tags: list[dict] = []

    total_value = _safe_float(parcel.get('total_value'))
    owner_type  = (parcel.get('owner_type') or '').lower()
    stored_tenure = _safe_float(parcel.get('tenure_years'))

    # Prefer arms-length price and date when available.
    al_price = _safe_float(parcel.get('last_arms_length_price'))
    al_date  = parcel.get('last_arms_length_date')
    legacy_price = _safe_float(parcel.get('last_transfer_price'))

    # Which price anchors the equity ratio?
    if al_price > 0:
        equity_price = al_price
        equity_source = 'arms-length'
    else:
        equity_price = legacy_price
        equity_source = 'recorded'

    # Tenure used for HIGH EQUITY must match the price we're using.
    # If we're using the arms-length price, compute tenure from its date
    # so the multiplier's time horizon is honest. If the arms-length
    # date is unparseable, fall back to parcels_v3.tenure_years (itself
    # derived from last_transfer_date elsewhere).
    equity_tenure = stored_tenure
    if al_price > 0 and al_date:
        try:
            from datetime import date as _date, datetime as _dt
            if isinstance(al_date, str):
                d = _dt.strptime(al_date[:10], '%Y-%m-%d').date()
            elif isinstance(al_date, _date):
                d = al_date
            else:
                d = None
            if d:
                today = _date.today()
                equity_tenure = round(
                    (today.toordinal() - d.toordinal()) / 365.25, 1
                )
        except Exception:
            pass

    # ── HIGH EQUITY ───────────────────────────────────────────────────
    # Value-versus-sale multiplier. Requires all three inputs to be
    # real (nonzero, non-null) and tenure above the minimum.
    if (equity_price > 0
            and total_value > 0
            and equity_tenure >= HIGH_EQUITY_MIN_TENURE_YEARS):
        mult = total_value / equity_price
        if mult >= HIGH_EQUITY_MULT_THRESHOLD:
            anchor = (
                "last arms-length sale"
                if equity_source == 'arms-length'
                else "last sale"
            )
            tags.append({
                'label':       'HIGH EQUITY',
                'kind':        'high_equity',
                'description': (
                    f"Implied {mult:.1f}x appreciation since {anchor} "
                    f"({_fmt_dollars(equity_price)} → "
                    f"{_fmt_dollars(total_value)} over {equity_tenure:.0f} yrs)"
                ),
                'rank':        30,
            })

    # Tenure below uses the stored tenure_years (from parcels_v3), which
    # reflects the assessor's "last transfer" regardless of arms-length
    # status. That's correct for LEGACY HOLD / DEEP TENURE — those tags
    # describe continuous ownership, and a trust transfer within the
    # family doesn't break the continuity.
    tenure = stored_tenure

    # ── LEGACY HOLD (top tier) ────────────────────────────────────────
    # 40+ years of tenure. At this depth the tag is rare and the life-
    # change probability is high even without age data.
    if tenure >= LEGACY_HOLD_YEARS:
        tags.append({
            'label':       'LEGACY HOLD',
            'kind':        'legacy_hold',
            'description': (
                f"Owned {tenure:.0f}+ years; original buyers are almost "
                f"certainly in a life-change window"
            ),
            'rank':        25,
        })
    # ── DEEP TENURE ───────────────────────────────────────────────────
    # 30–39 years. Still meaningful but less rare. Note: we check this
    # only when LEGACY HOLD didn't fire, so tags don't double-up.
    elif tenure >= DEEP_TENURE_YEARS:
        tags.append({
            'label':       'DEEP TENURE',
            'kind':        'deep_tenure',
            'description': (
                f"Owned {tenure:.0f}+ years — multi-decade hold"
            ),
            'rank':        15,
        })

    # ── MATURE LLC ────────────────────────────────────────────────────
    # Investor exit-window trigger. Flags LLCs past the typical 5-year
    # hold. NOTE: the owner_type column has ingest-layer accuracy issues
    # (LLP-named entities sometimes classified as individual); this tag
    # is known to under-fire on 98004 for that reason.
    if owner_type == 'llc' and tenure >= MATURE_LLC_MIN_TENURE_YEARS:
        tags.append({
            'label':       'MATURE LLC',
            'kind':        'mature_llc',
            'description': (
                f"LLC-owned for {tenure:.0f} years — past typical investor "
                f"hold window"
            ),
            'rank':        20,
        })

    # Stable sort: highest rank first
    tags.sort(key=lambda t: -t['rank'])
    return tags


def tag_summary(parcels: list[dict]) -> dict:
    """
    Debugging helper: given a list of parcel dicts, count how many get
    each tag. Used by the diagnostic endpoint to verify tag distribution
    stays within the 10–20% target (so tags stay differentiating).

    Returns {tag_kind: count, '_total': int}.
    """
    from collections import Counter
    c: Counter = Counter()
    for p in parcels:
        tags = derive_tags(p)
        for t in tags:
            c[t['kind']] += 1
    result = dict(c)
    result['_total'] = len(parcels)
    return result
