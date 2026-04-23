"""
SellerSignal — Signal Registry (canonical source of truth).

Defines the 10 seller-signal families and the candidate-search specs for each.

IMPORTANT: These are HUMAN SELLER SITUATIONS, not data categories.
- death_inheritance is "owner died", not "trust→individual transfer"
- divorce_unwinding is "marital split", not "quit-claim 2→1"
- pre_listing_structuring is trigger-only, NEVER a standalone lead

Each family declares:
  - description (the human situation)
  - trigger_sources (what creates a candidate)
  - support_sources (what strengthens a candidate)
  - contradiction_sources (what weakens it)
  - resolution_sources (what kills it)
  - data_availability (what we can actually check today)
  - time_sensitivity (how fast this situation moves)

──────────────────────────────────────────────────────────────────────────
CURRENT PRODUCTION STATE (as of 2026-04-23)
──────────────────────────────────────────────────────────────────────────
Live harvesters feeding raw_signals_v3:
  • kc_superior_court  → probate + divorce signals (WA King County)
                         8,705 probate + 5,344 divorce rows in DB
  • obituary_rss       → Dignity Memorial + Seattle Times obit signals
                         164 obit rows in DB
  • kc_treasury        → KC tax-foreclosure snapshot (Socrata SODA)
                         167 parcel rows in DB

Parcel-state signals computed at read time (no harvester needed):
  • absentee_oos_disposition     (is_out_of_state column)
  • high_equity_long_tenure      (tenure_years + total_value)
  • retirement_downsize          (partial — missing age data)
  • investor_disposition         (owner_type = 'llc' + tenure)
  • pre_listing_structuring      (trigger-only; deed history)

NOT yet built:
  • relocation_executive         (needs historical mail-addr deltas +
                                  LinkedIn job-change scraper)
  • failed_sale_attempt          (Layer 1 parser exists; Layer 2 SerpAPI
                                  Zillow queries run in old investigation
                                  flow; Layer 3 bulk scraper not built)
  • financial_stress (NOD/NOTS)  (KC Recorder is captcha-blocked; newspaper
                                  legal notices feed unexplored; third-party
                                  property-data aggregators are not used per
                                  project policy)

Harvester → briefing bridge:
  /api/briefings/{zip} reads raw_signal_matches_v3 and promotes matched
  parcels via backend/selection/harvester_overlay.py. A strict harvester
  match fires pressure=3 → call_now. Current prod: 245 pins matched in
  98004, 64 promoted to call_now. See ``harvester_overlay.py`` for the
  pressure table.
──────────────────────────────────────────────────────────────────────────
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class SignalFamilySpec:
    family: str
    description: str
    trigger_sources: list[str]
    support_sources: list[str]
    contradiction_sources: list[str]
    resolution_sources: list[str]
    data_available_today: bool
    missing_data: list[str]
    typical_time_horizon_days: int
    can_promote_to_lead: bool = True   # pre_listing_structuring = False


SIGNAL_REGISTRY: dict[str, SignalFamilySpec] = {
    # ─── DEATH / INHERITANCE DISPOSITION ───────────────────────────────
    "death_inheritance": SignalFamilySpec(
        family="death_inheritance",
        description=(
            "Owner died; estate is in motion. Property will typically move within "
            "6-24 months depending on heir alignment and estate complexity."
        ),
        trigger_sources=[
            "obituary_name_match",
            "probate_docket_match",
            "estate_seller_in_deed",
        ],
        support_sources=[
            "trust_to_individual_transfer",
            "heir_name_in_obituary",
            "owner_tenure_over_15_years",
            "parcel_in_same_family_cluster",
        ],
        contradiction_sources=[
            "owner_names_dont_overlap_obit",
            "property_acquired_after_death",
            "owner_type_is_entity_not_person",
        ],
        resolution_sources=[
            "arms_length_sale_after_death",
            "active_or_pending_listing",
            "deed_transfer_post_death_to_unrelated",
        ],
        data_available_today=True,
        missing_data=[
            # probate + obit harvesters SHIPPED (kc_superior_court + obituary_rss).
            # Death certificates still unavailable (not public in WA); we infer
            # via obit + probate cross-reference, which produces convergence
            # signals when both fire on the same owner.
            "WA death certificate feed (not public)",
        ],
        typical_time_horizon_days=365,
    ),

    # ─── ABSENTEE OWNER / OUT-OF-STATE DISPOSITION ─────────────────────
    # New signal family — owner lives in another state, property is a
    # second home or rental that's becoming disposable.
    "absentee_oos_disposition": SignalFamilySpec(
        family="absentee_oos_disposition",
        description=(
            "Owner's mailing address is out of state. Property is a "
            "second-home / inherited property / investment that has become "
            "administratively distant. These owners often shed property after "
            "a life event (retirement, illness, heir dispersal). A decision signal "
            "is still required — out-of-state alone describes state, not action."
        ),
        trigger_sources=[
            "mail_address_out_of_state_with_long_tenure",  # >10y OOS = active consideration
            "mail_address_changed_to_oos_recently",         # needs historical data (not wired)
        ],
        support_sources=[
            "property_is_high_value_non_primary",
            "owner_age_proxy_senior",
        ],
        contradiction_sources=[
            "recent_out_of_state_acquisition",  # just bought, not disposing
            "owner_clearly_uses_as_second_home",
        ],
        resolution_sources=[
            "arms_length_sale",
            "active_listing",
        ],
        data_available_today=True,
        missing_data=[
            # search_absentee_oos_candidates() exists in pipeline/candidate_search.py
            # but is NOT wired into the production briefing flow — only into
            # the dead v2 research pipeline. The is_out_of_state column on
            # parcels_v3 IS populated and usable today for a read-time check,
            # but no promotion path for this family is live yet.
            "Production wiring: candidate_search is only called by "
            "research/run_bellevue.py, not by the live /api/briefings flow",
            "Historical mail-address deltas for true relocation signal "
            "(mail_address_changed_to_oos_recently trigger)",
        ],
        typical_time_horizon_days=540,
    ),

    # ─── HIGH-EQUITY LONG-TENURE DISPOSITION ───────────────────────────
    # Tax-timing-motivated sellers: very long hold + high equity hits the
    # $500k primary-residence exclusion cap and triggers planning conversations.
    "high_equity_long_tenure": SignalFamilySpec(
        family="high_equity_long_tenure",
        description=(
            "Owner has held 20+ years with estimated equity far above the "
            "Sec 121 primary-residence exclusion ($500k joint / $250k single). "
            "Tax-motivated to sell now vs. step-up-at-death tradeoff. Soft signal — "
            "requires a life-event or age trigger to activate."
        ),
        trigger_sources=[
            "tenure_over_20_years_plus_equity_3x_purchase",
            "senior_exemption_flag_plus_long_tenure",
        ],
        support_sources=[
            "owner_occupied_primary_residence",
            "recent_trust_formation",
        ],
        contradiction_sources=[
            "entity_ownership",
            "recent_refinance_equity_extracted",
        ],
        resolution_sources=[
            "arms_length_sale",
            "active_listing",
        ],
        data_available_today=True,
        missing_data=[
            # Same wiring gap as absentee_oos_disposition:
            # search_high_equity_long_tenure_candidates() exists but is only
            # called by research/run_bellevue.py. tenure_years + total_value
            # + last_transfer_price ARE all populated in parcels_v3, so this
            # would be straightforward to wire at read time in briefings.
            "Production wiring: candidate_search is only called by "
            "research/run_bellevue.py, not by the live /api/briefings flow",
            "KC senior exemption file (for senior_exemption_flag_plus_long_tenure trigger)",
            "Owner age data (for age-based activation)",
        ],
        typical_time_horizon_days=730,
    ),

    # ─── DIVORCE / ASSET UNWINDING ─────────────────────────────────────
    "divorce_unwinding": SignalFamilySpec(
        family="divorce_unwinding",
        description=(
            "Married couple separating; marital property must be divided."
        ),
        trigger_sources=[
            "divorce_docket_match",
            "public_divorce_announcement",
        ],
        support_sources=[
            "quit_claim_2_to_1_ownership",
            "shared_last_name_separation",
            "mail_address_change_one_party",
        ],
        contradiction_sources=[
            "quit_claim_into_trust",
            "quit_claim_family_restructure",
        ],
        resolution_sources=[
            "arms_length_sale_after_separation",
            "active_or_pending_listing",
        ],
        data_available_today=True,
        missing_data=[
            # kc_superior_court harvester SHIPPED — 5,344 divorce signals in
            # raw_signals_v3 as of 2026-04-23. Signals surface in the
            # briefing via harvester_overlay.py (strict divorce match →
            # pressure=3 → call_now). Public divorce announcements in local
            # press + quit-claim-2-to-1 analysis still unbuilt.
            "Public divorce announcements from local press (newspaper feeds)",
            "Automated quit-claim-2-to-1 detector over deed chain",
        ],
        typical_time_horizon_days=540,
    ),

    # ─── RETIREMENT / DOWNSIZE ─────────────────────────────────────────
    "retirement_downsize": SignalFamilySpec(
        family="retirement_downsize",
        description=(
            "Owner at retirement age considering downsize / second home / care facility."
        ),
        trigger_sources=[
            "retirement_announcement_name_match",
            "senior_exemption_flag",
            "owner_tenure_over_20_years_individual",
        ],
        support_sources=[
            "owner_occupied_matches_mail",
            "trust_formation_recent",
        ],
        contradiction_sources=[
            "rental_property_not_owner_occupied",
            "owner_young_or_midcareer",
        ],
        resolution_sources=[
            "arms_length_sale",
            "active_listing",
        ],
        data_available_today=True,
        missing_data=[
            # Partial: tenure-based trigger works today (tenure_years populated
            # in parcels_v3), but the search function is not wired into the
            # live briefing flow — only into research/run_bellevue.py.
            "Production wiring: search_retirement_candidates is only called "
            "by research/run_bellevue.py, not the live /api/briefings flow",
            "Age / date-of-birth data (for owner_age_proxy_senior trigger)",
            "LinkedIn retirement announcement scraper (for "
            "retirement_announcement_name_match trigger)",
        ],
        typical_time_horizon_days=730,
    ),

    # ─── RELOCATION / EXECUTIVE MOVE ───────────────────────────────────
    "relocation_executive": SignalFamilySpec(
        family="relocation_executive",
        description="Owner relocating for job / family; property becomes redundant.",
        trigger_sources=[
            "mail_address_delta_out_of_state",
            "executive_move_press_release_name_match",
            "sec_filing_executive_change",
        ],
        support_sources=[
            "mail_address_different_from_property",
            "vacancy_indicators",
            "company_hq_relocation_employee",
        ],
        contradiction_sources=[
            "second_home_explicit_indication",
            "rental_property_already",
        ],
        resolution_sources=["arms_length_sale", "active_listing"],
        data_available_today=False,
        missing_data=["historical mail-address deltas", "LinkedIn job-change scraper"],
        typical_time_horizon_days=270,
    ),

    # ─── FINANCIAL STRESS ──────────────────────────────────────────────
    "financial_stress": SignalFamilySpec(
        family="financial_stress",
        description=(
            "Owner facing involuntary liquidation pressure. Highest acuity."
        ),
        trigger_sources=[
            "notice_of_default_filed",
            "lis_pendens_filed",
            "tax_delinquency_3_year",
            "trustee_sale_scheduled",
            "bankruptcy_filing_name_match",
        ],
        support_sources=[
            "distressed_refinance_pattern",
            "rapid_equity_extraction",
            "multiple_liens_on_property",
        ],
        contradiction_sources=[
            "lien_satisfied",
            "bankruptcy_dismissed",
        ],
        resolution_sources=[
            "trustee_sale_completed",
            "arms_length_sale",
            "delinquency_cured",
        ],
        data_available_today=True,   # partial — tax_foreclosure harvester live
        missing_data=[
            # PARTIAL: tax_delinquency_3_year covered by kc_treasury harvester
            # (167 KC parcels in DB). notice_of_default / lis_pendens /
            # trustee_sale still unbuilt — see below.
            "KC Recorder NOD / lis pendens / trustee sale docs "
            "(LandmarkWeb portal is captcha-blocked; probe endpoint confirmed "
            "HTTP 200 with body 'Invalid Captcha' on naive POST — captcha is "
            "an engineered anti-automation control, not ToS boilerplate)",
            "Newspaper legal notices feed (Seattle Times, Bellevue Reporter — "
            "NOTS must be published by WA law; unexplored as of 2026-04-23)",
            "PACER bankruptcy scraper",
        ],
        typical_time_horizon_days=120,
    ),

    # ─── INVESTOR DISPOSITION ──────────────────────────────────────────
    "investor_disposition": SignalFamilySpec(
        family="investor_disposition",
        description=(
            "Entity owner rotating inventory. Requires asset-level exit signal."
        ),
        trigger_sources=[
            "asset_exit_window_match",
            "hold_overdue_relative_to_entity_pattern",
        ],
        support_sources=[
            "portfolio_churn_other_parcels",
            "cap_gains_holding_period_reached",
        ],
        contradiction_sources=[
            "active_acquisition_mode",
            "long_term_hold_investment",
            "still_in_renovation_phase",
        ],
        resolution_sources=[
            "arms_length_sale",
            "active_listing",
        ],
        data_available_today=True,
        missing_data=[
            # Briefing surfaces investor_disposition today via parcel-state
            # signals (owner_type='llc' + tenure_years above typical exit
            # window → band 2.5 or 3). No harvester-sourced catalyst yet.
            "WA SOS entity filings (for dissolution / registered-agent-change "
            "catalysts that would promote passive holds to active leads)",
            "KC building permits for renovation-complete signal",
        ],
        typical_time_horizon_days=180,
    ),

    # ─── FAILED SALE ATTEMPT ──────────────────────────────────────────
    # The highest-signal category: "they tried to sell and failed, still want to."
    #
    # Three layers exist:
    #   Layer 1 — Parser + detector (SHIPPED in backend/ingest/zillow_listings.py):
    #     parse_price_history_from_markdown() + detect_failed_sale_attempt()
    #     turn Zillow price-history tables into failed_sale signals. Pure
    #     logic, no fetch.
    #   Layer 2 — SerpAPI Zillow queries (LIVE in old investigation flow):
    #     The deep investigation runs "'{street}' '{city}' site:zillow.com"
    #     via SerpAPI and extracts coarse signals from snippets. Covers only
    #     deep-investigated parcels (~50/ZIP), not the full parcel base.
    #   Layer 3 — Bulk scraper (NOT BUILT):
    #     Full per-parcel Zillow fetches. Requires rotating-residential-IP
    #     infrastructure (ScraperAPI ~$49/mo or equivalent). Direct scraping
    #     from a single origin will hit rate limits and soft blocks.
    "failed_sale_attempt": SignalFamilySpec(
        family="failed_sale_attempt",
        description=(
            "Property was listed for sale and then withdrawn/expired without "
            "selling. Owner has already made the mental decision to sell but "
            "couldn't execute — the single cleanest buyer-of-agent signal in "
            "real estate."
        ),
        trigger_sources=[
            "zillow_listing_removed_no_subsequent_sale",
            "zillow_price_decrease_struggle",
            "zillow_stale_listing_180_plus_days",
        ],
        support_sources=[
            "multiple_price_reductions",
            "high_days_on_market",
            "concurrent_life_event_signal",
            "owner_tenure_suggests_ready",
        ],
        contradiction_sources=[
            "listing_withdrawn_then_relisted_at_higher_price",  # confidence-seeker
            "recent_sold_after_removal",  # resolved
            "builder_test_listing_pattern",  # spec home tests
        ],
        resolution_sources=[
            "arms_length_sale_after_removal",
            "active_relisting_same_agent",
        ],
        data_available_today=True,   # architecture built; bulk scrape needs infra
        missing_data=[
            # See module-level comment for 3-layer breakdown.
            "Layer 3 bulk Zillow scraper (ScraperAPI / Bright Data / Zyte — "
            "~$49/mo; required for full-ZIP coverage beyond deep-investigated pins)",
            "Serper API for zpid discovery (alternative to direct Zillow fetches)",
            "Daily incremental refresh job (only re-fetch listings with "
            "state changes or last-checked > 7d)",
        ],
        typical_time_horizon_days=180,
    ),

    # ─── PRE-LISTING STRUCTURING (TRIGGER-ONLY) ────────────────────────
    "pre_listing_structuring": SignalFamilySpec(
        family="pre_listing_structuring",
        description=(
            "Legal/structural moves consistent with imminent listing (indiv→LLC). "
            "TRIGGER ONLY — never a lead without corroborating human signal."
        ),
        trigger_sources=[
            "indiv_to_llc_recent",
            "title_normalization_pre_sale",
            "asset_protection_restructuring",
        ],
        support_sources=[
            "concurrent_death_signal",
            "concurrent_divorce_signal",
            "concurrent_retirement_signal",
            "concurrent_relocation_signal",
            "concurrent_financial_stress_signal",
        ],
        contradiction_sources=[
            "post_purchase_wrap",
            "internal_family_restructuring",
            "routine_asset_protection",
            "owner_type_long_term_developer",
        ],
        resolution_sources=[
            "arms_length_sale",
            "active_listing",
            "later_deed_supersedes",
        ],
        data_available_today=True,
        missing_data=[],
        typical_time_horizon_days=180,
        can_promote_to_lead=False,
    ),
}


def get_spec(family: str) -> SignalFamilySpec:
    return SIGNAL_REGISTRY[family]


def implementable_families() -> list[str]:
    """Families with enough data today to produce candidates."""
    return [f for f, spec in SIGNAL_REGISTRY.items() if spec.data_available_today]


def promotable_families() -> list[str]:
    """Families that can become leads (excludes pre_listing_structuring)."""
    return [f for f, spec in SIGNAL_REGISTRY.items() if spec.can_promote_to_lead]


if __name__ == "__main__":
    print(f"{'Family':<28} {'Data?':<6} {'Can lead?':<10} {'Horizon':<10} Description")
    print("─" * 110)
    for family, spec in SIGNAL_REGISTRY.items():
        avail = "✅" if spec.data_available_today else "❌"
        promo = "✅" if spec.can_promote_to_lead else "trigger-only"
        print(f"{family:<28} {avail:<6} {promo:<12} {spec.typical_time_horizon_days}d      {spec.description[:60]}...")
