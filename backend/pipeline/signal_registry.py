"""
SellerSignal v2 — Signal Registry.

Defines the 7 seller-signal families and the candidate-search specs for each.

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
        missing_data=["KC probate docket scraper", "death certificates"],
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
        missing_data=["historical mail-address deltas for true relocation signal"],
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
        missing_data=["KC senior exemption file", "owner age data"],
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
        data_available_today=False,
        missing_data=["KC Superior Court divorce dockets (ToS-restricted scrape)"],
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
        missing_data=["age/date-of-birth data", "LinkedIn retirement announcement scraper"],
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
        data_available_today=False,
        missing_data=[
            "KC Recorder NOD/lis pendens (ToS-restricted scrape; requires county recorder direct access or alternative legal filings feed)",
            "KC Treasurer tax delinquency file",
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
        missing_data=["WA SOS entity filings", "KC permits for renovation-complete"],
        typical_time_horizon_days=180,
    ),

    # ─── FAILED SALE ATTEMPT ──────────────────────────────────────────
    # The highest-signal category: "they tried to sell and failed, still want to"
    # Data: Zillow price-history scrape (no MLS login required — proven feasible
    # Apr 17, 2026 via web_fetch; production needs ScraperAPI/rotating residential IPs).
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
            "Production Zillow scraper (ScraperAPI / Bright Data / rotating residential IPs)",
            "Serper API for zpid discovery",
            "Daily incremental refresh job",
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
