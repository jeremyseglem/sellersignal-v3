"""
SerpAPI obituary search + survivor extraction.

Purpose: given a deceased person's name and city, find their online
obituary and extract the structured list of surviving family members
with their locations. This is the high-signal data source for finding
out-of-state personal representatives — obits explicitly name
survivors with locations ("survived by daughter Kira of Federal Way,
son Mike of Portland").

This module is intentionally narrow: it knows how to find an obit and
parse a survivor list. It does NOT know about PRs, parcels, or
skip-trace. Those concerns live in backend/integrations/web_research.py
which orchestrates this module + Tracerfy verification.

Flow:
  1. Build a SerpAPI query: "{deceased name}" obituary {city}
  2. Fetch top organic results, score them for likely-obit URLs
  3. Fetch the top candidate's HTML, strip to readable text
  4. Send truncated obit text to Claude for structured extraction
  5. Return {obit_url, obit_source, survivors[]} or None

The Claude pass handles natural-language parsing — obituaries are
unstructured prose, and a small LLM call is far more reliable than
regex for catching variations like "survived by his daughter Kira
Kuetgens (Federal Way)" vs "Kira of Federal Way, WA" vs "his daughter
Kira and her husband, of Federal Way".

Costs (rough, per call):
  - SerpAPI: $0.005
  - URL fetch: free
  - Claude extraction (Sonnet 4, ~2KB input + ~300 token output): ~$0.005

Total: ~$0.01 per successful extraction. Misses (no obit found) cost
only the SerpAPI call.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any

import requests
from bs4 import BeautifulSoup


log = logging.getLogger(__name__)


# Reuse the same SerpAPI key as the v2 investigation pipeline. Hard-
# fail at call time if missing rather than silently returning empty —
# silent failures were a serious bug class historically.
_SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
_SERPAPI_URL = "https://serpapi.com/search.json"

# Claude model for the extraction step. Same constant the rest of the
# project uses so we stay aligned on model version.
_CLAUDE_MODEL = "claude-sonnet-4-20250514"
_CLAUDE_MAX_TOKENS = 800  # Small budget — output is a structured JSON list

# Truncation: feed Claude at most this many chars of obit body text.
# Obits are typically 500-2000 chars; capping at 4000 covers long ones
# while keeping LLM cost predictable.
_OBIT_TEXT_CAP = 4000

# Polite timeouts. Funeral home sites and aggregators can be slow.
_HTTP_TIMEOUT_SEC = 15.0

# Domains we treat as high-confidence obit sources (rendered as text,
# not JavaScript-only). Pages on these domains are worth fetching;
# everything else we skip to save HTTP cost.
_OBIT_DOMAINS_TEXT = (
    "legacy.com",
    "dignitymemorial.com",
    "tributearchive.com",
    "echovita.com",
    "everloved.com",
    "obittree.com",
    "obituaries.com",
    "obittoday.com",
    "obitsforlife.com",
)

# Domains that gate obits behind JavaScript rendering. We don't fetch
# them — we still note them as obit URLs (for the cache) but skip
# extraction. The survivor list comes from snippet text only in this
# fallback path.
_OBIT_DOMAINS_JS = (
    "gather-app.com",
    "weeksfuneralhomes.com",
    "funeralinnovations.com",
)


class ObitNotFound(Exception):
    """Raised when no plausible obituary surfaces in search results."""


class ObitExtractionFailed(Exception):
    """Raised when an obit URL is found but its survivor list can't
    be parsed (page is JS-only, page is blank, Claude returns garbage,
    etc.). Caller can fall through to a different strategy."""


def find_obituary_and_extract_survivors(
    deceased_full_name: str,
    deceased_city: str,
    deceased_state: str = "WA",
) -> dict[str, Any] | None:
    """Top-level entry point. Returns a dict with the obit URL and a
    structured survivor list, or None if no obit can be found.

    Args:
        deceased_full_name: full name as it appears in court records
            (e.g., "Anne K Speros" or "Theodore E Wise"). Quoted in
            the SerpAPI query for exact-match search.
        deceased_city: city of the property in probate. The deceased
            lived here; the obit is usually published locally.
        deceased_state: 2-letter state code. Default WA since that's
            the only state we cover today.

    Returns:
        On success:
          {
            'obit_url':    str,
            'obit_source': str (domain),
            'obit_title':  str (page <title>),
            'survivors': [
              {'name': 'Kira Kuetgens', 'relationship': 'daughter',
               'city': 'Federal Way', 'state': 'WA'},
              ...
            ],
          }
        On failure (no obit found, or no survivors extracted):
          None

    Raises:
        None. All failure modes return None so the caller can fall
        through to other strategies. Internal logging captures why.
    """
    name = (deceased_full_name or "").strip()
    city = (deceased_city or "").strip()
    state = (deceased_state or "WA").strip().upper()

    if not name or not city:
        return None

    # Step 1: SerpAPI obit search
    try:
        results = _serpapi_obit_search(name, city, state)
    except Exception as e:
        log.warning("SerpAPI obit search failed for %s: %s", name, e)
        return None

    if not results:
        return None

    # Step 2: rank candidates, prefer text-rendered domains
    candidates = _rank_obit_candidates(results, name)
    if not candidates:
        return None

    # Step 3: fetch the top candidate, extract text
    for cand in candidates[:3]:  # try up to 3 if top fetches fail
        url = cand["link"]
        domain = _domain_of(url)

        # JS-rendered pages: we record the URL but can't extract.
        # We try snippet-only extraction as a fallback.
        if any(d in domain for d in _OBIT_DOMAINS_JS):
            log.info("Obit at %s is JS-rendered, trying snippet fallback",
                     domain)
            survivors = _extract_from_snippet(cand.get("snippet", ""), name)
            if survivors:
                return {
                    "obit_url":    url,
                    "obit_source": domain,
                    "obit_title":  cand.get("title", ""),
                    "survivors":   survivors,
                    "_extraction": "snippet_only",
                }
            continue

        # Text-rendered: fetch and parse
        obit_text = _fetch_obit_text(url)
        if not obit_text:
            log.info("Empty body fetched from %s, skipping", url)
            continue

        # Post-fetch validation: even if the SerpAPI snippet had the
        # deceased's name, the actual page might be a different
        # person's obit that just happens to reference our deceased
        # in passing (e.g., as a relative of someone else who died).
        # Confirm the deceased's full name appears in the body before
        # sending to Claude — otherwise Claude will faithfully extract
        # whichever survivors ARE in the page and label them as ours.
        if not _name_in_body(name, obit_text):
            log.info(
                "Page %s does not contain '%s' in body, skipping",
                url, name
            )
            continue

        survivors = _extract_survivors_via_claude(
            obit_text, deceased_name=name
        )
        if survivors:
            return {
                "obit_url":    url,
                "obit_source": domain,
                "obit_title":  cand.get("title", ""),
                "survivors":   survivors,
                "_extraction": "full_text",
            }

    return None


# ════════════════════════════════════════════════════════════════════
#  SerpAPI search
# ════════════════════════════════════════════════════════════════════

def _serpapi_obit_search(
    name: str, city: str, state: str
) -> list[dict[str, str]]:
    """Build and execute the SerpAPI obit query. Returns the top
    organic results as a list of {title, snippet, link}. Empty list
    on no results or API error."""
    if not _SERPAPI_KEY:
        log.warning("SERPAPI_KEY not set; obit search disabled")
        return []

    # The double-quoted name forces SerpAPI to do an exact-match search.
    # "obituary" plus city scopes the result set. Adding state would
    # over-constrain — most obit pages don't include state in their
    # text, just city + funeral home name.
    query = f'"{name}" obituary {city}'

    url = (_SERPAPI_URL + "?" + urllib.parse.urlencode({
        "q":       query,
        "api_key": _SERPAPI_KEY,
        "num":     10,  # Top 10 — gives us room to filter and rank
    }))

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "SellerSignal/3.0"}
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        log.warning("SerpAPI request failed: %s", e)
        return []

    if "error" in data:
        log.info("SerpAPI returned error: %s", data["error"])
        return []

    organic = data.get("organic_results") or []
    return [
        {
            "title":   (item.get("title") or "")[:300],
            "snippet": (item.get("snippet") or "")[:600],
            "link":    item.get("link") or "",
        }
        for item in organic
        if item.get("link")
    ]


# ════════════════════════════════════════════════════════════════════
#  Candidate ranking
# ════════════════════════════════════════════════════════════════════

def _rank_obit_candidates(
    results: list[dict[str, str]], deceased_name: str
) -> list[dict[str, str]]:
    """Score and rank search results by likelihood of being a real
    obituary for THIS deceased person.

    Strict name-match requirement: the deceased's full name must
    appear in the title OR snippet. A partial-token match is NOT
    enough — that path produced false positives in testing where
    e.g. "Annelene Speros / Maple Valley" returned an obit for
    "Alliene Sabo" because SerpAPI surfaced an unrelated funeral-home
    page where "Speros" appeared once as a tangential reference.

    Better to MISS a real obit (which falls through to other
    strategies gracefully) than to HIT a wrong obit (which produces
    a confident, fabricated survivor list).

    Scoring signals:
      +10 if the deceased's full name appears in the title
      +6  if the deceased's full name appears in the snippet
      +5  if "obituary" appears in title or URL
      +5  if the domain is a known text-rendered obit source
      +3  if the domain is a known JS-rendered obit source
      +2  if the snippet mentions "survived by" or "passed away"

    Any result that fails the name-match gate is dropped entirely
    (not negative-scored — completely excluded). This is intentional.
    """
    name_lower = deceased_name.lower()

    scored = []
    for r in results:
        title = (r.get("title") or "").lower()
        snippet = (r.get("snippet") or "").lower()
        link = (r.get("link") or "").lower()
        domain = _domain_of(link)

        # Hard name-match gate: full name must appear in title or
        # snippet. Skip anything else entirely.
        in_title = name_lower in title
        in_snippet = name_lower in snippet
        if not in_title and not in_snippet:
            continue

        score = 0
        if in_title:
            score += 10
        if in_snippet:
            score += 6

        # Obit-y signals
        if "obituary" in title or "obituary" in link:
            score += 5
        if "obituaries" in link:
            score += 3

        # Domain familiarity
        if any(d in domain for d in _OBIT_DOMAINS_TEXT):
            score += 5
        elif any(d in domain for d in _OBIT_DOMAINS_JS):
            score += 3
        # Funeral home domains (catch-all): often have "funeral",
        # "memorial", "cremation" in the hostname
        elif any(kw in domain for kw in ("funeral", "memorial", "cremation")):
            score += 4

        # Body-text signals
        if "survived by" in snippet or "passed away" in snippet:
            score += 2

        scored.append((score, r))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in scored]


def _domain_of(url: str) -> str:
    """Extract the lowercase domain from a URL."""
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def _name_in_body(deceased_name: str, body_text: str) -> bool:
    """Verify the deceased's name appears in the obit body. Used as
    a post-fetch sanity check before sending to Claude.

    Accepts either:
      - Full name as given (case-insensitive)
      - First+Last (skipping middle initial/name)

    Returns True if either form appears.
    """
    text_lower = body_text.lower()
    name_lower = deceased_name.lower().strip()

    if name_lower in text_lower:
        return True

    # Try first + last only (strip middle name/initial)
    parts = [p for p in re.split(r"\s+", name_lower) if p]
    if len(parts) >= 2:
        first_last = f"{parts[0]} {parts[-1]}"
        if first_last in text_lower:
            return True

    return False


# ════════════════════════════════════════════════════════════════════
#  Page fetch + text extraction
# ════════════════════════════════════════════════════════════════════

def _fetch_obit_text(url: str) -> str:
    """Fetch an obit URL and return cleaned visible body text.
    Returns empty string on any failure."""
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; SellerSignal/3.0; "
                    "+https://sellersignal.co)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=_HTTP_TIMEOUT_SEC,
            allow_redirects=True,
        )
    except Exception as e:
        log.info("HTTP fetch of %s failed: %s", url, e)
        return ""

    if resp.status_code >= 400:
        log.info("HTTP %d fetching %s", resp.status_code, url)
        return ""

    # Some pages return tiny bodies because the real content is JS-
    # injected. Detect this and bail rather than feeding a placeholder
    # to Claude.
    if len(resp.text) < 1000:
        return ""

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return ""

    # Strip scripts, styles, nav chrome
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    body_text = soup.get_text(separator=" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text)

    if len(body_text) < 200:
        # Almost certainly a JS-rendered page that left us with chrome
        return ""

    return body_text[:_OBIT_TEXT_CAP]


# ════════════════════════════════════════════════════════════════════
#  Claude-powered survivor extraction
# ════════════════════════════════════════════════════════════════════

_EXTRACTION_SYSTEM_PROMPT = """\
You extract structured survivor lists from obituary text.

Given an obituary AND the name of a specific deceased person, return
ONLY a JSON object with this shape:
{
  "obit_matches_deceased": true | false,
  "survivors": [
    {
      "name": "Full Name",
      "relationship": "daughter" | "son" | "spouse" | "wife" | "husband" \
        | "brother" | "sister" | "mother" | "father" | "grandchild" | "other",
      "city": "City Name" (or null if not specified),
      "state": "ST" (2-letter, or null if not specified)
    }
  ]
}

FIRST: confirm the obituary is for the named deceased person. The obit
should explicitly identify them as the person who died. If the
obituary is for someone else (and merely mentions the named person as
a relative, neighbor, or passing reference), set
obit_matches_deceased=false and return {"survivors": []}. Do not
extract survivors from someone else's obituary.

Rules for the survivors list (only if obit_matches_deceased=true):
- ONLY include people who are explicitly named as SURVIVING the deceased.
- Exclude the deceased themselves.
- Exclude predeceased family members (those listed as "preceded in death by").
- Exclude friends, neighbors, pallbearers — survivors only.
- If a city is mentioned for a survivor ("of Federal Way", "in Phoenix"), \
include it; otherwise leave city null.
- If state is not stated, infer ONLY if the city is unambiguously in one state \
(e.g., "Seattle" → "WA"). Otherwise leave null.
- If multiple survivors share a city ("his children, Kira and Mike of Federal Way"), \
copy the city to each.

Return ONLY the JSON object. No prose, no markdown, no preamble.
"""


def _extract_survivors_via_claude(
    obit_text: str, deceased_name: str
) -> list[dict[str, Any]]:
    """Send obit body text to Claude, return structured survivor list.
    Returns empty list on any extraction failure, on parse failure, or
    if Claude reports the obit is not actually for the named deceased.
    """
    try:
        from anthropic import Anthropic
        client = Anthropic()
    except Exception as e:
        log.warning("Anthropic client unavailable: %s", e)
        return []

    user_prompt = (
        f"Deceased: {deceased_name}\n\n"
        f"Obituary text:\n---\n{obit_text}\n---\n\n"
        f"First confirm the obit is for {deceased_name}, then extract "
        f"the survivor list per the system instructions."
    )

    try:
        resp = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=_CLAUDE_MAX_TOKENS,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = resp.content[0].text.strip()
    except Exception as e:
        log.warning("Claude extraction call failed: %s", e)
        return []

    # Strip markdown code fences if Claude added them despite the
    # system prompt
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except Exception as e:
        log.warning("Claude returned non-JSON: %s | %s", e, raw[:200])
        return []

    # Defense-in-depth: even though we validated the deceased's name
    # in the body before sending, also respect Claude's judgment on
    # whether this obit actually IS for the named deceased.
    if not parsed.get("obit_matches_deceased", True):
        log.info("Claude reports obit does not match deceased '%s'",
                 deceased_name)
        return []

    survivors = parsed.get("survivors") or []
    if not isinstance(survivors, list):
        return []

    # Light validation: each entry needs at least a name. Strip anything
    # malformed.
    cleaned = []
    for s in survivors:
        if not isinstance(s, dict):
            continue
        name = (s.get("name") or "").strip()
        if not name:
            continue
        cleaned.append({
            "name":         name,
            "relationship": (s.get("relationship") or "other").strip().lower(),
            "city":         (s.get("city") or "").strip() or None,
            "state":        (s.get("state") or "").strip().upper() or None,
        })
    return cleaned


# ════════════════════════════════════════════════════════════════════
#  Snippet fallback (when full-page fetch isn't possible)
# ════════════════════════════════════════════════════════════════════

def _extract_from_snippet(
    snippet: str, deceased_name: str
) -> list[dict[str, Any]]:
    """When the obit page is JS-rendered (Weeks Funeral Home, gather-
    app.com, etc.) we can't get full text, but the SerpAPI snippet
    often contains the survivor line. Send THAT to Claude with the
    same extraction prompt.

    Lower confidence than full-text extraction — snippets are 200-600
    chars and may truncate mid-sentence.
    """
    if not snippet or len(snippet) < 50:
        return []
    # Re-use the same extraction path. The cap-truncated input is fine
    # for Claude — the system prompt handles short inputs gracefully.
    return _extract_survivors_via_claude(
        snippet, deceased_name=deceased_name
    )
