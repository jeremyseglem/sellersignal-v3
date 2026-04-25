"""
SellerSignal v2 — Pipeline Orchestrator.

Runs the full signal-first pipeline end to end for one ZIP.
"""
from __future__ import annotations
import json

from lead_schema import CandidateReview, Lead
from candidate_search import (
    build_person_index,
    load_deed_chain_by_pin,
    search_death_inheritance_candidates,
    search_investor_disposition_candidates,
    search_retirement_candidates,
    search_pre_listing_structuring_candidates,
    search_divorce_candidates,
    search_relocation_candidates,
    search_financial_stress_candidates,
    dedupe_candidates,
)
from candidate_review import review_all_candidates, apply_cross_family_support
from lead_builder import build_leads
from briefing_render import render_briefing_markdown, render_briefing_manifest


def run_pipeline(
    zip_code: str,
    owners_db: dict,
    deed_csv_path: str,
    use_codes: dict[str, dict],
    mailing_addresses: dict[str, dict],
    obituary_signals: list[dict],
    retirement_signals: list[dict],
    zillow_events_by_pin: dict[str, list[dict]] = None,
    divorce_filings_csv: str = None,
    recorder_docs_csv: str = None,
) -> dict:
    """
    Execute the full pipeline for one ZIP.

    divorce_filings_csv: path to weekly export from KC Script Portal
                        (Family Law case search, last 30 days)
    recorder_docs_csv:   path to weekly export from KC Recorder LandmarkWeb
                        (Record Date Search filtered to NOD/Lis Pendens/Trustee Sale)
    """
    if zillow_events_by_pin is None:
        zillow_events_by_pin = {}
    # ─── STAGE 1: index owner DB ──────────────────────────────────────
    print(f"[1/6] Building person index for {len(owners_db)} parcels...")
    person_index = build_person_index(owners_db)
    residential_pin_count = sum(1 for pin in owners_db
                                if use_codes.get(pin, {}).get("prop_type") in ("R", "K"))
    print(f"      Indexed {len(person_index)} parcels with natural-person owners")
    print(f"      Eligible (R+K): {residential_pin_count} parcels — target universe")

    # ─── STAGE 2: load deed chain + build entity activity index ──────
    print(f"[2/6] Loading deed chain from {deed_csv_path}...")
    deed_chain_by_pin = load_deed_chain_by_pin(deed_csv_path)
    # Keep full index for cross-parcel activity BEFORE filtering to our owner DB
    from decision_signals import build_entity_activity_index
    activity_index = build_entity_activity_index(deed_chain_by_pin)
    print(f"      Loaded deed history for {len(deed_chain_by_pin)} parcels "
          f"(full KC universe for entity-activity index)")
    print(f"      Built entity activity index: {len(activity_index)} business entities")
    # Now filter to owner-DB parcels for the review layer
    deed_chain_by_pin = {pin: chain for pin, chain in deed_chain_by_pin.items()
                         if pin in owners_db}

    # ─── STAGE 3: candidate search per signal family ──────────────────
    print(f"[3/6] Running candidate search per signal family (residential only)...")
    signals_harvested: dict[str, int] = {}
    all_candidates = []

    death_cands = search_death_inheritance_candidates(
        obituary_signals=obituary_signals,
        person_index=person_index,
        owners_db=owners_db,
        use_codes=use_codes,
    )
    signals_harvested["death_inheritance"] = len(obituary_signals)
    all_candidates.extend(death_cands)
    print(f"      death_inheritance: {len(obituary_signals)} obituary signals → {len(death_cands)} residential candidates")

    inv_cands = search_investor_disposition_candidates(
        owners_db=owners_db,
        deed_chain_by_pin=deed_chain_by_pin,
        use_codes=use_codes,
    )
    signals_harvested["investor_disposition"] = len(inv_cands)
    all_candidates.extend(inv_cands)
    print(f"      investor_disposition: {len(inv_cands)} residential rotation candidates")

    ret_cands = search_retirement_candidates(
        retirement_signals=retirement_signals,
        person_index=person_index,
        owners_db=owners_db,
        use_codes=use_codes,
    )
    signals_harvested["retirement_downsize"] = len(retirement_signals)
    all_candidates.extend(ret_cands)
    print(f"      retirement_downsize: {len(retirement_signals)} retirement signals → {len(ret_cands)} residential candidates")

    prep_cands = search_pre_listing_structuring_candidates(
        owners_db=owners_db,
        deed_chain_by_pin=deed_chain_by_pin,
        use_codes=use_codes,
    )
    signals_harvested["pre_listing_structuring"] = len(prep_cands)
    all_candidates.extend(prep_cands)
    print(f"      pre_listing_structuring (trigger-only): {len(prep_cands)} residential candidates")

    # NEW: Absentee out-of-state
    from candidate_search import (
        search_absentee_oos_candidates, search_high_equity_long_tenure_candidates,
    )
    oos_cands = search_absentee_oos_candidates(
        owners_db=owners_db,
        mailing_addresses=mailing_addresses,
        use_codes=use_codes,
    )
    signals_harvested["absentee_oos_disposition"] = len(oos_cands)
    all_candidates.extend(oos_cands)
    print(f"      absentee_oos_disposition: {len(oos_cands)} residential out-of-state long-hold candidates")

    # NEW: High-equity long-tenure (soft watchlist, needs catalyst)
    heq_cands = search_high_equity_long_tenure_candidates(
        owners_db=owners_db,
        deed_chain_by_pin=deed_chain_by_pin,
        use_codes=use_codes,
    )
    signals_harvested["high_equity_long_tenure"] = len(heq_cands)
    all_candidates.extend(heq_cands)
    print(f"      high_equity_long_tenure: {len(heq_cands)} residential candidates")

    # NEW: Failed sale attempt (Zillow listing history)
    from candidate_search import search_failed_sale_attempt_candidates
    fsa_cands = search_failed_sale_attempt_candidates(
        owners_db=owners_db,
        use_codes=use_codes,
        zillow_events_by_pin=zillow_events_by_pin,
    )
    signals_harvested["failed_sale_attempt"] = len(zillow_events_by_pin)
    all_candidates.extend(fsa_cands)
    print(f"      failed_sale_attempt: {len(zillow_events_by_pin)} parcels scraped → {len(fsa_cands)} candidates")

    # NEW: Divorce unwinding (KC Superior Court Family Law filings)
    if divorce_filings_csv:
        from legal_filings import load_divorce_filings_csv, match_divorce_to_parcels
        filings = load_divorce_filings_csv(divorce_filings_csv)
        dissolution_only = [f for f in filings if f.is_dissolution]
        div_cands = match_divorce_to_parcels(
            filings=filings, owners_db=owners_db, use_codes=use_codes,
        )
        signals_harvested["divorce_unwinding"] = len(dissolution_only)
        all_candidates.extend(div_cands)
        print(f"      divorce_unwinding: {len(filings)} filings ({len(dissolution_only)} dissolution) → {len(div_cands)} candidates")
    else:
        signals_harvested["divorce_unwinding"] = 0
        print(f"      divorce_unwinding: no CSV provided (weekly KC Script Portal export not loaded)")

    # NEW: Financial stress (KC Recorder NOD/Lis Pendens/Trustee Sale)
    if recorder_docs_csv:
        from legal_filings import load_recorder_documents_csv, match_recorder_to_parcels
        docs = load_recorder_documents_csv(recorder_docs_csv)
        fs_cands = match_recorder_to_parcels(
            docs=docs, owners_db=owners_db, use_codes=use_codes,
        )
        signals_harvested["financial_stress"] = len(docs)
        all_candidates.extend(fs_cands)
        print(f"      financial_stress: {len(docs)} adverse recordings → {len(fs_cands)} candidates")
    else:
        signals_harvested["financial_stress"] = 0
        print(f"      financial_stress: no CSV provided (weekly LandmarkWeb export not loaded)")

    for fname in ("relocation_executive",):
        signals_harvested[fname] = 0

    all_candidates = dedupe_candidates(all_candidates)
    print(f"      Total unique (family, parcel) candidates: {len(all_candidates)}")

    # ─── STAGE 4: review candidates ────────────────────────────────────
    print(f"[4/6] Reviewing candidates (with decision-signal activation)...")
    reviews = review_all_candidates(
        candidates=all_candidates,
        owners_db=owners_db,
        deed_chain_by_pin=deed_chain_by_pin,
        person_index=person_index,
        activity_index=activity_index,
    )
    # Cross-family support boost
    reviews = apply_cross_family_support(reviews)

    status_counts = {"confirmed": 0, "weak": 0, "rejected": 0}
    for r in reviews:
        status_counts[r.candidate_status] += 1
    print(f"      Confirmed: {status_counts['confirmed']}  "
          f"Weak: {status_counts['weak']}  Rejected: {status_counts['rejected']}")

    # ─── STAGE 5: build leads ──────────────────────────────────────────
    print(f"[5/6] Building leads from confirmed reviews...")
    leads = build_leads(reviews)
    print(f"      Shipped {len(leads)} leads across tiers")

    # ─── STAGE 6: group absentee leads by owner, then render ──────────
    print(f"[6/6] Rendering briefing...")
    from briefing_render import group_absentee_oos_by_owner
    leads = group_absentee_oos_by_owner(leads)
    markdown = render_briefing_markdown(
        leads=leads, reviews=reviews,
        zip_code=zip_code, signals_harvested=signals_harvested,
    )
    manifest = render_briefing_manifest(
        leads=leads, reviews=reviews,
        zip_code=zip_code, signals_harvested=signals_harvested,
    )

    return {
        "markdown": markdown,
        "manifest": manifest,
        "leads": leads,
        "reviews": reviews,
    }
