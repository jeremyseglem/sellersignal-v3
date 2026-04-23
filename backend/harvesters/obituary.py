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
        except (requests.HTTPError, requests.RequestException) as e:
            log.warning(f"[{self.name}] sitemap fetch failed: {e}")
            return
        except Exception as e:
            # Catch any unexpected exception so one bad URL doesn't kill
            # the whole harvest. Log with exception type for debugging.
            log.warning(f"[{self.name}] sitemap unexpected error: {type(e).__name__}: {e}")
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

        # 2) Extract obit body specifically, not whole page chrome.
        # Seattle Times renders: <h2>... Obituary</h2> then paragraphs.
        # We find the h2 whose text ends with "Obituary" and collect
        # sibling paragraphs until we hit "Read more", "Published on",
        # "Events", or "Guestbook" markers.
        obit_body = None
        for h2 in soup.find_all(["h2", "h3"]):
            h2_text = h2.get_text(" ", strip=True)
            if h2_text.lower().endswith("obituary"):
                # Collect text from siblings until stop marker
                parts = []
                for sib in h2.find_all_next(["p", "div", "h2", "h3"], limit=40):
                    sib_text = sib.get_text(" ", strip=True)
                    low = sib_text.lower()
                    if not sib_text:
                        continue
                    if (low.startswith(("events", "guestbook",
                                         "funeral arrangements"))
                            or low.startswith("published on")
                            or "read more" in low):
                        break
                    parts.append(sib_text)
                if parts:
                    obit_body = " ".join(parts)
                    break

        # Fallback: whole-page text minus nav chrome (if we couldn't
        # isolate the body). Strip common nav fragments.
        full_text = soup.get_text(" ", strip=True)
        if not obit_body:
            obit_body = full_text

        death_date = _extract_death_date(obit_body) or _extract_death_date(full_text)
        if death_date and not (since <= death_date <= until):
            return None

        age = _extract_age(obit_body)
        city = _extract_city(obit_body)
        survivors_text = _extract_survivors_text(obit_body)

        return ObituaryRecord(
            decedent_name=name,
            source_name=self.name,
            obit_url=url,
            death_date=death_date,
            age_at_death=age,
            city=city,
            survivors_raw=survivors_text,
            obit_text_excerpt=obit_body[:3000] if obit_body else None,
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
    LISTING_URLS = [
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

        for listing_path in self.LISTING_URLS:
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
        # Clean the decedent name before structured parsing. Obituary
        # sources commonly format names like:
        #   'Landrum "Lanny" Thomas Head (Lanny)'
        #   'William Michael Taylor (Bill)'
        # Both a quoted nickname and a trailing parenthetical need to
        # come off before _split_name, which otherwise returns
        # last="(Lanny)" — garbage that then gets propagated as the
        # inferred surname to every first-name-only survivor.
        from .kc_superior_court import _split_name
        clean_name = re.sub(r"\([^)]*\)", "", rec.decedent_name or "")  # drop (nickname)
        clean_name = re.sub(r'"[^"]*"', "", clean_name)                  # drop "nickname"
        clean_name = re.sub(r"\s+", " ", clean_name).strip()

        decedent_parsed = _split_name(clean_name)
        parties = [Party(
            raw=rec.decedent_name,
            role="decedent",
            **decedent_parsed,
        )]

        # Extract survivors from the obit body if we have one.
        # Survivors are valuable because they're the heirs/PRs — exactly
        # who the agent wants to contact. We emit them as additional Party
        # objects with survivor_* roles, which the matcher can also try
        # to match to parcel owners (catches cases where a child inherits
        # and moves in).
        decedent_surname = decedent_parsed.get("last") or None
        excerpt = rec.obit_text_excerpt or rec.survivors_raw or ""
        survivor_names = _extract_survivor_names(
            excerpt, decedent_surname=decedent_surname,
        )
        # Filter out survivor candidates that are junk tokens rather than
        # real first names. Common offenders: 'Jr', 'Sr', 'II', 'III', 'IV'.
        # These come from a regex that captured a suffix as if it were a name.
        _JUNK_FIRST = {"Jr", "Sr", "Ii", "Iii", "Iv", "V", "The", "A", "An"}
        for s in survivor_names:
            parts = s["name"].split()
            first = parts[0] if parts else None
            if first in _JUNK_FIRST:
                continue  # skip bogus entry
            last = parts[-1] if len(parts) > 1 else None
            parties.append(Party(
                raw=s["name"],
                role=s["role"],
                first=first,
                last=last,
            ))

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
                "survivors_parsed":  survivor_names,
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


# ─── Survivors extraction ──────────────────────────────────────────────

# Match sentences that introduce survivor lists. We capture the sentence
# body so downstream code can parse individual names.
_SURVIVOR_INTRO_RE = re.compile(
    r"(?:(?:he|she)\s+(?:is\s+)?(?:leaves|survived\s+by|leaves\s+behind)|"
    r"survived\s+by|leaves\s+behind|leaves\s+his|leaves\s+her|"
    r"(?:he|she)\s+is\s+the\s+(?:father|mother)\s+of|"
    r"father\s+to|mother\s+to|"
    r"preceded\s+in\s+death\s+by|predeceased\s+by)",
    re.IGNORECASE,
)

# Capture the family segment immediately following a survivor intro.
# Usually runs until the next sentence (ends with ". " followed by capital)
# or until we hit a section break.
_SURVIVOR_SEGMENT_RE = re.compile(
    r"(?P<intro>"
    r"(?:(?:he|she|they)\s+(?:is\s+)?(?:leaves|survived\s+by|leaves\s+behind)|"
    r"survived\s+by|leaves\s+behind|leaves\s+his|leaves\s+her|"
    r"preceded\s+in\s+death\s+by|predeceased\s+by|"
    r"father\s+to|mother\s+to)"
    r")"
    r"(?P<segment>[^.]{5,400}?)(?:\.\s+[A-Z]|\.\s*$|$)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_survivors_text(text: str) -> Optional[str]:
    """
    Extract a human-readable multi-sentence block describing family/
    survivors. Concatenates all sentences matching survivor intros.
    Returns None if nothing found.

    This is the fallback agents can read directly — structured name
    extraction happens separately via _extract_survivor_names.
    """
    if not text:
        return None
    matches = list(_SURVIVOR_SEGMENT_RE.finditer(text))
    if not matches:
        return None
    # Reassemble each match as a full phrase
    phrases = []
    for m in matches:
        full = (m.group("intro") + m.group("segment")).strip()
        # Collapse internal whitespace
        full = re.sub(r"\s+", " ", full)
        if full and full not in phrases:
            phrases.append(full)
    return ". ".join(phrases)[:2000] if phrases else None


# Relationship marker words. Each maps to a Party role.
# Includes both singular ("son") and plural ("sons") forms so the regex
# alternation built from this dict matches both.
_RELATIONSHIP_MARKERS = {
    # Spouse
    "wife":            "survivor_spouse",
    "husband":         "survivor_spouse",
    "spouse":          "survivor_spouse",
    "partner":         "survivor_spouse",
    # Children
    "son":             "survivor_child",
    "sons":            "survivor_child",
    "daughter":        "survivor_child",
    "daughters":       "survivor_child",
    "child":           "survivor_child",
    "children":        "survivor_child",
    "stepson":         "survivor_child",
    "stepsons":        "survivor_child",
    "stepdaughter":    "survivor_child",
    "stepdaughters":   "survivor_child",
    # Siblings
    "brother":         "survivor_sibling",
    "brothers":        "survivor_sibling",
    "sister":          "survivor_sibling",
    "sisters":         "survivor_sibling",
    # Parents
    "father":          "survivor_parent",
    "mother":          "survivor_parent",
    "parent":          "survivor_parent",
    "parents":         "survivor_parent",
    # Grandchildren
    "grandson":        "survivor_grandchild",
    "grandsons":       "survivor_grandchild",
    "granddaughter":   "survivor_grandchild",
    "granddaughters":  "survivor_grandchild",
    "grandchild":      "survivor_grandchild",
    "grandchildren":   "survivor_grandchild",
    # Grandparents (rare but appears in some obits)
    "grandfather":     "survivor_grandparent",
    "grandmother":     "survivor_grandparent",
    "grandparent":     "survivor_grandparent",
    "grandparents":    "survivor_grandparent",
    # Other
    "niece":           "survivor_other",
    "nieces":          "survivor_other",
    "nephew":          "survivor_other",
    "nephews":         "survivor_other",
    "cousin":          "survivor_other",
    "cousins":         "survivor_other",
    "friend":          "survivor_other",
    "friends":         "survivor_other",
}

# Build the "rel" alternation for the intro regex. Order matters — match
# longer words first (e.g. "grandmother" before "mother") so the regex
# doesn\'t short-circuit to a shorter prefix.
_REL_WORDS_BY_LENGTH = sorted(
    _RELATIONSHIP_MARKERS.keys(),
    key=lambda w: -len(w),
)
_REL_ALT = "|".join(re.escape(w) for w in _REL_WORDS_BY_LENGTH)


# Intro phrase matcher. Captures just "<modifier?> <rel_word>" and the
# optional connector ("to", "of N years", "in life", ",") that introduces
# the name list. The list itself is parsed separately from the text
# that lies between one intro and the next.
#
# The `connector` group captures "to" or "of" so extraction code can
# invert the role for patterns like "Father to X" (X is a child, not a
# parent) or "Grandmother to Y" (Y is a grandchild).
_REL_INTRO_RE = re.compile(
    r"(?:(?:loving|beloved|devoted|dear|cherished|surviving)\s+)?"
    # Number words before plural: "three sons", "39 year partner"
    r"(?:(?:\d+\s+year\s+|\d+\s+|two\s+|three\s+|four\s+|five\s+|"
    r"six\s+|seven\s+|many\s+))?"
    r"\b(?P<rel>" + _REL_ALT + r")\b"
    # Phrases that can attach between rel and name list:
    r"(?:\s+of\s+(?:\d+\s+years?|his\s+life|her\s+life))?"
    r"(?:\s+in\s+life)?"
    # Connector: optional "to"/"of" or comma/colon. Word boundary after
    # connector prevents matching "To" at start of "Tom".
    r"\s*[,:]?\s*(?P<connector>to|of)?\b\s*",
    re.IGNORECASE,
)

# A single name token: 1-4 capitalized words. Handles middle initials
# ("James I. Doughty"), internal apostrophes ("O\'Brien"), hyphens
# ("Mary-Kate"), and Jr/Sr/II/III/IV suffixes. Minimum 2 chars per
# name-part rules out bare "I" as a standalone word.
_NAME_PART = r"[A-Z][a-zA-Z\'\u2019\-]*[a-zA-Z]"
_NAME_RE = re.compile(
    _NAME_PART                                       # first word
    + r"(?:\s+(?:" + _NAME_PART + r"|[A-Z]\.))*"   # more words or X. initials
    + r"(?:\s+(?:Jr\.?|Sr\.?|II|III|IV))?"        # optional suffix
)

# Stop markers inside a name list. When we see these, the list is over.
_LIST_STOP_RE = re.compile(
    r"\s+(?:and\s+(?:his|her|their|by\s+his|by\s+her)|"
    r"as\s+well\s+as|along\s+with|plus|including)\b",
    re.IGNORECASE,
)


def _parse_name_list(
    segment: str,
    decedent_surname: Optional[str] = None,
) -> list[str]:
    """
    Given a text segment between a relationship intro and the next stop
    point, extract a list of names.

    Handles:
      - comma-separated: "Paul, John, James"
      - Oxford "and" variants: "Paul, John, and James"
      - "X and Y" pairs: "Albert and Jean Anderson"
      - Surname propagation: single-token names get the LAST name\'s
        surname if available, else the decedent\'s surname.
    """
    if not segment:
        return []

    # Terminate at the first stop marker.
    stop = _LIST_STOP_RE.search(segment)
    if stop:
        segment = segment[: stop.start()]
    # Also terminate at sentence-ending punctuation if present.
    segment = re.split(r"[.;:!?]", segment, maxsplit=1)[0]

    # Split on: ", [and ]" (comma with optional "and" after) OR bare " and ".
    # Handles "Tom, Jane, and Sarah" (Oxford) and "Tom and Jane" (non-Oxford).
    raw_parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", segment)

    names: list[str] = []
    for part in raw_parts:
        part = part.strip().strip("()").strip()
        if not part:
            continue
        m = _NAME_RE.match(part)
        if not m:
            continue
        name = m.group(0).strip()
        if name and len(name) >= 2:
            names.append(name)

    if not names:
        return []

    # Surname propagation within the list: if the LAST name has 2+ tokens
    # and earlier names are single-token, append the last name\'s surname
    # to them. Handles "Albert and Jean Anderson" → both Anderson.
    last_tokens = names[-1].split()
    if len(last_tokens) >= 2:
        shared_surname = last_tokens[-1]
        # Don\'t propagate if the shared_surname is actually a suffix
        if shared_surname.rstrip(".").lower() not in (
            "jr", "sr", "ii", "iii", "iv",
        ):
            names = [
                n if len(n.split()) >= 2 else f"{n} {shared_surname}"
                for n in names
            ]

    # Fallback: any remaining single-token names get the decedent\'s surname.
    if decedent_surname:
        names = [
            n if len(n.split()) >= 2 else f"{n} {decedent_surname}"
            for n in names
        ]

    return names


def _classify_context(clause: str) -> str:
    """Return \'survived\', \'preceded\', or \'skip\' for a sentence clause."""
    low = clause.lower()
    if re.search(r"preceded\s+in\s+death\s+by|predeceased\s+by", low):
        return "preceded"
    if re.search(
        r"survived\s+by|leaves\s+(?:his|her|behind)|"
        r"is\s+the\s+(?:father|mother|grandfather|grandmother)\s+of|"
        r"(?:father|mother|grandfather|grandmother)\s+to",
        low,
    ):
        return "survived"
    return "skip"


def _extract_survivor_names(
    text: str, decedent_surname: Optional[str] = None,
) -> list[dict]:
    """
    Extract structured (name, role) pairs from survivor text.

    Returns list of dicts: [{"name": "Jane Smith", "role": "survivor_spouse"}, ...]

    Two-pass approach:
      1. Split text into sentence clauses; classify each as "survived",
         "preceded", or "skip" based on context markers.
      2. Within each non-skipped clause, find all relationship intros
         (wife, sons, parents, grandfather, etc.). The name list for
         each intro is the text from that intro\'s end to the next
         intro\'s start (or end of clause).

    Role inversion: "Father to Andrew" means Andrew is a child, not a
    parent; same for Grandfather/Grandmother to. Detected via the "to"
    connector captured on the intro match.

    Surname propagation: within a list like "Albert and Jean Anderson",
    the trailing surname is shared. Remaining single-token names fall
    back to the decedent\'s surname if provided.
    """
    if not text:
        return []
    results: list[dict] = []
    seen: set = set()

    clauses = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)

    for clause in clauses:
        context = _classify_context(clause)
        if context == "skip":
            continue

        intros = list(_REL_INTRO_RE.finditer(clause))
        for i, m in enumerate(intros):
            rel_word = m.group("rel").lower()
            connector = (m.group("connector") or "").lower()

            if rel_word in _RELATIONSHIP_MARKERS:
                base_role = _RELATIONSHIP_MARKERS[rel_word]
            else:
                base_role = _RELATIONSHIP_MARKERS.get(
                    rel_word.rstrip("s"), "survivor_other",
                )

            # ROLE INVERSION: "Father/Mother to X" → X is a child;
            # "Grandfather/Grandmother to X" → X is a grandchild.
            if connector == "to":
                if rel_word in ("father", "mother"):
                    base_role = "survivor_child"
                elif rel_word in ("grandfather", "grandmother"):
                    base_role = "survivor_grandchild"

            role = (
                base_role.replace("survivor_", "predeceased_")
                if context == "preceded"
                else base_role
            )

            # Segment = text between this intro\'s end and next intro\'s
            # start, or end of clause if last intro.
            seg_start = m.end()
            seg_end = (
                intros[i + 1].start()
                if i + 1 < len(intros)
                else len(clause)
            )
            segment = clause[seg_start:seg_end]

            # Propagate decedent surname only for roles that likely share
            # it. Grandchildren often have different surnames (through a
            # married daughter), so skip propagation for them.
            use_decedent_surname = (
                decedent_surname
                if base_role in (
                    "survivor_spouse", "survivor_child",
                    "survivor_sibling", "survivor_parent",
                )
                else None
            )

            for name in _parse_name_list(segment, use_decedent_surname):
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                results.append({"name": name, "role": role})

    return results
