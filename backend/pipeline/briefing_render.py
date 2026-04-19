"""
SellerSignal v2 — Briefing Render.

Renders the final briefing from confirmed leads.
NO fixed mix. NO category quotas. The output IS what survived review.

Also renders the full audit trail: what was searched, what was rejected, why.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime

from backend.pipeline.schema import Lead, CandidateReview, lead_to_dict, review_to_dict
from collections import defaultdict as _dd


def group_absentee_oos_by_owner(leads: list[Lead]) -> list[Lead]:
    """
    When the same absentee-OOS owner appears on multiple parcels, collapse
    into a single lead covering all of them. Multi-parcel holding is stronger
    signal than single-parcel.

    The merged lead:
      - Uses the highest-value parcel as the primary address
      - Aggregates total value across parcels
      - Upgrades confidence (3+ parcels = medium, was low)
      - Rewrites narrative to reflect the portfolio
    """
    by_owner: dict[str, list[Lead]] = _dd(list)
    other: list[Lead] = []
    for ld in leads:
        if ld.signal_family == "absentee_oos_disposition":
            by_owner[ld.current_owner].append(ld)
        else:
            other.append(ld)

    merged: list[Lead] = []
    for owner, parcels in by_owner.items():
        if len(parcels) == 1:
            merged.append(parcels[0])
            continue

        parcels.sort(key=lambda p: -(p.value or 0))
        primary = parcels[0]
        total_value = sum((p.value or 0) for p in parcels)
        addresses = [p.address for p in parcels]

        # Upgrade confidence by portfolio concentration
        new_conf = "medium" if len(parcels) >= 3 else primary.confidence
        if len(parcels) >= 5:
            new_conf = "high"

        primary.confidence = new_conf
        primary.value = total_value
        primary.situation = (
            f"Owner: {owner}. Cross-parcel concentration: holds "
            f"{len(parcels)} 98004 residential properties totaling ${total_value:,}, "
            f"all with same out-of-state mailing address. Concentrated absentee "
            f"holding is a much stronger disposition signal than single-parcel OOS. "
            f"Properties: {', '.join(addresses)}."
        )
        primary.approach = (
            f"Address the owner as a portfolio-level conversation, not a per-parcel "
            f"pitch. Offer a consolidated market view across all {len(parcels)} "
            f"holdings. A sophisticated OOS holder is thinking in terms of portfolio "
            f"optimization — meet them there."
        )
        merged.append(primary)

    return sorted(other + merged, key=lambda ld: (
        {"act_this_week": 0, "active_window": 1, "long_horizon": 2}[ld.lead_tier],
        {"high": 0, "medium": 1, "low": 2}[ld.confidence],
        -(ld.value or 0),
    ))


def render_briefing_markdown(
    leads: list[Lead],
    reviews: list[CandidateReview],
    zip_code: str,
    signals_harvested: dict[str, int],
) -> str:
    """
    Produce the briefing markdown.

    leads: confirmed leads to show
    reviews: all candidate reviews (for funnel/audit)
    signals_harvested: {family: count_of_raw_signals_searched}
    """
    lines: list[str] = []
    lines.append(f"# SellerSignal v2 Briefing — ZIP {zip_code}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Architecture:** signal-first (v2)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ─── FUNNEL ────────────────────────────────────────────────────────
    status_counts = Counter(r.candidate_status for r in reviews)
    family_counts = Counter(r.signal_family for r in reviews)

    lines.append("## Funnel")
    lines.append("")
    lines.append("| Stage | Count |")
    lines.append("|---|---|")
    total_signals = sum(signals_harvested.values())
    lines.append(f"| Signals harvested across all families | {total_signals} |")
    lines.append(f"| Candidates generated | {len(reviews)} |")
    lines.append(f"| Confirmed | {status_counts.get('confirmed', 0)} |")
    lines.append(f"| Weak | {status_counts.get('weak', 0)} |")
    lines.append(f"| Rejected | {status_counts.get('rejected', 0)} |")
    lines.append(f"| **Leads shipped** | **{len(leads)}** |")
    lines.append("")

    lines.append("### Signal harvest by family")
    lines.append("")
    lines.append("| Family | Raw signals | Candidates | Confirmed |")
    lines.append("|---|---|---|---|")
    for family in signals_harvested:
        cand_count = family_counts.get(family, 0)
        conf_count = sum(1 for r in reviews
                         if r.signal_family == family and r.candidate_status == "confirmed")
        lines.append(f"| {family} | {signals_harvested[family]} | {cand_count} | {conf_count} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ─── LEADS BY TIER ─────────────────────────────────────────────────
    if not leads:
        lines.append("## No leads shipped today")
        lines.append("")
        lines.append("This is a legitimate outcome. No candidates survived review.")
        lines.append("See audit trail below for rejection reasons.")
        lines.append("")
    else:
        # Split act_this_week into URGENT (forced sellers) and OPPORTUNITY (motivated sellers).
        # financial_stress = forced (foreclosure, trustee sale, lis pendens)
        # failed_sale_attempt = motivated but not forced
        FORCED_FAMILIES = {"financial_stress"}

        def is_forced(ld):
            return ld.signal_family in FORCED_FAMILIES

        sections = [
            ("act_this_week_urgent", "🔴 URGENT · FORCED SELLERS",
             lambda l: l.lead_tier == "act_this_week" and is_forced(l)),
            ("act_this_week_opp", "🟠 OPPORTUNITY · MOTIVATED SELLERS",
             lambda l: l.lead_tier == "act_this_week" and not is_forced(l)),
            ("active_window", "🟡 ACTIVE WINDOW",
             lambda l: l.lead_tier == "active_window"),
            ("long_horizon", "🟢 LONG HORIZON · WATCHLIST",
             lambda l: l.lead_tier == "long_horizon"),
        ]

        for _, title, selector in sections:
            tier_leads = [l for l in leads if selector(l)]
            if not tier_leads:
                continue
            lines.append(f"## {title} ({len(tier_leads)})")
            lines.append("")
            for i, ld in enumerate(tier_leads, 1):
                conf_icon = {"high": "🟢", "medium": "🟡", "low": "⚪"}[ld.confidence]
                lines.append(f"### {conf_icon} Lead · {ld.address}")
                lines.append("")
                lines.append(f"- **Signal family:** `{ld.signal_family}`")
                lines.append(f"- **Owner:** {ld.current_owner}")
                lines.append(f"- **Assessed value:** ${ld.value or 0:,}")
                lines.append(f"- **Parcel ID:** {ld.parcel_id}")
                lines.append(f"- **Confidence:** {ld.confidence}")
                lines.append(f"- **Why now:** {ld.why_now}")
                lines.append(f"- **Situation:** {ld.situation}")
                lines.append(f"- **Approach:** {ld.approach}")
                lines.append(f"- **Channel:** {ld.recommended_channel} · **Window:** {ld.timing_window_days} days")
                lines.append("")
                lines.append("**Supporting evidence:**")
                for e in ld.supporting_evidence:
                    lines.append(f"  - `[{e.role}]` {e.description} — *{e.source}*")
                if ld.contradicting_evidence:
                    lines.append("")
                    lines.append("**Contradicting evidence (noted but not fatal):**")
                    for e in ld.contradicting_evidence:
                        lines.append(f"  - `[{e.role}]` {e.description} — *{e.source}*")
                lines.append("")
                lines.append("---")
                lines.append("")

    # ─── REJECTED — top reasons ────────────────────────────────────────
    rejected = [r for r in reviews if r.candidate_status == "rejected"]
    if rejected:
        lines.append("## Rejection audit (top reasons)")
        lines.append("")
        rej_reasons = Counter(r.reason[:80] for r in rejected)
        lines.append("| Count | Reason |")
        lines.append("|---|---|")
        for reason, count in rej_reasons.most_common(10):
            lines.append(f"| {count} | {reason} |")
        lines.append("")

    # ─── WEAK — kept for review but not promoted ───────────────────────
    weak = [r for r in reviews if r.candidate_status == "weak"]
    if weak:
        lines.append(f"## Weak candidates ({len(weak)}) — logged, not shipped")
        lines.append("")
        lines.append("These had triggers but insufficient support or structural blockers. "
                     "Not promoted to leads, but preserved in audit trail.")
        lines.append("")
        # Show top 10
        for r in weak[:10]:
            lines.append(f"- **{r.address}** · `{r.signal_family}` · {r.owner_name}")
            lines.append(f"  - Reason: {r.reason}")
        if len(weak) > 10:
            lines.append(f"- …and {len(weak)-10} more (see audit JSON)")
        lines.append("")

    # ─── DATA GAPS ─────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## What this briefing did NOT search")
    lines.append("")
    lines.append("These signal families have no working data source today. "
                 "Adding any of them multiplies the lead count; they don't require "
                 "changes to the review architecture.")
    lines.append("")
    lines.append("| Family | Data required |")
    lines.append("|---|---|")
    lines.append("| divorce_unwinding | KC Superior Court divorce dockets |")
    lines.append("| relocation_executive | Historical mail-address deltas / LinkedIn job-change scraper |")
    lines.append("| financial_stress | KC NOD / lis pendens / trustee-sale / tax-delinquency feeds |")
    lines.append("")

    # ─── BOTTOM LINE ───────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Architectural principle, restated")
    lines.append("")
    lines.append("> The signal defines the search.")
    lines.append("> The data confirms or rejects it.")
    lines.append("> The lead only exists if it survives that test.")
    lines.append("")

    return "\n".join(lines)


def render_briefing_manifest(
    leads: list[Lead],
    reviews: list[CandidateReview],
    zip_code: str,
    signals_harvested: dict[str, int],
) -> dict:
    """
    Structured output for audit and machine consumption.
    """
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "zip": zip_code,
        "architecture": "signals_first_v2",
        "signals_harvested": signals_harvested,
        "funnel": {
            "candidates_total": len(reviews),
            "confirmed": sum(1 for r in reviews if r.candidate_status == "confirmed"),
            "weak": sum(1 for r in reviews if r.candidate_status == "weak"),
            "rejected": sum(1 for r in reviews if r.candidate_status == "rejected"),
            "leads_shipped": len(leads),
        },
        "leads": [lead_to_dict(l) for l in leads],
        "all_reviews": [review_to_dict(r) for r in reviews],
    }
