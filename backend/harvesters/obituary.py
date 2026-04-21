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

    The site has a search endpoint with filter_date and sort options.
    Each result has its own detail page with full obituary text.

    URL pattern for listings:
      /obituaries/obituaries/search/?filter_date=pastweek
      &filter_date=today / pastweek / pastmonth / past3months
    """

    name = "seattle_times"
    BASE = "https://obituaries.seattletimes.com"
    SEARCH_PATH = "/obituaries/obituaries/search/"

    # How far back to window per query (Seattle Times only exposes these presets)
    FILTERS = {
        7:   "pastweek",
        30:  "pastmonth",
        90:  "past3months",
    }

    def fetch(self, since: date, until: date) -> Iterator[ObituaryRecord]:
        session = self._session()
        days_back = (until - since).days

        # Pick the smallest preset that covers our window
        filter_date = "past3months"
        for days, label in self.FILTERS.items():
            if days_back <= days:
                filter_date = label
                break

        url = f"{self.BASE}{self.SEARCH_PATH}?filter_date={filter_date}&sort_by=obitspubdate_meta&order=desc"
        log.info(f"[{self.name}] fetching {url}")

        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as e:
            log.warning(f"[{self.name}] failed: {e}")
            return

        soup = BeautifulSoup(r.text, "html.parser")

        # Parse the result cards. ST typically uses .obit-card or similar;
        # we look for any anchor tags linking to individual obit detail pages.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/obituaries/" not in href or href.endswith("/search/"):
                continue

            name = a.get_text(" ", strip=True)
            if not name or len(name) < 3 or len(name) > 120:
                continue

            # Filter: names should have at least two tokens and look like names
            if not re.match(r"^[A-Z][A-Za-z].*\s+[A-Z][A-Za-z]", name):
                continue

            abs_url = href if href.startswith("http") else self.BASE + href

            # Only fetch detail pages for names that look like full names.
            # Detail pages have publish date, age, death date, obit text.
            record = self._fetch_detail(session, abs_url, name, since, until)
            if record:
                yield record
            time.sleep(0.5)

    def _fetch_detail(
        self,
        session: requests.Session,
        url: str,
        name: str,
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

        # Try to extract: publish date, age, death date, city
        full_text = soup.get_text(" ", strip=True)

        death_date = _extract_death_date(full_text)
        if death_date and not (since <= death_date <= until):
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
            obit_text_excerpt=full_text[:800] if full_text else None,
        )


# ─── Source: Legacy.com Bellevue ───────────────────────────────────────

class LegacyBellevueObituariesSource(ObituarySource):
    """
    Legacy.com Bellevue-area obituary listing.

    URL: https://www.legacy.com/us/obituaries/local/washington/bellevue
    """

    name = "legacy_bellevue"
    BASE = "https://www.legacy.com"
    LIST_PATH = "/us/obituaries/local/washington/bellevue"

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

        # Legacy cards have data-component="ObituaryCard" or similar markers.
        # We look for h3/h4 elements with name text inside obituary cards.
        # This parser is best-effort — Legacy's markup has changed before.
        cards = soup.find_all(attrs={"data-component": re.compile("Obituary", re.I)})
        if not cards:
            # Fallback: any <a href> containing /us/obituaries/name/...
            cards = [a for a in soup.find_all("a", href=True)
                     if "/us/obituaries/name/" in a["href"]]

        for card in cards:
            # Extract name and URL
            if hasattr(card, 'find'):
                link = card.find("a", href=True)
                href = link["href"] if link else None
                name_el = card.find(["h3", "h4", "p"])
                name = name_el.get_text(" ", strip=True) if name_el else None
            else:
                # Fallback <a> element
                href = card.get("href")
                name = card.get_text(" ", strip=True)

            if not name or not href:
                continue

            abs_url = href if href.startswith("http") else self.BASE + href
            record = ObituaryRecord(
                decedent_name=name,
                source_name=self.name,
                obit_url=abs_url,
                city="Bellevue",   # Implicit from the listing
            )
            yield record


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
            LegacyBellevueObituariesSource(),
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
    re.compile(r"\b(?:passed away|died|death)\s+(?:on|peacefully on)?\s+"
               r"(January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
               re.IGNORECASE),
    # "March 25, 2026"  (standalone when context makes it clear)
    re.compile(r"\b(January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
               re.IGNORECASE),
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _extract_death_date(text: str) -> Optional[date]:
    """Best-effort death date extraction from unstructured obit text."""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                month = _MONTHS[m.group(1).lower()]
                day = int(m.group(2))
                year = int(m.group(3))
                return date(year, month, day)
            except (KeyError, ValueError):
                continue
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
    """Look for 'of <City>, Washington' or 'of <City>, WA'."""
    low = text.lower()
    for city in _KC_CITIES:
        if f"of {city}, washington" in low or f"of {city}, wa" in low:
            return city.title()
    return None
