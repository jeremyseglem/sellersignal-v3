"""
backend/services/letter_content.py — Python port of frontend/src/lib/sixLetters.js

Generates the 6-letter seller-cultivation sequence body text for a parcel.
Direct 1:1 port — same inputs (parcel + harvester matches + archetype key)
return the same letter content. The frontend module remains the source of
truth for the modal preview; this module is for backend rendering (Lob
letter creation and PDF generation).

Letters escalate over 180 days:
  Day 1   — Introduction
  Day 30  — Context / check-in
  Day 60  — Story / market info
  Day 90  — Explicit valuation offer
  Day 135 — Re-engagement
  Day 180 — Final / standing offer

Archetype dispatch (highest priority first):
  archetypeKey='probate'           → _probate_sequence (PR first name greeting)
  archetypeKey='divorce'           → _divorce_sequence (discreet, brief)
  archetypeKey='investor' OR LLC   → _investor_sequence (institutional voice)
  archetypeKey='trust' OR is_trust → _trust_sequence (trustee greeting)
  archetypeKey='estateTransition'  → _estate_transition_sequence (family voice)
  otherwise                        → long-tenure / general default

Gov / nonprofit owners return [] — we don't cultivate cities, fire
districts, churches, YMCAs etc. as sellers.
"""

import re
from typing import Any, Optional


# ── Utility functions (ported from JS) ───────────────────────────────


_ENTITY_UPPER = frozenset({
    "LLC", "INC", "CORP", "CO", "LP", "LLP", "PLLC", "PC", "NA",
    "LTD", "GMBH", "SA", "AG", "BV", "PBC",
})

_DIRECTIONS = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})

_STREET_SUFFIXES = frozenset({
    "ST", "AVE", "BLVD", "RD", "DR", "LN", "CT", "PL", "TER", "TRL",
    "HWY", "PKWY", "CIR", "WAY", "APT", "UNIT", "STE",
})


def _title_case_street(s: str) -> str:
    """Mirror titleCaseStreet from sixLetters.js. Preserves numeric tokens,
    uppercases directionals (N/S/E/W/NE/SW/etc), title-cases street types."""
    if not s:
        return ""
    parts = []
    for w in s.split():
        if not w:
            continue
        if w[0].isdigit():
            parts.append(w)
            continue
        upper = w.upper()
        if upper in _DIRECTIONS:
            parts.append(upper)
            continue
        if upper in _STREET_SUFFIXES:
            parts.append(w[0].upper() + w[1:].lower())
            continue
        parts.append(w[0].upper() + w[1:].lower())
    return " ".join(parts)


def _normalize_name(name: str) -> str:
    """Mirror normalizeName from sixLetters.js. Title-cases names but
    keeps entity tokens (LLC, INC, CORP, etc.) uppercased in their
    business context, and uppercases short tokens (≤2 chars)."""
    if not name:
        return ""
    parts = []
    for w in name.split():
        if not w:
            continue
        upper = re.sub(r"[^A-Z]", "", w.upper())
        if upper in _ENTITY_UPPER:
            parts.append(w.upper())
            continue
        if len(w) <= 2:
            parts.append(w.upper())
            continue
        parts.append(w[0].upper() + w[1:].lower())
    return " ".join(parts)


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value (mirrors JS ?? nullish coalescing)."""
    for v in values:
        if v is not None:
            return v
    return None


# ── Main entry point ─────────────────────────────────────────────────


def generate_six_letters(
    parcel: dict[str, Any],
    harvester_matches: Optional[list[dict[str, Any]]] = None,
    archetype_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return a list of 6 letter dicts in the form
        {"num": int, "name": str, "dayLabel": str, "trigger": str, "body": str}

    Returns [] for gov/nonprofit owners (we don't cultivate those).

    parcel keys read (both camelCase and snake_case supported, matching
    the JS source — Python callers typically pass snake_case):
        owner_name / ownerName
        owner_type / ownerType
        address
        city / neighborhood / marketName
        tenure_years / yearsOwned
        is_absentee / isAbsentee
        is_out_of_state / isOutOfState

    harvester_matches: list of match dicts from raw_signal_matches_v3.
        For probate, we dig out personal_representative.name_first and
        the decedent's name from all_case_parties.

    archetype_key: explicit archetype dispatch key. Auto-detection of
        LLC/trust/estate kicks in only when this is None.
    """
    if harvester_matches is None:
        harvester_matches = []

    owner_type_raw = str(_coalesce(parcel.get("ownerType"), parcel.get("owner_type"), "")).lower()

    if owner_type_raw in ("gov", "nonprofit"):
        return []

    full_name = _normalize_name(
        _coalesce(parcel.get("ownerName"), parcel.get("owner_name"), "") or ""
    ) or "Property Owner"
    first_name = full_name.split()[0] if full_name.split() else "Property Owner"

    raw_address = _coalesce(parcel.get("address"), "your property") or "your property"
    property_address = _title_case_street(re.sub(r"\s+", " ", raw_address).strip())

    neighborhood = (
        _coalesce(
            parcel.get("neighborhood"),
            parcel.get("marketName"),
            parcel.get("city"),
        )
        or "your area"
    )

    is_absentee = bool(_coalesce(parcel.get("isAbsentee"), parcel.get("is_absentee")))
    is_out_of_state = bool(_coalesce(parcel.get("isOutOfState"), parcel.get("is_out_of_state")))

    owner_name_for_regex = _coalesce(parcel.get("ownerName"), parcel.get("owner_name"), "") or ""
    is_trust = bool(
        re.search(r"trust", owner_name_for_regex, re.IGNORECASE)
        or owner_type_raw == "trust"
        or "trust" in owner_type_raw
    )
    is_llc = bool(
        re.search(
            r"\b(LLC|CORP|INC|HOLDINGS|PROPERTIES|GROUP|FOUNDATION)\b",
            owner_name_for_regex,
            re.IGNORECASE,
        )
        or owner_type_raw == "llc"
        or re.search(r"(llc|corp|inc)", owner_type_raw)
    )
    is_estate = bool(
        owner_type_raw == "estate"
        or re.search(r"\b(ESTATE|HEIRS|DECEASED|SURVIVOR)\b", owner_name_for_regex, re.IGNORECASE)
    )
    years_owned = _coalesce(parcel.get("yearsOwned"), parcel.get("tenure_years"))

    # Dig personal representative + decedent out of harvester matches
    # for probate. Mirrors the JS loop exactly.
    pr_first: Optional[str] = None
    decedent_name: Optional[str] = None
    for m in harvester_matches:
        pr = m.get("personal_representative") or {}
        if not pr_first and pr.get("name_first"):
            pr_first = pr.get("name_first")
        if not decedent_name and m.get("signal_type") == "probate":
            parties = m.get("all_case_parties") or []
            dec = next(
                (q for q in parties if q.get("role") in ("deceased", "decedent")),
                None,
            )
            if dec:
                f = dec.get("name_first") or ""
                last = dec.get("name_last") or ""
                joined = f"{f} {last}".strip()
                decedent_name = joined or None
        if pr_first and decedent_name:
            break

    # ── Dispatch ──
    if archetype_key == "probate":
        return _probate_sequence(pr_first, decedent_name, property_address, neighborhood)
    if archetype_key == "divorce":
        return _divorce_sequence(first_name, property_address, neighborhood)
    if archetype_key == "investor" or is_llc:
        return _investor_sequence(full_name, property_address, neighborhood)
    if archetype_key == "trust" or is_trust:
        return _trust_sequence(property_address, neighborhood)
    if archetype_key == "estateTransition":
        return _estate_transition_sequence(first_name, property_address, neighborhood, years_owned)

    # ── Long-tenure / general fallback ──
    greeting = (
        "To the estate of the owner"
        if is_estate
        else f"Dear {first_name}"
    )

    if is_estate:
        owner_type_context = "an estate navigating the settlement of an inherited property"
    elif is_absentee:
        owner_type_context = "an out-of-area owner who had been holding the property for years"
    elif years_owned and years_owned > 15:
        owner_type_context = "a longtime owner who had built significant equity over time"
    else:
        owner_type_context = "a homeowner who had been quietly considering their options"

    if is_out_of_state:
        distance_ack = (
            f" Even from a distance, your investment in {neighborhood} represents real value, "
            f"and you deserve to have someone watching it closely on your behalf."
        )
    elif is_absentee:
        distance_ack = (
            " Owners who don't live at their property often miss the day-to-day signals "
            "of what their home is worth — I try to fill that gap."
        )
    else:
        distance_ack = ""

    return [
        {
            "num": 1,
            "name": "The Introduction",
            "dayLabel": "Day 1",
            "trigger": "Sent immediately upon enrollment",
            "body": (
                f"{greeting},\n\n"
                f"I'm writing because I've been studying {neighborhood} for some time, and your "
                f"property at {property_address} caught my attention.\n\n"
                f"I'm not reaching out to ask for anything today. I just wanted to introduce "
                f"myself as someone who pays close attention to this market — what's selling, "
                f"what isn't, and what your property might be worth in today's environment if "
                f"you ever decided to find out.{distance_ack}\n\n"
                f"If that's a conversation you'd like to have someday, I'd welcome it. If not, "
                f"I'll continue watching the market and may write again when there's something "
                f"worth sharing about your area specifically.\n\n"
                f"Either way, thank you for letting me introduce myself.\n\n"
                f"Warmly,"
            ),
        },
        {
            "num": 2,
            "name": "The Context",
            "dayLabel": "Day 30",
            "trigger": "Sent 30 days after enrollment, or earlier if a comparable property lists",
            "body": (
                f"{greeting},\n\n"
                f"Following up on my note from last month — I wanted to share some context "
                f"about what's actually happening in {neighborhood} right now.\n\n"
                f"In the past 90 days, properties similar to yours have moved through this "
                f"market at a pace that has surprised even local agents. Homes are changing "
                f"hands at numbers that would have seemed optimistic a year ago, and the "
                f"buyer pool for {neighborhood} specifically remains deeper than supply.\n\n"
                f"For a property like yours at {property_address}, that translates to a "
                f"meaningfully different valuation conversation than even six months ago. "
                f"I'm not telling you this to push you toward anything. I'm telling you "
                f"this because if I owned a home like yours, I'd want to know.\n\n"
                f"If you'd ever like a clearer picture of where your property sits in today's "
                f"market — confidentially, no commitment — I'd be glad to put it together "
                f"for you.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 3,
            "name": "The Story",
            "dayLabel": "Day 60",
            "trigger": "Sent 60 days after enrollment, or earlier if a directly comparable sale closes nearby",
            "body": (
                f"{greeting},\n\n"
                f"A property near you sold recently. I won't name the exact address out of "
                f"respect for the seller's privacy, but the situation reminded me of yours — "
                f"{owner_type_context}, comparable in size and character to {property_address}.\n\n"
                f"The owner had been thinking about selling for over a year but had never "
                f"taken the simple step of finding out what their home was actually worth in "
                f"today's market. When they finally did, the number was higher than they "
                f"expected. The decision became a lot easier.\n\n"
                f"I share this not as a sales pitch but as a pattern I see often. Most "
                f"homeowners in {neighborhood} who eventually sell tell me afterward that "
                f"they wish they'd known their number sooner. Knowing doesn't commit you to "
                f"anything — it just makes the eventual decision, whenever it comes, a real "
                f"decision based on real information rather than a guess.\n\n"
                f"If that's something you'd like, you know where to find me.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 4,
            "name": "The Offer",
            "dayLabel": "Day 90",
            "trigger": "Sent 90 days after enrollment",
            "body": (
                f"{greeting},\n\n"
                f"I want to make this very simple.\n\n"
                f"I'd like to put together a confidential, no-obligation valuation of your "
                f"property at {property_address}. I'll do the work — recent comparable sales "
                f"on your block and in your immediate area, current market positioning, what "
                f"I'd list it for if you were my client today, and what I'd realistically "
                f"expect it to net you after closing costs.\n\n"
                f"You don't need to be considering selling. You don't need to call me back to "
                f"discuss it. I'll just put it together and send it to you, and you can do "
                f"whatever you want with it — file it away, ignore it, share it with your "
                f"accountant, or use it as a starting point for a conversation when the time "
                f"is right for you.\n\n"
                f"If you'd like me to prepare it, just call or text the number below. One "
                f"sentence is enough: \"Yes, send the valuation.\"\n\n"
                f"That's the entire ask.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5,
            "name": "The Moment",
            "dayLabel": "Day 135",
            "trigger": "Sent 135 days in, or earlier if local market data shifts meaningfully",
            "body": (
                f"{greeting},\n\n"
                f"Five months into our correspondence and I haven't heard back, which is "
                f"completely fine. Most homeowners I write to don't respond to early letters, "
                f"and I'd rather earn your eventual trust slowly than push for something "
                f"you're not ready for.\n\n"
                f"But I'm writing today because the market in {neighborhood} is in a moment "
                f"that's worth your attention.\n\n"
                f"Inventory remains tight. Qualified buyers are still actively looking — I "
                f"have several right now who would be interested in a property exactly like "
                f"yours at {property_address}. And the rate environment, while uncertain, is "
                f"creating motivation among buyers who don't want to wait any longer.\n\n"
                f"I'm not predicting anything. Markets always have moments, and the right "
                f"moment to know your property's value is usually the moment before you wish "
                f"you'd known it.\n\n"
                f"If you'd like that picture now, I can have it to you within 48 hours.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 6,
            "name": "The Conversation",
            "dayLabel": "Day 180",
            "trigger": "Final letter — sent 180 days after enrollment",
            "body": (
                f"{greeting},\n\n"
                f"This is the sixth letter I've written to you over the past six months. You "
                f"haven't responded, and I want to acknowledge that with respect rather than "
                f"persistence.\n\n"
                f"So I'm not going to ask you to call me again. I'm going to ask something "
                f"different.\n\n"
                f"Whenever the day eventually comes — six months from now, two years from "
                f"now, or ten — that you start thinking seriously about what your property "
                f"at {property_address} might be worth and what selling it would actually "
                f"look like, I'd like to be the person you call first. Not because I've "
                f"earned it through these letters, but because by then I'll have spent over "
                f"a year studying {neighborhood} closely and watching how it's evolved.\n\n"
                f"If that day comes, just save my number. That's all I'm asking.\n\n"
                f"I'll keep watching the market. I won't write again unless something material "
                f"changes that affects your property specifically.\n\n"
                f"With genuine respect,"
            ),
        },
    ]


# ── Archetype sub-sequences ──────────────────────────────────────────


def _probate_sequence(
    pr_first: Optional[str],
    decedent_name: Optional[str],
    property_address: str,
    neighborhood: str,
) -> list[dict[str, Any]]:
    greeting = f"Dear {pr_first}" if pr_first else "To the family"
    decedent_ref = f"the estate of {decedent_name}" if decedent_name else "the estate"

    return [
        {
            "num": 1, "name": "The Introduction", "dayLabel": "Day 1",
            "trigger": "Sent immediately upon enrollment — keep tone respectful, no asks",
            "body": (
                f"{greeting},\n\n"
                f"I came across the filing for {decedent_ref} and wanted to write briefly. "
                f"I'm a real estate agent who works with families navigating decisions about "
                f"a home after a loved one passes — I'm not reaching out today to discuss "
                f"anything specific, just to introduce myself.\n\n"
                f"There's no expectation here, only an offer. When you're ready to think "
                f"about what comes next for the property at {property_address} — whether "
                f"that's months from now or longer — I'd be glad to be a resource.\n\n"
                f"Until then, please accept my sincere condolences.\n\n"
                f"With respect,"
            ),
        },
        {
            "num": 2, "name": "Checking In", "dayLabel": "Day 30",
            "trigger": "Sent 30 days after introduction — light touch, still no asks",
            "body": (
                f"{greeting},\n\n"
                f"I wanted to follow up briefly on my earlier note. I imagine the past month "
                f"has been full of details — the practical kind that come with settling an "
                f"estate — and I don't want to add to that.\n\n"
                f"I'm writing only to say I'm still here, still available whenever questions "
                f"about the property come up. Many of the families I've worked with have told "
                f"me the most useful thing was just knowing they had someone they could call "
                f"when the timing felt right, with no pressure to act.\n\n"
                f"If a question arises — about valuation, market timing, or what selling "
                f"actually looks like in practice — please reach out. Otherwise, I'll write "
                f"again when there's something worth sharing.\n\n"
                f"Warm regards,"
            ),
        },
        {
            "num": 3, "name": "What to Know", "dayLabel": "Day 60",
            "trigger": "Sent 60 days in — first letter that shares any substantive information",
            "body": (
                f"{greeting},\n\n"
                f"Two months on, I wanted to share a few things that often come up around "
                f"inherited or estate-held property in {neighborhood} — not because you need "
                f"to act, but because they're useful to know.\n\n"
                f"First, the timing question is yours. Properties held through probate or "
                f"estate settlement can be sold at any pace — quickly when an estate needs "
                f"to close, or slowly when families want time. Both are normal.\n\n"
                f"Second, valuation matters more in these situations than in typical sales. "
                f"Stepped-up cost basis at the time of inheritance can meaningfully affect "
                f"tax outcomes, which is why most estate sellers I work with want a clear, "
                f"defensible number to anchor decisions.\n\n"
                f"Third, you don't need to commit to anything to get that number. I can put "
                f"together a confidential valuation of {property_address} whenever you'd "
                f"like, and you can use it however helps — share it with your attorney or "
                f"accountant, file it for later, or simply have it for context.\n\n"
                f"No rush. Just here when needed.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 4, "name": "The Quiet Offer", "dayLabel": "Day 90",
            "trigger": "Sent 90 days after enrollment — explicit but unpressured offer",
            "body": (
                f"{greeting},\n\n"
                f"It's been three months since I first wrote, and I want to make a simple "
                f"offer.\n\n"
                f"If a current valuation of {property_address} would be useful to you — for "
                f"the estate's records, for an attorney conversation, or for any reason at "
                f"all — I'd be glad to prepare one. I'll do the work: recent comparable "
                f"sales, current market context, what the property would realistically sell "
                f"for today, and what a sale would actually net once costs are accounted "
                f"for.\n\n"
                f"You don't need to be considering selling. You don't need to call me back "
                f"to discuss it. Just reply with one sentence — \"Yes, please send a "
                f"valuation\" — and I'll have it to you within a week.\n\n"
                f"That's the entire ask. I won't follow up to push anything further.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5, "name": "When the Time Comes", "dayLabel": "Day 135",
            "trigger": "Sent 135 days in — gentle re-engagement, no urgency",
            "body": (
                f"{greeting},\n\n"
                f"I haven't heard from you, which is completely understandable — there's no "
                f"right pace for these decisions.\n\n"
                f"I want to share one observation that may be useful. In my experience, "
                f"families navigating an estate's property tend to make better decisions when "
                f"they have current information than when they have to guess. The act of "
                f"getting a clear valuation often clarifies the timing question on its own — "
                f"sometimes the answer is \"sell now,\" sometimes \"hold for a year or two,\" "
                f"sometimes \"keep it in the family.\" But the right answer is rarely visible "
                f"without the data.\n\n"
                f"If that's something you'd find helpful at any point, I'm here. I won't "
                f"push, I won't follow up beyond the natural cadence of these letters, and "
                f"I'll keep the offer open as long as you need.\n\n"
                f"In the meantime, I hope the past few months have brought some peace.\n\n"
                f"With respect,"
            ),
        },
        {
            "num": 6, "name": "A Standing Offer", "dayLabel": "Day 180",
            "trigger": "Final letter — closes the formal sequence with a standing offer",
            "body": (
                f"{greeting},\n\n"
                f"This is the last of my regular letters. I won't keep writing on a schedule "
                f"— I've said what I think is useful to say, and the rest is timing.\n\n"
                f"But I want to leave you with this: my offer doesn't expire. Whenever the "
                f"moment comes that you want a clear, current picture of what the property "
                f"at {property_address} is worth — whether that's six months from now or six "
                f"years — please reach out. I'd be glad to help, and the conversation will "
                f"start the same way it would today: no pressure, no commitment, just useful "
                f"information when you're ready for it.\n\n"
                f"Until then, please know I'm thinking of your family with respect.\n\n"
                f"Whenever you need me,"
            ),
        },
    ]


def _divorce_sequence(
    first_name: str, property_address: str, neighborhood: str,
) -> list[dict[str, Any]]:
    greeting = f"Dear {first_name}"
    return [
        {
            "num": 1, "name": "The Introduction", "dayLabel": "Day 1",
            "trigger": "Sent after the 60-day wait window has cleared",
            "body": (
                f"{greeting},\n\n"
                f"I'm a real estate agent who works with homeowners in {neighborhood} on "
                f"questions related to selling, valuation, and timing.\n\n"
                f"I'm not reaching out today because I think you should sell. I'm reaching "
                f"out to introduce myself in case you'd find it useful to have someone to "
                f"call. Conversations about a property are often easier when you have an "
                f"outside perspective — and I'm happy to be that, whenever it's helpful.\n\n"
                f"If a question comes up about {property_address}, I'm available. Until "
                f"then, no expectation here.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 2, "name": "Available", "dayLabel": "Day 30",
            "trigger": "Sent 30 days after introduction — short, no asks",
            "body": (
                f"{greeting},\n\n"
                f"A brief follow-up to say I'm still here.\n\n"
                f"Decisions about a property tend to surface gradually — and there's no "
                f"right answer about timing. When a question does come up about "
                f"{property_address}, even a small one, please feel free to reach out.\n\n"
                f"Otherwise I'll be quiet. I'll write again only if there's something "
                f"specifically worth sharing.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 3, "name": "The Information", "dayLabel": "Day 60",
            "trigger": "Sent 60 days in — first letter with substantive market information",
            "body": (
                f"{greeting},\n\n"
                f"Two months on, I wanted to share some context about {neighborhood} that "
                f"you may find useful — not as pressure, just as information.\n\n"
                f"Properties similar to yours have moved at a steady pace this year. "
                f"Inventory is tight, buyers are active, and valuations have held meaningfully "
                f"higher than even twelve months ago. For a property like {property_address}, "
                f"that translates to a clearer picture of what the home would bring today "
                f"than was possible recently.\n\n"
                f"If knowing that number would be helpful — for any reason, even just for "
                f"clarity — I can put together a confidential valuation. It's the kind of "
                f"thing many homeowners find useful to have on hand whether they're actively "
                f"considering selling or not.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 4, "name": "The Offer", "dayLabel": "Day 90",
            "trigger": "Sent 90 days in — explicit valuation offer",
            "body": (
                f"{greeting},\n\n"
                f"I want to make this simple.\n\n"
                f"I can prepare a confidential, no-obligation valuation of {property_address}: "
                f"recent comparable sales, current market positioning, what the home would "
                f"likely sell for today, and what a sale would net after costs.\n\n"
                f"You don't need to be considering selling. Just reply with one sentence — "
                f"\"Yes, please send the valuation\" — and I'll have it to you within a "
                f"week. No follow-up pressure, no further outreach beyond what you ask "
                f"for.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5, "name": "A Useful Number", "dayLabel": "Day 135",
            "trigger": "Sent 135 days in — light re-engagement",
            "body": (
                f"{greeting},\n\n"
                f"I haven't heard back, which is fine — most homeowners I write to don't "
                f"respond to early letters, and I'd rather earn trust slowly than push.\n\n"
                f"I'm writing today only because, in my experience, the homeowners who "
                f"eventually sell tend to say afterward that they wish they'd known their "
                f"property's current value sooner. Not because the number itself was decisive, "
                f"but because having it made every subsequent conversation easier — with "
                f"family, with attorneys, with their own thinking.\n\n"
                f"That valuation offer remains open. One sentence is all it takes.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 6, "name": "A Standing Offer", "dayLabel": "Day 180",
            "trigger": "Final letter — closes the formal sequence",
            "body": (
                f"{greeting},\n\n"
                f"This is the last of my regular letters.\n\n"
                f"I won't keep writing on a schedule. But the offer doesn't expire — "
                f"whenever the question of {property_address} comes up, in any form, I'd "
                f"like to be the person you call. Not because of these letters, but because "
                f"by then I'll have spent over a year watching {neighborhood} closely.\n\n"
                f"Save my number. That's all I'm asking.\n\n"
                f"With respect,"
            ),
        },
    ]


def _investor_sequence(
    entity_name: str, property_address: str, neighborhood: str,
) -> list[dict[str, Any]]:
    greeting = f"To {entity_name}"
    return [
        {
            "num": 1, "name": "The Introduction", "dayLabel": "Day 1",
            "trigger": "Sent immediately upon enrollment",
            "body": (
                f"{greeting},\n\n"
                f"I'm a real estate agent who works with investor-owners in {neighborhood}, "
                f"and I wanted to introduce myself in connection with the property at "
                f"{property_address}.\n\n"
                f"I'm not writing to ask for anything today. I work with portfolios where "
                f"dispositions are evaluated against cap rate, market timing, and 1031 "
                f"considerations, and I make a point of staying available to owners who may "
                f"want to revisit their position when conditions warrant.\n\n"
                f"If a disposition window opens — now or later — I'd welcome a brief "
                f"conversation.\n\n"
                f"Regards,"
            ),
        },
        {
            "num": 2, "name": "Market Context", "dayLabel": "Day 30",
            "trigger": "Sent 30 days after introduction — substantive market data",
            "body": (
                f"{greeting},\n\n"
                f"Following up briefly with market context for {neighborhood} relevant to "
                f"the property at {property_address}.\n\n"
                f"Recent transaction activity suggests sustained buyer demand at price levels "
                f"meaningfully above prior cycle highs. Cap rates on stabilized residential "
                f"have compressed modestly; off-market trades are clearing at premiums to "
                f"listed comps in several recent cases.\n\n"
                f"For an owner evaluating disposition timing, the current environment "
                f"continues to favor sellers willing to consider off-market or pre-listing "
                f"engagement. If that's a conversation worth having, I'd be glad to share "
                f"specific recent comps relevant to your asset.\n\n"
                f"Regards,"
            ),
        },
        {
            "num": 3, "name": "Comparable Activity", "dayLabel": "Day 60",
            "trigger": "Sent 60 days in — references comparable transaction activity",
            "body": (
                f"{greeting},\n\n"
                f"A comparable property in your immediate market traded recently at terms I "
                f"think are worth flagging. Out of respect for the seller's confidentiality "
                f"I won't name the asset, but the situation is directly relevant: the owner "
                f"had held the property for several years, was not actively marketing it, "
                f"and engaged with a private buyer through an off-market introduction.\n\n"
                f"Outcome: cleared at a premium to the public listing comps, structured for "
                f"tax efficiency, closed quickly.\n\n"
                f"The pattern matters because it's repeatable. If a similar disposition path "
                f"makes sense for {property_address} — whether immediately or as a stalking-"
                f"horse conversation for later — I can put together a current valuation and "
                f"outline what an off-market engagement would look like.\n\n"
                f"Regards,"
            ),
        },
        {
            "num": 4, "name": "The Disposition Inquiry", "dayLabel": "Day 90",
            "trigger": "Sent 90 days in — explicit valuation and disposition framing",
            "body": (
                f"{greeting},\n\n"
                f"I want to make a direct offer.\n\n"
                f"I'll prepare a current valuation of {property_address} along with an off-"
                f"market disposition outline: recent comp transactions, current market "
                f"positioning, projected net proceeds, and any 1031 timing considerations "
                f"relevant to your position. Confidential, no obligation, delivered within "
                f"a week.\n\n"
                f"If a disposition is on the table this year, the analysis is genuinely "
                f"useful. If it's not, the document goes in a file and we revisit when "
                f"conditions warrant.\n\n"
                f"Reply with one line — \"Yes, send the analysis\" — and I'll start.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5, "name": "Timing Note", "dayLabel": "Day 135",
            "trigger": "Sent 135 days in — re-engagement on market timing",
            "body": (
                f"{greeting},\n\n"
                f"A short note on timing for {neighborhood}.\n\n"
                f"Inventory remains tight. Buyer pools at the price points relevant to "
                f"{property_address} continue to clear at faster cadences than 12 months "
                f"ago. The rate environment is creating a moving target, and several "
                f"investor-owners I've worked with this year have moved on dispositions "
                f"earlier than they originally planned.\n\n"
                f"If revisiting your position is worthwhile, the offer to prepare a current "
                f"valuation and disposition outline remains open.\n\n"
                f"Regards,"
            ),
        },
        {
            "num": 6, "name": "A Standing Channel", "dayLabel": "Day 180",
            "trigger": "Final letter — closes the formal sequence with a relationship offer",
            "body": (
                f"{greeting},\n\n"
                f"This closes the formal sequence.\n\n"
                f"I'll continue tracking {neighborhood} and the comparable set relevant to "
                f"{property_address}. If a meaningful market shift, a comparable transaction, "
                f"or an off-market buyer interest emerges that's specifically relevant to "
                f"your asset, I'll write again on that basis — not on a schedule.\n\n"
                f"In the meantime, the channel stays open. When timing aligns, a single "
                f"email opens it.\n\n"
                f"Regards,"
            ),
        },
    ]


def _trust_sequence(
    property_address: str, neighborhood: str,
) -> list[dict[str, Any]]:
    greeting = "To the trustees"
    return [
        {
            "num": 1, "name": "The Introduction", "dayLabel": "Day 1",
            "trigger": "Sent immediately upon enrollment",
            "body": (
                f"{greeting},\n\n"
                f"I'm a real estate agent who works with trustees and trust beneficiaries in "
                f"{neighborhood}, and I wanted to introduce myself in connection with the "
                f"property at {property_address}.\n\n"
                f"Trust-held properties often involve longer decision horizons and multiple "
                f"stakeholders, and the right time to engage a real estate professional is "
                f"often well before any decision is made. I make a point of being available "
                f"to trustees who may want a clear picture of a property's value as part of "
                f"broader trust administration — not because a sale is imminent, but because "
                f"good information makes future decisions cleaner.\n\n"
                f"If that's useful, I'm here.\n\n"
                f"With respect,"
            ),
        },
        {
            "num": 2, "name": "Trustee Context", "dayLabel": "Day 30",
            "trigger": "Sent 30 days after introduction",
            "body": (
                f"{greeting},\n\n"
                f"A brief follow-up. Many trustees I work with find that a current valuation "
                f"of trust-held real estate is useful even outside of an active sale "
                f"conversation — for trust accounting, for beneficiary distributions, for "
                f"tax planning, or simply as part of the trustee's record-keeping.\n\n"
                f"If a current valuation of {property_address} would be useful for any of "
                f"those purposes, I can prepare one confidentially and at no cost. It's the "
                f"kind of document many trustees keep on file regardless of whether sale is "
                f"being discussed.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 3, "name": "Market Context", "dayLabel": "Day 60",
            "trigger": "Sent 60 days in — substantive market context",
            "body": (
                f"{greeting},\n\n"
                f"Two months on, I wanted to share context about {neighborhood} that may be "
                f"relevant to your trust's records.\n\n"
                f"Property values in this market have held meaningfully higher than even "
                f"twelve months ago, and inventory remains constrained. For a trust-held "
                f"asset like {property_address}, the implications cut several ways — current "
                f"valuation is materially different than recent appraisals likely show; if a "
                f"future sale is contemplated as part of trust administration, current "
                f"conditions favor sellers; and even where no sale is planned, having an "
                f"accurate current number on file is good practice.\n\n"
                f"If you'd like that current valuation, I'm glad to prepare it.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 4, "name": "The Offer", "dayLabel": "Day 90",
            "trigger": "Sent 90 days in — explicit valuation offer",
            "body": (
                f"{greeting},\n\n"
                f"I want to make this concrete.\n\n"
                f"I can prepare a current, defensible valuation of {property_address} "
                f"suitable for trust records: recent comparable sales, current market "
                f"positioning, expected sale value, and notes on market conditions specific "
                f"to {neighborhood}. Confidential, no obligation, delivered within a "
                f"week.\n\n"
                f"A sale doesn't need to be on the table. Many trustees keep such valuations "
                f"in their records as standard practice. Reply with one sentence — \"Yes, "
                f"please prepare the valuation\" — and I'll begin.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5, "name": "When Decisions Arise", "dayLabel": "Day 135",
            "trigger": "Sent 135 days in — gentle re-engagement",
            "body": (
                f"{greeting},\n\n"
                f"I haven't heard back, which is appropriate — trust-held properties don't "
                f"move on outside schedules.\n\n"
                f"A note for whenever a property decision does come up. Trustees who engage "
                f"early — well before a decision is required — tend to navigate sales more "
                f"cleanly than those who engage at the moment of need. Comparable data, "
                f"market context, and a current valuation are all easier to assemble before "
                f"a decision than during one.\n\n"
                f"If that early-engagement model is useful for {property_address}, I'm glad "
                f"to begin. The same offer stands.\n\n"
                f"With respect,"
            ),
        },
        {
            "num": 6, "name": "Standing Availability", "dayLabel": "Day 180",
            "trigger": "Final letter — closes the formal sequence",
            "body": (
                f"{greeting},\n\n"
                f"This closes the formal sequence.\n\n"
                f"I'll continue tracking {neighborhood} and will reach out only if a market "
                f"development, comparable transaction, or relevant change emerges that's "
                f"specifically meaningful to {property_address}.\n\n"
                f"In the meantime, the offer remains: a current valuation, prepared "
                f"confidentially, available whenever the trust has reason for one. A single "
                f"reply opens that conversation.\n\n"
                f"With respect,"
            ),
        },
    ]


def _estate_transition_sequence(
    first_name: str,
    property_address: str,
    neighborhood: str,
    years_owned: Optional[float],
) -> list[dict[str, Any]]:
    greeting = f"Dear {first_name}"
    if years_owned and years_owned > 15:
        tenure_ref = f"your family's long history with {property_address}"
    else:
        tenure_ref = f"your family's connection to {property_address}"

    return [
        {
            "num": 1, "name": "The Introduction", "dayLabel": "Day 1",
            "trigger": "Sent immediately upon enrollment",
            "body": (
                f"{greeting},\n\n"
                f"I'm a real estate agent who works with families in {neighborhood}, and I "
                f"wanted to introduce myself.\n\n"
                f"I'm not writing because I think you should sell. I'm writing because I "
                f"noticed {tenure_ref}, and in my experience, when families are eventually "
                f"thinking through what comes next for a long-held home, they appreciate "
                f"having someone they can call — not as a salesperson, but as a resource.\n\n"
                f"If that day comes, even years from now, I'd like to be that resource.\n\n"
                f"Warmly,"
            ),
        },
        {
            "num": 2, "name": "A Quiet Follow-Up", "dayLabel": "Day 30",
            "trigger": "Sent 30 days after introduction",
            "body": (
                f"{greeting},\n\n"
                f"A brief follow-up to my note from last month.\n\n"
                f"Decisions about a long-held family home are rarely sudden — they unfold "
                f"over months or years, and the right answer depends on family conversations "
                f"as much as market conditions. I won't presume to know your family's "
                f"situation. I'm writing only to say I'm available whenever questions "
                f"surface.\n\n"
                f"If a question comes up — about {property_address}, about the market, "
                f"about the practical mechanics of selling a home eventually — please reach "
                f"out.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 3, "name": "Useful to Know", "dayLabel": "Day 60",
            "trigger": "Sent 60 days in — first letter with substantive content",
            "body": (
                f"{greeting},\n\n"
                f"Two months on, a few things often come up around long-held family homes "
                f"that may be useful to know — not because you need to act, but because "
                f"they're easier to learn now than later.\n\n"
                f"First, valuations of long-held homes tend to surprise families. Properties "
                f"held for many years frequently appraise at multiples of purchase price, "
                f"and the equity picture is rarely accurate without a current number.\n\n"
                f"Second, tax considerations matter more for long-held homes than typical "
                f"sales — capital gains exposure, step-up basis questions if the home has "
                f"passed through generations, and sometimes 1031 strategies all come into "
                f"play.\n\n"
                f"Third, none of this requires you to be considering a sale. A current "
                f"valuation of {property_address}, prepared confidentially, is something "
                f"many families keep on hand for planning purposes regardless of timing.\n\n"
                f"If that's useful, I'm glad to prepare it.\n\n"
                f"Best,"
            ),
        },
        {
            "num": 4, "name": "The Offer", "dayLabel": "Day 90",
            "trigger": "Sent 90 days in — explicit valuation offer",
            "body": (
                f"{greeting},\n\n"
                f"I'd like to make a simple offer.\n\n"
                f"I can prepare a confidential, no-obligation current valuation of "
                f"{property_address}: recent comparable sales, current market positioning, "
                f"what the home would realistically sell for today, and what a sale would "
                f"net after costs.\n\n"
                f"You don't need to be considering selling. Many families I work with use "
                f"these valuations for estate planning, family conversations, or simply for "
                f"clarity. Reply with one sentence — \"Yes, please send the valuation\" — "
                f"and I'll have it to you within a week.\n\n"
                f"Sincerely,"
            ),
        },
        {
            "num": 5, "name": "A Family Question", "dayLabel": "Day 135",
            "trigger": "Sent 135 days in — gentle re-engagement",
            "body": (
                f"{greeting},\n\n"
                f"I haven't heard back, which is fine — these are family decisions, and "
                f"they don't run on outside schedules.\n\n"
                f"I'm writing today only to share an observation. The families I've worked "
                f"with who eventually sold a long-held home almost universally said "
                f"afterward that they wished they'd had a current valuation earlier — not "
                f"because the number itself drove the decision, but because it grounded "
                f"every subsequent family conversation in real information instead of "
                f"guesses.\n\n"
                f"That offer remains open for {property_address}. A single reply is all it "
                f"takes.\n\n"
                f"With respect,"
            ),
        },
        {
            "num": 6, "name": "Whenever the Day Comes", "dayLabel": "Day 180",
            "trigger": "Final letter — closes the formal sequence",
            "body": (
                f"{greeting},\n\n"
                f"This is the last of my regular letters.\n\n"
                f"If the day eventually comes that your family begins thinking seriously "
                f"about {property_address} — six months from now, two years, or longer — "
                f"I'd like to be the person you call first. Not because of these letters, "
                f"but because by then I'll have spent over a year watching {neighborhood} "
                f"closely.\n\n"
                f"Save my number. That's all I'm asking.\n\n"
                f"With genuine respect,"
            ),
        },
    ]
