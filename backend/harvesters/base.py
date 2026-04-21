"""
Harvester base class and shared data types.

Every harvester returns an Iterator[RawSignal]. The runner is responsible
for persistence to raw_signals_v3 — harvesters are pure pull-and-parse.

This separation lets us:
  - unit test harvesters without a database
  - rate-limit and batch at the runner level uniformly
  - swap in re-harvest / backfill logic without touching harvester code
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Iterator, Optional


# ─── Data model ────────────────────────────────────────────────────────

@dataclass
class Party:
    """A person or entity named in a filing."""
    raw: str                                          # e.g. "SMITH, JOHN Q"
    role: str = "party"                               # decedent | petitioner | respondent | grantor | grantee
    first: Optional[str] = None                       # Parsed; populated by harvester if easy, else null
    last: Optional[str] = None
    middle: Optional[str] = None
    suffix: Optional[str] = None
    entity: Optional[str] = None                      # For LLC / Trust / corporation

    def to_dict(self) -> dict:
        # Include a 'normalized' sub-object to match schema's party_names shape
        normalized = {}
        for k in ("first", "last", "middle", "suffix", "entity"):
            v = getattr(self, k)
            if v:
                normalized[k] = v
        return {
            "raw": self.raw,
            "role": self.role,
            "normalized": normalized if normalized else None,
        }


@dataclass
class RawSignal:
    """
    One harvested filing/record, ready to write to raw_signals_v3.

    Required fields:
      - source_type      matches the source_type ENUM in 006_raw_signals.sql
      - signal_type      matches the signal_type ENUM
      - party_names      list of Party objects (at least one)
      - document_ref     unique identifier from the source (case no, URL, etc)

    Optional fields:
      - trust_level      defaults to 'high' for court filings, 'medium' for
                         listings, 'low' for web matches. Override per-signal.
      - event_date       filing date / death date / listing change
      - jurisdiction     e.g. 'WA_KING' or 'WA_STATE'
      - property_hint    {address, city, state, zip, parcel_id, ...} if known
      - raw_data         original payload for audit/reprocessing
    """
    source_type: str
    signal_type: str
    party_names: list[Party]
    document_ref: str
    trust_level: str = "high"
    event_date: Optional[date] = None
    jurisdiction: Optional[str] = None
    property_hint: Optional[dict] = None
    raw_data: Optional[dict] = None

    def to_row(self) -> dict:
        """Shape for Supabase insert into raw_signals_v3."""
        return {
            "source_type":   self.source_type,
            "signal_type":   self.signal_type,
            "trust_level":   self.trust_level,
            "party_names":   [p.to_dict() for p in self.party_names],
            "event_date":    self.event_date.isoformat() if self.event_date else None,
            "jurisdiction":  self.jurisdiction,
            "property_hint": self.property_hint,
            "document_ref":  self.document_ref,
            "raw_data":      self.raw_data,
        }


# ─── Base harvester ────────────────────────────────────────────────────

class BaseHarvester:
    """
    Subclasses implement .harvest(since, until) -> Iterator[RawSignal].

    Conventions:
      - source_type is a class constant matching the ENUM in schema
      - jurisdiction is the default (override per-signal if multi-jurisdiction)
      - Harvesters should be pure pull-and-parse; persistence is the runner's job
      - Respect polite rate limits: sleep 0.5-2s between requests by default
      - Raise exceptions freely; the runner logs and continues with the next source
    """

    source_type: str = ""
    jurisdiction: str = ""

    def harvest(
        self,
        since: date,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        raise NotImplementedError

    # Helper: subclasses can override to add custom HTTP session config.
    # Default is a plain requests.Session with a modern UA.
    def build_session(self):
        import requests
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        return s
