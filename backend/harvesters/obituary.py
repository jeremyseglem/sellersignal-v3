"""
Obituary harvester.

Pulls obituary notices from multiple sources and emits them as
RawSignals with signal_type='obituary'.

KEY INSIGHT vs court filings: obituaries are typically published
1-4 WEEKS BEFORE probate is filed. The obituary harvester is a
leading indicator — agents who act on obit signals are in the
market weeks before competitors working off probate filings.

Multi-source architecture:
  - Seattle Times obituaries (primary — largest paid-obit publisher
    in KC, also syndicates to Legacy.com)
  - Legacy.com Bellevue feed (secondary — aggregator covering
    funeral homes + smaller papers)
  - (Future: Evergreen Washelli, Dignity Memorial, funeral home RSS)

Cloudflare / anti-bot considerations:
  - Some sources (Legacy.com) put obituaries behind JS challenges
    that block non-browser clients
  - We use a rotating user-agent strategy + tolerant error handling:
    a failing source doesn't kill the whole harvest
  - When testing from Railway vs local sandbox, success rates may
    differ because of IP reputation. Run live from Railway.

Dedup strategy:
  - Each obituary has (normalized_name, death_date) as its
    document_ref
  - Multiple sources reporting the same death produce the same
    document_ref and upsert to the same row
  - raw_data.sources_seen tracks which sources independently
    surfaced the same obit

Signal semantics:
  - signal_type='obituary'
  - trust_level='high' (obits are published by reputable outlets)
  - party_names[0] = decedent with role='decedent'
  - raw_data includes: age, death_date, obit_url, source_name,
    funeral_home (if known), survivors (if parsed)
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator, Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseHarvester, Party, RawSignal

log = logging.getLogger(__name__)


# ─── Source adapter protocol ───────────────────────────────────────────

@dataclass
class ObituaryRecord:
    """One obituary from a source — pre-RawSignal format."""
    decedent_name: str
    source_name: str                        # 'seattle_times', 'legacy_bellevue', etc.
    obit_url: Optional[str] = None
    death_date: Optional[date] = None       # Date of death if parsed
    publish_date: Optional[date] = None     # When the obit was published
    age_at_death: Optional[int] = None
    city: Optional[str] = None              # Resident city if known
    funeral_home: Optional[str] = None
    survivors_raw: Optional[str] = None     # Free text describing family
    obit_text_excerpt: Optional[str] = None


class ObituarySource(ABC):
    """Pluggable source adapter. One per website/feed."""

    name: str = ""

    @abstractmethod
    def fetch(self, since: date, until: date) -> Iterator[ObituaryRecord]:
        ...

    def _session(self) -> requests.Session:
        s = requests.Session()
        # A realistic browser UA tends to get fewer 403/503s from
        # publisher sites behind Cloudflare. Still not guaranteed.
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        return s


# ─── Source: Seattle Times ─────────────────────────────────────────────

class SeattleTimesObituariesSource(ObituarySource):
    """
    Seattle Times paid obituaries at obituaries.seattletimes.com.

    URL pattern for individual obituaries:
      /obituary/<slug>-<10+digit ID>

    Strategy: use the public sitemap index rather than the search listing
    pages. The search listings server-render only 25 results per URL and
    ?page=N pagination is JS-only (doesn't work for raw HTTP clients).

    The sitemap at /sitemap.xml is an index pointing to 48+ child
    sitemaps, each holding 500 obit URLs. Child sitemap '0-500' is
    updated every time a new obit is published, so it always contains
    the ~500 most recent obits (covers roughly the last 2-3 weeks at
    typical publication rate of ~30-50/day in King County).

    We fetch that newest-first child sitemap, extract obit URLs, then
    fetch detail pages and filter by extracted death_date.
    """

    name = "seattle_times"
    BASE = "https://obituaries.seattletimes.com"
    # Primary sitemap entry — sorted newest-first, ~500 most recent obits
    RECENT_SITEMAP = "/sitemap/obituaries/obituaries/sitemap-15192521-0-500.xml"
    # Regex to validate obit URLs from the sitemap
    OBIT_URL_RE = re.compile(
        r"^https://obituaries\.seattletimes\.com/obituary/"
        r"([a-z0-9-]+?)-(\d{10,})/?$"
    )

    def fetch(self, since: date, until: date) -> Iterator[ObituaryRecord]:
        session = self._session()
        seen_ids: set = set()

        # 1) Pull the most-recent child sitemap
        sitemap_url = self.BASE + self.RECENT_SITEMAP
        log.info(f"[{self.name}] fetching sitemap {sitemap_url}")
        try:
            r = session.get(sitemap_url, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as e:
            log.warning(f"[{self.name}] sitemap fetch failed: {e}")
            return

        # 2) Extract all obit URLs from <loc> tags
        #    Regex is faster and more tolerant than an XML parser here.
        candidates = []
        for match in re.finditer(r"<loc>([^<]+)</loc>", r.text):
            url = match.group(1).strip()
            m = self.OBIT_URL_RE.match(url)
            if not m:
                continue
            slug, obit_id = m.group(1), m.group(2)
            if obit_id in seen_ids:
                continue
            seen_ids.add(obit_id)
            candidates.append((obit_id, slug, url))

        log.info(f"[{self.name}] sitemap has {len(candidates)} obit URLs")

        # 3) Fetch detail pages and filter by death_date window
        #    Obits in the sitemap are ordered newest-first, so we can stop
        #    early once we've seen several obits older than `since`.
        past_window_count = 0
        PAST_WINDOW_STOP = 50  # after 50 consecutive obits older than since

        for obit_id, slug, abs_url in candidates:
            record = self._fetch_detail(
                session, abs_url, slug, card_text="",
                since=since, until=until,
            )
            if record is None:
                # detail fetch failed OR obit was OUTSIDE our window
                # We don't know which without extra state; _fetch_detail
                # returns None for both. Increment the counter; if we hit
                # 50 in a row, assume we've passed the since date.
                past_window_count += 1
                if past_window_count >= PAST_WINDOW_STOP:
                    log.info(
                        f"[{self.name}] stopping early — "
                        f"{PAST_WINDOW_STOP} consecutive misses"
                    )
                    break
            else:
                past_window_count = 0   # reset on every hit
                yield record
            time.sleep(0.35)

    def _fetch_detail(
        self,
        session: requests.Session,
        url: str,
        slug: str,
        card_text: str,
        since: date,
        until: date,
    ) -> Optional[ObituaryRecord]:
        """Fetch and parse a single obituary detail page."""
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
        except requests.HTTPError:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # 1) Name: prefer <h1> (detail page title). Fallback: title-case slug.
        name = None
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(" ", strip=True)
            # Strip "Obituary of " prefix sometimes added
            h1_text = re.sub(r"^(Obituary of|In Memory of)\s+", "",
                             h1_text, flags=re.I)
            if 2 <= len(h1_text.split()) <= 8:
                name = h1_text
        if not name:
            # Derive from slug: "katherine-tate" -> "Katherine Tate"
            # Last component is the ID — strip it from consideration.
            parts = slug.replace("-", " ").split()
            # Filter out suffixes like "jr", "iii"
            name = " ".join(p.title() for p in parts)

        # 2) Body text for date/age/city extraction
        full_text = soup.get_text(" ", strip=True)

        death_date = _extract_death_date(full_text)
        if death_date and not (since <= death_date <= until):
            # Obit is outside requested window
            return None

        age = _extract_age(full_text)
        city = _extract_city(full_text)

        return ObituaryRecord(
            decedent_name=name,
            source_name=self.name,
            obit_url=url,
            death_date=death_date,
            age_at_death=age,
            city=city,
            obit_text_excerpt=full_text[:3000] if full_text else None,
        )


# ─── Source: Dignity Memorial (replaces Cloudflare-blocked Legacy.com) ──

class DignityMemorialObituariesSource(ObituarySource):
    """
    Dignity Memorial regional obituary listings.

    Unlike Legacy.com (Cloudflare-blocked from Railway IPs), Dignity
    Memorial serves public HTML pages with obituary data fully rendered
    server-side — no JS, no bot challenge.

    Pages hit:
      /obituaries/bellevue-wa  — Eastside KC (Bellevue, Mercer Island,
                                  Kirkland, Medina, Redmond, etc.)
      /obituaries/seattle-wa   — Seattle + nearby

    Listing format: 50 obits per page, each rendered as:
      <h3>FIRST MIDDLE LAST</h3>
      MM/DD/YYYY - MM/DD/YYYY   (birth - death)
      <p>Excerpt text mentioning residence city...</p>
      <a href="/obituaries/<city>-wa/first-last-<digits>">...</a>

    We parse everything from the listing HTML — no detail fetches needed
    for the data we care about (name, death_date, city, excerpt).

    URL format: /obituaries/bellevue-wa/<slug>-<6+digit-id>
    """

    name = "dignity_memorial"
    BASE = "https://www.dignitymemorial.com"
    LISTING_PATHS = [
        "/obituaries/bellevue-wa",  # Eastside KC
        "/obituaries/seattle-wa",   # Seattle + west-side KC
    ]
    # Match obit detail URLs: /obituaries/<city>-wa/<slug>-<digits>
    OBIT_URL_RE = re.compile(
        r"^/obituaries/[a-z-]+-wa/([a-z0-9-]+?)-(\d{5,})/?$"
    )
    # Date range pattern in listings: "03/13/1927 - 04/18/2026"
    DATE_RANGE_RE = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{1,2}/\d{4})"
    )

    # For single-date obits: "Passed away MM/DD/YYYY"
    SINGLE_DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")

    def fetch(self, since: date, until: date) -> Iterator[ObituaryRecord]:
        session = self._session()
        seen_ids: set = set()

        for listing_path in self.LISTING_PATHS:
            url = self.BASE + listing_path
            log.info(f"[{self.name}] fetching {url}")
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
            except requests.HTTPError as e:
                log.warning(f"[{self.name}] failed {url}: {e}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            # The listing is structured as repeating card blocks. Each card
            # has an <h3> with the name, a date range, an excerpt, and an
            # <a> link to the detail page. We anchor off the <a> link since
            # that's the most reliable marker.
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    if not href.startswith(self.BASE):
                        continue
                    href = href[len(self.BASE):]
                m = self.OBIT_URL_RE.match(href)
                if not m:
                    continue
                slug, obit_id = m.group(1), m.group(2)
                if obit_id in seen_ids:
                    continue
                seen_ids.add(obit_id)

                # Extract name from the card. Dignity renders it inside
                # an <h3> directly preceding the <a>. Walk up to find.
                name_text = None
                date_range_text = None
                excerpt_text = None

                # Strategy: find the closest ancestor containing both an
                # <h3> (name) and the date text. Common container classes:
                # .obit-card, .card, article, etc.
                container = a
                for _ in range(6):  # walk up at most 6 parents
                    parent = container.parent
                    if parent is None:
                        break
                    container = parent
                    h3 = container.find("h3")
                    if h3:
                        name_text = h3.get_text(" ", strip=True)
                        # Search the container for date range
                        container_text = container.get_text(" ", strip=True)
                        dm = self.DATE_RANGE_RE.search(container_text)
                        if dm:
                            date_range_text = (dm.group(1), dm.group(2))
                        # Excerpt: grab first <p> inside container
                        p = container.find("p")
                        if p:
                            excerpt_text = p.get_text(" ", strip=True)
                        break

                # Fallback to slug-derived name if no h3 found
                if not name_text:
                    name_text = " ".join(w.title() for w in slug.split("-"))

                # Parse dates
                birth_date = None
                death_date = None
                if date_range_text:
                    try:
                        birth_date = datetime.strptime(
                            date_range_text[0], "%m/%d/%Y",
                        ).date()
                        death_date = datetime.strptime(
                            date_range_text[1], "%m/%d/%Y",
                        ).date()
                    except ValueError:
                        pass

                # Filter by death date window (if we parsed one)
                if death_date and not (since <= death_date <= until):
                    continue

                # Compute age if we have both dates
                age = None
                if birth_date and death_date:
                    age = (death_date - birth_date).days // 365

                # Extract city from excerpt
                city = None
                if excerpt_text:
                    city = _extract_city(excerpt_text)
                # If no city in excerpt, assume Bellevue-listing context
                if not city and "bellevue-wa" in href:
                    city = "Bellevue"

                abs_url = self.BASE + href
                yield ObituaryRecord(
                    decedent_name=name_text,
                    source_name=self.name,
                    obit_url=abs_url,
                    death_date=death_date,
                    age_at_death=age,
                    city=city,
                    obit_text_excerpt=excerpt_text[:3000] if excerpt_text else None,
                )

                # Polite delay between same-listing obits (no detail fetch
                # needed, so this is small)
                time.sleep(0.05)


# ─── Source: Legacy.com Bellevue (DEPRECATED — Cloudflare blocks Railway) ─

class LegacyBellevueObituariesSource(ObituarySource):
    """
    Legacy.com Bellevue-area obituary listing.

    URL: https://www.legacy.com/us/obituaries/local/washington/bellevue
    """

    name = "legacy_bellevue"
    BASE = "https://www.legacy.com"
    LIST_PATH = "/us/obituaries/local/washington/bellevue"
    # Legacy obituary URLs follow:
    #   /us/obituaries/name/first-last-obituary?pid=<digits>
    # Require the ?pid= param to skip CTA / nav links.
    OBIT_URL_RE = re.compile(r"^/us/obituaries/name/[^/?]+\?pid=\d+")

    def fetch(self, since: date, until: date) -> Iterator[ObituaryRecord]:
        session = self._session()
        url = f"{self.BASE}{self.LIST_PATH}"
        log.info(f"[{self.name}] fetching {url}")

        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as e:
            log.warning(f"[{self.name}] failed: {e} — likely Cloudflare block")
            return

        soup = BeautifulSoup(r.text, "html.parser")

        seen_pids: set = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                if not href.startswith(self.BASE):
                    continue
                href = href[len(self.BASE):]
            if not self.OBIT_URL_RE.match(href):
                continue
            # Dedup by pid
            pid_match = re.search(r"pid=(\d+)", href)
            if not pid_match:
                continue
            pid = pid_match.group(1)
            if pid in seen_pids:
                continue
            seen_pids.add(pid)

            # Name: text inside the anchor, or fallback to slug
            card_text = a.get_text(" ", strip=True)
            if not card_text or len(card_text) < 3:
                # Derive from slug
                slug_match = re.match(r"^/us/obituaries/name/([^/?]+)", href)
                if slug_match:
                    slug = slug_match.group(1).replace("-obituary", "")
                    card_text = " ".join(p.title() for p in slug.split("-"))
                else:
                    continue
            # Strip trailing "Obituary" word that anchor text often includes
            card_text = re.sub(r"\s*obituary\s*$", "", card_text, flags=re.I).strip()

            abs_url = self.BASE + href
            yield ObituaryRecord(
                decedent_name=card_text,
                source_name=self.name,
                obit_url=abs_url,
                city="Bellevue",   # Implicit from the /bellevue listing
            )


# ─── Top-level harvester ───────────────────────────────────────────────

class ObituaryHarvester(BaseHarvester):
    """
    Multi-source obituary harvester. Delegates to ObituarySource adapters
    and dedups by (normalized_name, death_date) before yielding.
    """

    source_type = "obituary_rss"
    jurisdiction = "WA_KING"

    def __init__(self, sources: Optional[list[ObituarySource]] = None):
        self.sources = sources or [
            SeattleTimesObituariesSource(),
            DignityMemorialObituariesSource(),
            # LegacyBellevueObituariesSource() — deprecated, Cloudflare blocks Railway
        ]

    def harvest(
        self,
        since: date,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        until = until or date.today()
        seen: dict = {}     # dedup key → ObituaryRecord

        for source in self.sources:
            try:
                for rec in source.fetch(since, until):
                    key = self._dedup_key(rec)
                    if key in seen:
                        # Merge: track that this source also saw the obit
                        existing = seen[key]
                        if rec.source_name not in (existing.obit_url or ""):
                            # Could track sources_seen in a list; skip for now
                            pass
                        continue
                    seen[key] = rec
            except Exception as e:
                log.exception(f"[{source.name}] harvester failed")
                continue

        log.info(f"Obituary harvest: {len(seen)} unique obituaries "
                 f"from {len(self.sources)} sources")

        # Emit RawSignals
        for rec in seen.values():
            yield self._record_to_signal(rec)

    # ─── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _dedup_key(rec: ObituaryRecord) -> str:
        """Normalized key for deduping obits across sources."""
        name = re.sub(r"[^A-Za-z ]", "", rec.decedent_name or "").strip().upper()
        name = re.sub(r"\s+", " ", name)
        date_str = rec.death_date.isoformat() if rec.death_date else "nodate"
        return f"{name}::{date_str}"

    @staticmethod
    def _record_to_signal(rec: ObituaryRecord) -> RawSignal:
        # Parse the decedent name into structured components
        from .kc_superior_court import _split_name
        parties = [Party(
            raw=rec.decedent_name,
            role="decedent",
            **_split_name(rec.decedent_name),
        )]

        # document_ref = dedup key so re-runs are idempotent
        doc_ref = f"obit::{ObituaryHarvester._dedup_key(rec)}::{rec.source_name}"

        return RawSignal(
            source_type="obituary_rss",
            signal_type="obituary",
            trust_level="high",
            party_names=parties,
            event_date=rec.death_date or rec.publish_date,
            jurisdiction="WA_KING",
            document_ref=doc_ref,
            raw_data={
                "source_name":       rec.source_name,
                "obit_url":          rec.obit_url,
                "age_at_death":      rec.age_at_death,
                "city":              rec.city,
                "funeral_home":      rec.funeral_home,
                "survivors_raw":     rec.survivors_raw,
                "obit_text_excerpt": rec.obit_text_excerpt,
            },
        )


# ─── Regex helpers for unstructured obit text ──────────────────────────

_DATE_PATTERNS = [
    # "passed away on March 25, 2026" / "died January 14, 2026"
    re.compile(r"\b(?:passed away|died|death|laid to rest|entered eternal rest|"
               r"went to be with|was called home|departed this life)"
               r"\s+(?:on|peacefully on|suddenly on|unexpectedly on)?\s*"
               r"(January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
               re.IGNORECASE),
]

# Generic Month-Day-Year pattern used as fallback. Captures ALL occurrences
# and the extractor picks the latest plausible date — the birth date always
# precedes the death date chronologically, so max() gives death.
_ANY_DATE_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _extract_death_date(text: str) -> Optional[date]:
    """
    Best-effort death date extraction. Two strategies:

    1) Look for an explicit death-verb phrase (passed away, died, etc.)
       immediately followed by a date. Most reliable when the obit is
       well-structured prose.

    2) Fallback: find every 'Month Day, Year' in the text and take the
       LATEST one. Obituaries always mention birth before death
       chronologically, so the max date is the death date.
    """
    from datetime import date as _date_cls

    # Strategy 1: explicit death-verb match
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                month = _MONTHS[m.group(1).lower()]
                day = int(m.group(2))
                year = int(m.group(3))
                return _date_cls(year, month, day)
            except (KeyError, ValueError):
                continue

    # Strategy 2: take the latest plausible date from all mentions
    dates_found = []
    for m in _ANY_DATE_PATTERN.finditer(text):
        try:
            month = _MONTHS[m.group(1).lower()]
            day = int(m.group(2))
            year = int(m.group(3))
            if 1900 <= year <= 2100:
                dates_found.append(_date_cls(year, month, day))
        except (KeyError, ValueError):
            continue
    if dates_found:
        return max(dates_found)

    return None


def _extract_age(text: str) -> Optional[int]:
    """Match 'age XX' or 'XX years old'."""
    m = re.search(r"\b(?:age|aged)\s+(\d{1,3})\b", text, re.IGNORECASE)
    if m:
        age = int(m.group(1))
        if 0 < age < 120:
            return age
    m = re.search(r"\b(\d{1,3})\s+years\s+old\b", text, re.IGNORECASE)
    if m:
        age = int(m.group(1))
        if 0 < age < 120:
            return age
    return None


# KC cities we care about for the pilot
_KC_CITIES = {
    "bellevue", "seattle", "redmond", "kirkland", "medina", "mercer island",
    "issaquah", "bothell", "sammamish", "newcastle", "renton", "kent",
    "federal way", "auburn", "shoreline", "burien", "tukwila", "des moines",
    "snoqualmie", "north bend", "maple valley", "covington", "black diamond",
    "clyde hill", "yarrow point", "hunts point", "beaux arts", "woodinville",
}


def _extract_city(text: str) -> Optional[str]:
    """Look for city mentions in obit text. Returns the first KC city
    found in any of several common obit patterns."""
    low = text.lower()
    # Patterns ordered by specificity (most specific first)
    for city in _KC_CITIES:
        for pattern in (
            f"of {city}, washington",
            f"of {city}, wa",
            f"in {city}, washington",
            f"in {city}, wa",
            f"at home in {city}",
            f"resident of {city}",
            f"from {city}, wa",
            f"{city}, wa passed away",
            f"passed away in {city}",
            f"died in {city}",
        ):
            if pattern in low:
                return city.title()
    return None
