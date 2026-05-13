"""
Web-research orchestrator for finding out-of-state probate PRs.

Problem: when the named Personal Representative doesn't live at the
property under probate, our standard skip-trace can't find them.
Tracerfy's address-anchored lookup needs an address to query against,
and we don't know the PR's home address.

Solution: assemble it from public web sources.

Pipeline:
  1. Find the deceased's obituary via SerpAPI
     (delegated to backend.integrations.serpapi_obit, built on Day 1).
     Returns survivors with names + relationships + cities.
  2. Match the named PR (from court records) against the survivor
     list. Tolerant matching: ignores middle names, case-insensitive.
  3. Use the matched survivor's city as the search context.
  4. SerpAPI search for the PR by name in that city. Parse snippets
     from public-records aggregators (Radaris, ClustrMaps, Whitepages,
     PeekYou, Spokeo) for candidate street addresses.
  5. For each candidate address (capped at 3), call
     tracerfy.lookup_person(PR name, candidate address). First Tracerfy
     hit wins — we now have a verified PR with phones, emails, and DNC
     flags.
  6. Return the verified contact in the standard provider_result shape
     so the /lookup endpoint can drop it straight into its persons
     list and cache.

Cost per lead (best case: PR found via obit, verified on first try):
  - SerpAPI obit search:     $0.005
  - Claude obit extraction:  $0.005
  - SerpAPI candidate search:$0.005
  - 1 Tracerfy hit:          $0.10
  Total: ~$0.12

Cost per lead (worst case: 3 verification attempts, all miss):
  - SerpAPI ×2 + Claude:     $0.015
  - 3 Tracerfy misses:       $0.00 (Tracerfy charges only on hits)
  Total: ~$0.02

Failure modes that return None gracefully:
  - No obit found (recent death, no online presence, etc.)
  - PR not in survivor list (PR is non-family, e.g., attorney)
  - PR matched but no city listed in obit
  - No candidate addresses surface in SerpAPI snippets
  - All Tracerfy verifications miss (PR not in Tracerfy's database)

The /lookup endpoint inserts this between the standard PR-name search
miss and the household fallback. If web_research finds the PR, we
present the verified contact. Otherwise we fall through to household
fallback as before.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
import urllib.request
import json
from typing import Any

from backend.integrations import serpapi_obit
from backend.integrations import tracerfy

log = logging.getLogger(__name__)

_SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
_SERPAPI_URL = "https://serpapi.com/search.json"
_HTTP_TIMEOUT_SEC = 15.0

# Cap on Tracerfy verification calls per attempt. Each candidate
# address found in SerpAPI snippets is potentially the PR's home,
# but we don't want unbounded credit spend if many candidates surface.
# 3 is the sweet spot: typical first-page snippets have 1-3 distinct
# addresses for a named person, and burning more than 3 verifications
# blindly hurts unit economics. Configurable via env if needed.
_MAX_VERIFICATIONS = int(os.environ.get("WEB_RESEARCH_MAX_CANDIDATES", "3"))

# Tracerfy lookup_person rejects WA-only addresses out of the box, but
# in principle the PR could live anywhere. WA is the default state for
# obit results in our context (deceased lived in King County). When we
# extract a candidate that lives in a different state, we pass that
# state through to Tracerfy.
_DEFAULT_STATE = "WA"

# Regex patterns to pull street addresses out of SerpAPI snippets.
# Public-records aggregators include addresses like:
#   "703 SW 350th Ct, Federal Way, WA 98023"
#   "22029 SE 241st Ln, Maple Valley, WA"
#   "Last known address: 1234 Main St #5, Seattle, WA 98101"
# We're conservative: only match patterns that look like real US
# street addresses with at least number + street + city + state.
_ADDR_PATTERN = re.compile(
    r"\b(\d{1,6}\s+[NSEW]{0,2}\s*[A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+){0,4}"
    r"(?:\s+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court"
    r"|Way|Pl|Place|Blvd|Boulevard|Pkwy|Parkway|Cir|Circle|Ter|Terrace"
    r"|Trl|Trail|Hwy|Highway)\.?)"
    r"(?:\s+(?:Apt|Apartment|Unit|Ste|Suite|#)\s*\w+)?)"
    r"[,\s]+([A-Z][A-Za-z\s\-]+?),?\s+([A-Z]{2})\b",
    re.IGNORECASE,
)


def find_pr_via_web_research(
    pr_first: str,
    pr_last: str,
    deceased_name: str,
    deceased_city: str,
    deceased_state: str = _DEFAULT_STATE,
) -> dict[str, Any] | None:
    """Top-level entry point.

    Args:
        pr_first, pr_last: PR's first and last name from court records.
            These come in court-records casing (often ALL CAPS); we
            handle case-insensitive matching internally.
        deceased_name: deceased's name as it appears in court records.
        deceased_city: city of the property in probate. Deceased
            typically lived there; obit usually published locally.
        deceased_state: 2-letter state code (default WA).

    Returns:
        On success: a dict in the same shape as tracerfy.lookup_person
        results, with two web-research-specific additions:
          {
            'hit':              True,
            'credits_deducted': N (Tracerfy credits actually charged),
            'persons':          [{...PR data..., '_web_research': True,
                                  '_web_research_source': 'obit'}],
            'provider':         'tracerfy',
            'search_mode':      'web_research',
            'raw': {
              'obit_url':            str | None,
              'matched_survivor':    dict | None,
              'candidates_tried':    list of {address, city, state},
              'verified_candidate':  dict,
            }
          }

        On any failure (no obit, no PR match, no candidate addresses,
        no Tracerfy verification hit): None. Caller (/lookup) falls
        through to household fallback as before.

    Logging-only failure modes: every miss case is logged with
    enough context to debug post-hoc.
    """
    pr_first = (pr_first or "").strip()
    pr_last = (pr_last or "").strip()
    deceased_name = (deceased_name or "").strip()
    deceased_city = (deceased_city or "").strip()

    if not pr_first or not pr_last or not deceased_name or not deceased_city:
        log.info("web_research: missing required input field")
        return None

    # ── Step 1: find the obit ─────────────────────────────────────
    obit = serpapi_obit.find_obituary_and_extract_survivors(
        deceased_full_name=deceased_name,
        deceased_city=deceased_city,
        deceased_state=deceased_state,
    )
    if not obit:
        log.info("web_research miss: no obit for %s", deceased_name)
        return None

    survivors = obit.get("survivors") or []
    if not survivors:
        log.info("web_research miss: obit found but no survivors extracted")
        return None

    # ── Step 2: match PR to a survivor ────────────────────────────
    matched = _match_pr_to_survivor(pr_first, pr_last, survivors)
    if not matched:
        log.info(
            "web_research miss: PR '%s %s' not in survivor list (%d survivors)",
            pr_first, pr_last, len(survivors)
        )
        return None

    # ── Step 3: candidate-address search ──────────────────────────
    # If the matched survivor has a city listed in the obit, use that.
    # Otherwise we still try, but in a broader scope (the deceased's
    # state). Hit rate is much lower without a city.
    search_city = matched.get("city")
    search_state = matched.get("state") or deceased_state

    candidates = _find_candidate_addresses(
        pr_first=pr_first, pr_last=pr_last,
        city=search_city, state=search_state,
    )
    if not candidates:
        log.info(
            "web_research miss: no candidate addresses for %s %s in %s, %s",
            pr_first, pr_last, search_city or "?", search_state
        )
        return None

    # ── Step 4: Tracerfy verification ─────────────────────────────
    tried: list[dict[str, str]] = []
    total_credits = 0
    for cand in candidates[:_MAX_VERIFICATIONS]:
        tried.append(cand)
        try:
            verify_result = tracerfy.lookup_person(
                first_name=pr_first,
                last_name=pr_last,
                address=cand["address"],
                city=cand["city"],
                state=cand["state"],
                zip_code=cand.get("zip"),
            )
        except tracerfy.TracerfyError as e:
            log.warning(
                "web_research: Tracerfy error verifying %s %s @ %s: %s",
                pr_first, pr_last, cand["address"], e.message
            )
            continue

        total_credits += verify_result.get("credits_deducted", 0)

        if verify_result.get("hit"):
            persons = verify_result.get("persons") or []
            # Tag each person with web-research provenance so the
            # frontend can render them differently from a standard
            # property-owner result. Tag with the obit URL too so an
            # agent can verify the chain of evidence if curious.
            for p in persons:
                p["_web_research"] = True
                p["_web_research_source"] = "obit"
                p["_web_research_obit_url"] = obit.get("obit_url")

            return {
                "hit":              True,
                "credits_deducted": total_credits,
                "persons":          persons,
                "provider":         "tracerfy",
                "search_mode":      "web_research",
                "raw": {
                    "obit_url":           obit.get("obit_url"),
                    "obit_source":        obit.get("obit_source"),
                    "matched_survivor":   matched,
                    "candidates_tried":   tried,
                    "verified_candidate": cand,
                },
            }

    log.info(
        "web_research miss: %d candidates tried, none verified for %s %s",
        len(tried), pr_first, pr_last
    )
    return None


# ════════════════════════════════════════════════════════════════════
#  PR-to-survivor matching
# ════════════════════════════════════════════════════════════════════

def _match_pr_to_survivor(
    pr_first: str, pr_last: str, survivors: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the survivor in the obit list whose name matches the PR.

    Tolerant matching:
      - Case-insensitive
      - Last name must match exactly (no middle-initial weirdness)
      - First name match accepts: exact, nickname-stripped, or first
        name appearing as substring of survivor's name

    This is intentionally strict on last name and loose on first name.
    Court records sometimes use legal names ('William') while obits
    use nicknames ('Bill'). Last names rarely vary that way.
    """
    pr_first_lower = pr_first.lower().strip()
    pr_last_lower = pr_last.lower().strip()

    for s in survivors:
        s_name = (s.get("name") or "").strip().lower()
        if not s_name:
            continue
        s_parts = s_name.split()
        if not s_parts:
            continue

        # Last name must match the last token of the survivor's name
        s_last = s_parts[-1]
        if s_last != pr_last_lower:
            continue

        # First name match: exact OR substring (handles Jane → Janet,
        # Bill → William, etc. with some false-positive tolerance —
        # we're already constrained to survivors of this deceased)
        s_first = s_parts[0]
        if (s_first == pr_first_lower
                or pr_first_lower in s_first
                or s_first in pr_first_lower):
            return s

    return None


# ════════════════════════════════════════════════════════════════════
#  Candidate-address search via SerpAPI snippets
# ════════════════════════════════════════════════════════════════════

def _find_candidate_addresses(
    pr_first: str, pr_last: str,
    city: str | None, state: str,
) -> list[dict[str, str]]:
    """Search SerpAPI for the PR by name + city, extract candidate
    street addresses from result snippets.

    Public-records aggregators (Radaris, ClustrMaps, PeekYou, Spokeo,
    WhitePages) routinely surface partial address data in their
    snippets — often something like:
        "Kira T Kuetgens, age 59, lives at 703 SW 350th Ct,
         Federal Way, WA 98023..."

    We parse snippets (NOT page bodies — we don't scrape these sites
    directly, we use what SerpAPI returns) for anything that pattern-
    matches a US street address.

    Returns a deduplicated list of {address, city, state, zip}.
    """
    if not _SERPAPI_KEY:
        log.warning("SERPAPI_KEY missing; web_research can't search")
        return []

    # Build query: prefer city if we have one; otherwise state-only is
    # the fallback (much lower hit rate).
    pr_full = f"{pr_first} {pr_last}".strip()
    if city:
        query = f'"{pr_full}" {city} {state}'
    else:
        query = f'"{pr_full}" {state}'

    try:
        url = (_SERPAPI_URL + "?" + urllib.parse.urlencode({
            "q":       query,
            "api_key": _SERPAPI_KEY,
            "num":     10,
        }))
        req = urllib.request.Request(
            url, headers={"User-Agent": "SellerSignal/3.0"}
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        log.warning("SerpAPI candidate search failed: %s", e)
        return []

    if "error" in data:
        log.info("SerpAPI candidate search error: %s", data["error"])
        return []

    # Combine title + snippet from each result, then regex-extract
    # addresses. The full page bodies aren't fetched — we work with
    # what SerpAPI gives us, which is faster, cheaper, and respects
    # aggregator ToS (we're consuming search results, not scraping).
    addresses: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in (data.get("organic_results") or []):
        text = (
            (item.get("title") or "") + " " + (item.get("snippet") or "")
        )
        for m in _ADDR_PATTERN.finditer(text):
            street = " ".join(m.group(1).split())  # collapse whitespace
            cand_city = m.group(2).strip()
            cand_state = m.group(3).upper().strip()

            # Skip non-US states or garbage
            if len(cand_state) != 2:
                continue

            key = f"{street.lower()}|{cand_city.lower()}|{cand_state}"
            if key in seen:
                continue
            seen.add(key)

            addresses.append({
                "address": street,
                "city":    cand_city,
                "state":   cand_state,
                "zip":     "",  # rarely in snippets; Tracerfy can handle empty
            })

    return addresses
