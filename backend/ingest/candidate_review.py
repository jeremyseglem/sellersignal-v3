"""
SellerSignal v2 — Candidate Review Engine.

For each (signal_family, parcel) candidate, gather all evidence, classify it,
and decide confirmed / weak / rejected.

This is where most candidates die. That's the point.
"""
from __future__ import annotations
from collections import defaultdict

from lead_schema import CandidateReview, Evidence
from evidence_resolution import (
    resolve_death_inheritance_evidence,
    resolve_investor_disposition_evidence,
    resolve_retirement_evidence,
    resolve_pre_listing_structuring_evidence,
    resolve_absentee_oos_evidence,
    resolve_high_equity_long_tenure_evidence,
    resolve_failed_sale_attempt_evidence,
    resolve_divorce_unwinding_evidence,
    resolve_financial_stress_evidence,
    classify_candidate,
    is_entity_owner,
)
from signal_registry import SIGNAL_REGISTRY


def review_candidate(
    candidate: dict,
    owners_db: dict,
    deed_chain_by_pin: dict,
    person_index: dict,
    concurrent_families_per_parcel: dict,
    activity_index: dict,
) -> CandidateReview:
    """
    Takes one (signal_family, parcel) candidate and produces a CandidateReview.

    concurrent_families_per_parcel: {parcel_id: [families_with_triggers, ...]}
      used by pre_listing_structuring to detect cross-family support.
    activity_index: {entity_name: [activity rows]} for behavioral/decision signals.
    """
    family = candidate["signal_family"]
    pin = candidate["parcel_id"]
    owner_info = owners_db.get(pin, {})
    owner_name = owner_info.get("owner_name", "")
    address = owner_info.get("address", "") or "(no address)"
    deed_chain = deed_chain_by_pin.get(pin, [])

    evidence: list[Evidence] = []
    if family == "death_inheritance":
        hint = candidate.get("trigger_hint", {})
        obit_tokens = set(hint["obit_tokens"])
        import re as _re
        name = hint["obit"].get("name", "")
        name_tokens = [t.upper() for t in _re.sub(r"['\"]", "", name).split()
                       if t.isalpha() and len(t) >= 2]
        name_tokens = [t for t in name_tokens
                       if t not in ("JR", "SR", "II", "III", "IV", "MR", "MRS", "DR")]
        surname = name_tokens[-1] if name_tokens else ""

        evidence = resolve_death_inheritance_evidence(
            obit_signal=hint["obit"],
            owner_record=owner_info,
            deed_chain=deed_chain,
            person_tokens_on_title=person_index.get(pin, []),
            obit_tokens=obit_tokens,
            surname=surname,
        )
    elif family == "investor_disposition":
        evidence = resolve_investor_disposition_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint"),
            activity_index=activity_index,
            parcel_id=pin,
        )
    elif family == "retirement_downsize":
        hint = candidate.get("trigger_hint", {})
        evidence = resolve_retirement_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            retirement_signal=hint.get("retirement"),
        )
    elif family == "pre_listing_structuring":
        concurrent = concurrent_families_per_parcel.get(pin, [])
        evidence = resolve_pre_listing_structuring_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            concurrent_signals=concurrent,
        )
    elif family == "absentee_oos_disposition":
        concurrent = concurrent_families_per_parcel.get(pin, [])
        evidence = resolve_absentee_oos_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint", {}),
            cross_family_signals=concurrent,
        )
    elif family == "high_equity_long_tenure":
        concurrent = concurrent_families_per_parcel.get(pin, [])
        evidence = resolve_high_equity_long_tenure_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint", {}),
            cross_family_signals=concurrent,
        )
    elif family == "failed_sale_attempt":
        evidence = resolve_failed_sale_attempt_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint", {}),
        )
    elif family == "divorce_unwinding":
        evidence = resolve_divorce_unwinding_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint", {}),
        )
    elif family == "financial_stress":
        evidence = resolve_financial_stress_evidence(
            owner_record=owner_info,
            deed_chain=deed_chain,
            trigger_hint=candidate.get("trigger_hint", {}),
        )

    spec = SIGNAL_REGISTRY[family]
    status, confidence, reason = classify_candidate(
        evidence=evidence,
        family=family,
        can_promote_to_lead=spec.can_promote_to_lead,
    )

    return CandidateReview(
        signal_family=family,
        parcel_id=pin,
        owner_name=owner_name,
        address=address,
        evidence=evidence,
        candidate_status=status,
        confidence=confidence,
        reason=reason,
        value=owner_info.get("value"),
        tenure_years=owner_info.get("tenure_years"),
        last_transfer_date=owner_info.get("last_transfer_date"),
    )


def review_all_candidates(
    candidates: list[dict],
    owners_db: dict,
    deed_chain_by_pin: dict,
    person_index: dict,
    activity_index: dict,
) -> list[CandidateReview]:
    """
    Run review on all candidates. Handles two-pass logic for pre_listing_structuring.
    """
    # Families that NEED cross-family context go in pass 2
    CROSS_FAMILY_DEPENDENT = {
        "pre_listing_structuring",
        "absentee_oos_disposition",
        "high_equity_long_tenure",
    }
    concurrent: dict[str, set[str]] = defaultdict(set)
    first_pass_reviews = []
    second_pass_candidates = []

    for c in candidates:
        if c["signal_family"] in CROSS_FAMILY_DEPENDENT:
            second_pass_candidates.append(c)
        else:
            r = review_candidate(
                candidate=c, owners_db=owners_db,
                deed_chain_by_pin=deed_chain_by_pin,
                person_index=person_index,
                concurrent_families_per_parcel={},
                activity_index=activity_index,
            )
            first_pass_reviews.append(r)
            if r.triggers:
                concurrent[r.parcel_id].add(r.signal_family)

    second_pass_reviews = []
    for c in second_pass_candidates:
        r = review_candidate(
            candidate=c, owners_db=owners_db,
            deed_chain_by_pin=deed_chain_by_pin,
            person_index=person_index,
            concurrent_families_per_parcel={k: list(v) for k, v in concurrent.items()},
            activity_index=activity_index,
        )
        second_pass_reviews.append(r)

    return first_pass_reviews + second_pass_reviews


# ═══════════════════════════════════════════════════════════════════════
# POST-REVIEW: promote cross-family evidence
# ═══════════════════════════════════════════════════════════════════════
def apply_cross_family_support(reviews: list[CandidateReview]) -> list[CandidateReview]:
    """
    If a pre_listing_structuring candidate has a valid trigger (contradiction-free),
    AND another family has a confirmed review for the same parcel,
    add cross-family support evidence to the other family's review.

    This lets pre_listing_structuring strengthen other leads without ever becoming
    a lead itself.
    """
    # Find parcels with valid pre_listing_structuring triggers (not rejected on contradiction)
    strong_structuring: dict[str, CandidateReview] = {}
    for r in reviews:
        if r.signal_family != "pre_listing_structuring": continue
        if r.candidate_status == "rejected": continue
        # Valid structuring: has a trigger, no fatal contradictions
        if r.triggers and not r.resolutions:
            strong_structuring[r.parcel_id] = r

    if not strong_structuring:
        return reviews

    # Attach cross-family support to other family reviews for the same parcel
    for r in reviews:
        if r.signal_family == "pre_listing_structuring": continue
        if r.parcel_id not in strong_structuring: continue
        if r.candidate_status != "confirmed": continue
        r.evidence.append(Evidence(
            role="support",
            source="cross_family:pre_listing_structuring",
            description=(f"Concurrent pre-listing structuring trigger at same parcel "
                         f"strengthens hypothesis"),
            weight=2.0,
        ))
        # Re-classify with new support
        from evidence_resolution import classify_candidate as _classify
        spec_can_promote = True  # this is the other family, not structuring
        status, conf, reason = _classify(r.evidence, r.signal_family, spec_can_promote)
        r.candidate_status = status
        r.confidence = conf
        r.reason = reason

    return reviews
