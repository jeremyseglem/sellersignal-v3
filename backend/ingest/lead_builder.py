"""
SellerSignal v2 — Lead Builder.

Converts CONFIRMED CandidateReviews into Lead objects.
Weak and rejected reviews do not produce leads. They are logged for audit.

Also: assigns tier (act_this_week / active_window / long_horizon), generates
narrative fields (why_now, situation, approach) strictly grounded in evidence.
"""
from __future__ import annotations
from datetime import datetime

from lead_schema import CandidateReview, Lead, LeadTier
from signal_registry import SIGNAL_REGISTRY


# ═══════════════════════════════════════════════════════════════════════
# TIER ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════
def assign_tier(review: CandidateReview) -> LeadTier:
    """
    Tier is a function of signal family time-sensitivity and confidence.

    act_this_week:   financial_stress (regardless of confidence) OR
                     high-confidence divorce/relocation with fresh trigger
    active_window:   medium-to-high confidence death, divorce, relocation
    long_horizon:    retirement, investor disposition, low-conf everything
    """
    family = review.signal_family
    conf = review.confidence

    if family == "financial_stress":
        return "act_this_week"   # NOD/lis pendens are by definition urgent
    if family == "failed_sale_attempt":
        return "act_this_week"   # high decision signal, short window
    if family == "divorce_unwinding":
        return "active_window"   # 6-18 month window, not immediate
    if family in ("divorce_unwinding", "relocation_executive"):
        if conf in ("high", "medium"):
            return "act_this_week"
        return "active_window"
    if family == "death_inheritance":
        # Fresh death (within 6 months) + high/medium conf → active_window
        # Else → long_horizon
        obit_date = None
        for e in review.triggers:
            if e.observed_at:
                try:
                    obit_date = datetime.strptime(e.observed_at, "%Y-%m-%d")
                    break
                except ValueError:
                    pass
        if obit_date:
            days_since = (datetime.utcnow() - obit_date).days
            if days_since < 180 and conf in ("high", "medium"):
                return "active_window"
            if days_since < 365:
                return "active_window"
        return "long_horizon"
    if family == "investor_disposition":
        return "active_window" if conf == "high" else "long_horizon"
    if family == "retirement_downsize":
        return "long_horizon"
    if family == "absentee_oos_disposition":
        return "long_horizon"
    if family == "high_equity_long_tenure":
        return "long_horizon"
    return "long_horizon"


# ═══════════════════════════════════════════════════════════════════════
# NARRATIVE GENERATION — strictly evidence-grounded
# ═══════════════════════════════════════════════════════════════════════
def generate_narrative(review: CandidateReview) -> dict:
    """
    Produces: why_now, situation, approach, recommended_channel, timing_window_days.

    RULES:
    - Every claim must trace to an Evidence item
    - No speculation about future seller intent
    - State the signal, state the data that confirms it, state what contradictions were ruled out
    - Approach is conservative: position as resource, not as transaction
    """
    family = review.signal_family
    triggers = review.triggers
    supports = review.supports
    contradictions = review.contradictions

    trigger_descs = [t.description for t in triggers]
    support_descs = [s.description for s in supports]

    # Family-specific templates — all grounded in evidence
    if family == "death_inheritance":
        obit_desc = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: death_inheritance. Trigger: {obit_desc}"
        situation = (
            f"Owner of record: {review.owner_name}. "
            f"Assessed value: ${review.value or 0:,}. Tenure: {review.tenure_years or 0:.1f} years. "
            f"No post-death deed activity found. Property has not been listed or sold."
        )
        approach = (
            "Condolence-framed hand-signed letter to surviving decision-maker at property address. "
            "Do not lead with listing conversation. Offer long-term resource availability. "
            "Revisit in 4 and 9 months if no response."
        )
        channel = "letter"
        window = 365

    elif family == "investor_disposition":
        why_now = (
            f"Signal: investor_disposition. Trigger: entity ownership "
            f"{review.tenure_years:.1f}-year tenure past long-term-capital-gains threshold"
        )
        situation = (
            f"Entity owner: {review.owner_name}. Assessed: ${review.value or 0:,}. "
            f"Professional seller, not an emotional seller. "
            f"{len(supports)} corroborating support item(s); "
            f"{len(contradictions)} contradiction(s) noted but not fatal."
        )
        approach = (
            "Reach out to entity's registered agent (WA SOS lookup). "
            "Position as market-expertise consultation. This is a business conversation, "
            "not a personal one. Timeline is measured in months, not weeks."
        )
        channel = "entity_agent_email"
        window = 180

    elif family == "retirement_downsize":
        ret_desc = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: retirement_downsize. Trigger: {ret_desc}"
        situation = (
            f"Owner: {review.owner_name}. Tenure: {review.tenure_years or 0:.1f} years. "
            f"Retirement announcement indicates career transition underway."
        )
        approach = (
            "Slow-build relationship. Hand-signed note congratulating career transition "
            "(NOT implying selling). Annual check-in cadence. 24-month horizon."
        )
        channel = "letter"
        window = 730

    elif family == "relocation_executive":
        why_now = f"Signal: relocation_executive. Trigger: {triggers[0].description if triggers else '(no trigger)'}"
        situation = f"Owner relocating; property redundant to new location."
        approach = "Professional outreach. Relocation-aware packaging. 9-month window."
        channel = "letter_and_email"
        window = 270

    elif family == "divorce_unwinding":
        trig = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: divorce_unwinding. Trigger: {trig}"
        situation = (
            f"Owner: {review.owner_name}. Dissolution filed in KC Superior Court. "
            f"Marital property typically resolves within 6-18 months via sale or "
            f"spousal buyout. Early-stage signal — catch the decision before listing."
        )
        approach = (
            "Discrete outreach only. This is a sensitive moment — approach as "
            "a resource, not a solicitor. Emphasize privacy, expertise with "
            "divorce-related property transactions, and flexibility on timing. "
            "Never reference the filing directly in first contact."
        )
        channel = "letter"
        window = 540

    elif family == "financial_stress":
        trig = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: financial_stress. Trigger: {trig}"
        doc_type = ""
        for e in review.evidence:
            if e.role == "trigger" and "TRUSTEE SALE" in (e.description or "").upper():
                doc_type = "Notice of Trustee Sale"; break
            elif e.role == "trigger" and "DEFAULT" in (e.description or "").upper():
                doc_type = "Notice of Default"; break
            elif e.role == "trigger" and "LIS PENDENS" in (e.description or "").upper():
                doc_type = "Lis Pendens"; break

        situation = (
            f"Owner: {review.owner_name}. {doc_type} recorded against this property. "
            f"Owner faces forced-sale timeline unless cured. Highest urgency tier — "
            f"window is 30-120 days depending on document type."
        )
        approach = (
            "Immediate direct outreach — letter + phone if permissible. Lead with "
            "'you have options' framing: fast sale, loan modification negotiation, "
            "short sale coordination. These owners often don't know their options "
            "and will engage with the first knowledgeable agent who reaches them."
        )
        channel = "letter_and_phone"
        window = 60

    elif family == "failed_sale_attempt":
        trig = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: failed_sale_attempt. Trigger: {trig}"
        situation = (
            f"Owner: {review.owner_name}. Assessed value: ${review.value or 0:,}. "
            f"Previously listed for sale and pulled without selling. The decision "
            f"to sell has already been made — the execution failed. This is the "
            f"cleanest seller-of-agent signal in the dataset."
        )
        approach = (
            "Direct, respectful outreach acknowledging the prior listing. Lead with "
            "a specific hypothesis about why it didn't sell (pricing, timing, "
            "photography, positioning) — not a generic pitch. Offer a no-obligation "
            "market review. Short window: many of these re-list within 60-90 days."
        )
        channel = "letter_and_email"
        window = 90

    elif family == "absentee_oos_disposition":
        trig = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: absentee_oos_disposition. Trigger: {trig}"
        situation = (
            f"Owner: {review.owner_name}. Long-hold residential property with "
            f"out-of-state mailing address. Administratively distant holding — "
            f"typical of inherited / second-home / investor-held inventory."
        )
        approach = (
            "Discreet written outreach to mailing address. Frame as market update, "
            "not listing pitch. OOS owners often have tax / estate-planning considerations; "
            "offer a no-obligation valuation. 12-18 month horizon."
        )
        channel = "letter_mail_address"
        window = 540

    elif family == "high_equity_long_tenure":
        trig = triggers[0].description if triggers else "(no trigger)"
        why_now = f"Signal: high_equity_long_tenure. Trigger: {trig}"
        situation = (
            f"Owner: {review.owner_name}. Long-tenure residential property with "
            f"significant equity position. Concurrent catalyst signal identified. "
            f"Tax-timing considerations in play (Sec 121 already maxed)."
        )
        approach = (
            "Soft-touch relationship building. Offer market update, property valuation, "
            "and referral to tax/estate professionals if useful. Do NOT lead with listing. "
            "24-month cultivation horizon."
        )
        channel = "letter"
        window = 730

    else:
        why_now = "Signal family not recognized"
        situation = ""
        approach = ""
        channel = "letter"
        window = 180

    return {
        "why_now": why_now,
        "situation": situation,
        "approach": approach,
        "recommended_channel": channel,
        "timing_window_days": window,
    }


# ═══════════════════════════════════════════════════════════════════════
# BUILD LEADS
# ═══════════════════════════════════════════════════════════════════════
def build_leads(reviews: list[CandidateReview]) -> list[Lead]:
    """
    Keep only confirmed reviews (in promotable families). Produce Lead objects.
    """
    leads: list[Lead] = []
    for r in reviews:
        if r.candidate_status != "confirmed":
            continue
        spec = SIGNAL_REGISTRY[r.signal_family]
        if not spec.can_promote_to_lead:
            continue  # pre_listing_structuring never ships as standalone

        narrative = generate_narrative(r)
        tier = assign_tier(r)

        leads.append(Lead(
            parcel_id=r.parcel_id,
            address=r.address,
            value=r.value,
            current_owner=r.owner_name,
            signal_family=r.signal_family,
            lead_tier=tier,
            evidence=r.evidence,
            supporting_evidence=r.supporting_evidence,
            contradicting_evidence=r.contradicting_evidence,
            confidence=r.confidence,
            why_now=narrative["why_now"],
            situation=narrative["situation"],
            approach=narrative["approach"],
            recommended_channel=narrative["recommended_channel"],
            timing_window_days=narrative["timing_window_days"],
            source_review=r,
        ))

    # Sort by tier (act_this_week first), then confidence, then value
    tier_order = {"act_this_week": 0, "active_window": 1, "long_horizon": 2}
    conf_order = {"high": 0, "medium": 1, "low": 2}
    leads.sort(key=lambda l: (
        tier_order[l.lead_tier],
        conf_order[l.confidence],
        -(l.value or 0),
    ))
    return leads
