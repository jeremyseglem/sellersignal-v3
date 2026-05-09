"""
KC Delinquent Property Taxes harvester.

Pulls the King County Treasury "Delinquent Taxes" dataset from KC Open Data
(Socrata SODA API) and emits each materially-delinquent parcel as a RawSignal
with signal_type=tax_delinquency.

Source: https://data.kingcounty.gov/resource/dsv3-ct3e
Provenance: King County Treasury (official). Updated weekly. Captures every
parcel/account that has any unpaid property tax line item, across all
billing years.

WHY THIS COMPLEMENTS kc_treasury (tax_foreclosure):
  - kc_treasury (signal_type=tax_foreclosure) catches parcels at the FORMAL
    foreclosure stage — 3+ years delinquent and the Certificate of Delinquency
    has been filed in Superior Court. Volume: ~100-200 parcels KC-wide. Late.
  - This harvester (signal_type=tax_delinquency) catches the EARLIER stages —
    parcels with 1-2 years of unpaid tax bills that haven't yet hit formal
    foreclosure. Volume: ~4,100 parcels KC-wide at bill_year≤2024 (1+yr).
  - The same parcel may legitimately appear in BOTH feeds at different points
    in the lifecycle. We do not dedup across signal types — they represent
    distinct stages and surface differently in the agent UI.

Signal semantics:
  - signal_type='tax_delinquency'
  - trust_level='high' (KC Treasury is authoritative — these are the actual
    billing records, not derived inferences)
  - party_names: a single sentinel party with role='parcel_only'; the matcher
    bypasses the surname gate for parcel-only signals (parcel identity itself
    is the match key)
  - property_hint.parcel_id = the parcel PIN
  - document_ref = parcel-keyed unique id; one signal row per delinquent
    parcel. raw_data carries the year-list and amounts so the briefing/dossier
    can render rich context without joining back to the source.

THE KEY DATA TRANSFORM (PIN ↔ account_number):
  Per KC's official property research FAQ:
    "A parcel number... 10 digit alpha-numeric number, and corresponds to
     the first 10 characters of your property tax account number."
  So account_number is 12 chars; PIN = account_number[:10]. Multiple
  account_numbers can exist per parcel (different tax sub-accounts: real
  property, drainage, forest patrol, etc.). We aggregate all rows for a
  given PIN before emitting the signal.

FILTERING (what counts as a "real" seller-stress signal):
  The raw dataset has ~492K rows / ~117K distinct accounts. Most are not
  seller-stress signals — they include current-year unpaid bills (just
  payment lag), tiny drainage/forest-patrol fees, and zero-balance lines.
  We filter to:
    1) bill_year <= (current_year - 2)   → at least 1 year overdue
    2) sum(billed - paid) >= $1,000       → meaningful unpaid amount
  This combination produces high-quality leads (verified against 98077:
  yields 11 parcels with $5K-$32K total unpaid).

TIER CLASSIFICATION (for downstream eligibility / briefing routing):
  Stamped into raw_data['tier']. Used by the eligibility selector to
  decide where each signal surfaces:
    - 'priority'   = multi-year delinquent AND unpaid >= $5,000
                     → its own elevated tier in the briefing
    - 'monitoring' = single-year delinquent OR unpaid in [$1K, $5K)
                     → Build Now pool with a tax-stress tag

SENIOR CITIZEN FLAGGING (per product decision):
  raw_data['senior_flag'] is set when ANY line item carries the
  senior_citizen_flag. This is surfaced visibly in the briefing/dossier
  (NOT used to exclude — agents need to make the judgment call). Per
  rationale: senior owners with deep delinquency are exactly the
  demographic that most needs help, and a competent agent helps.

DEDUP & UPDATES:
  - One document_ref per PIN. Re-running the harvester upserts the same
    raw_signals_v3 row with refreshed year-list / amounts.
  - A parcel that PAYS OFF its delinquency drops out of the feed. We do
    NOT auto-expire — past delinquency is still a meaningful indicator.
    (Future: add a nightly diff job that stamps resolved_at.)
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime
from typing import Iterator, Optional

import requests

from .base import BaseHarvester, Party, RawSignal

log = logging.getLogger(__name__)

# Socrata CSV endpoint. We use CSV (not JSON) because the JSON endpoint
# times out on row-fetches on this dataset (verified during Gate 1 source
# health check — JSON 60s timeout vs CSV ~3s for the same query).
SODA_CSV_URL = "https://data.kingcounty.gov/resource/dsv3-ct3e.csv"

# KC Treasury's public-facing page describing this dataset (for raw_data audit)
SOURCE_PAGE = (
    "https://data.kingcounty.gov/Property/Delinquent-Taxes/dsv3-ct3e"
)

# Filter thresholds — see module docstring "FILTERING" for rationale
MIN_UNPAID_CENTS = 100_000          # $1,000 minimum to qualify as a signal
PRIORITY_UNPAID_CENTS = 500_000     # $5,000 threshold for priority tier
PRIORITY_REQUIRES_MULTI_YEAR = True # priority also requires 2+ delinquent years


def _current_year() -> int:
    """Current calendar year. Extracted so tests can patch."""
    return datetime.utcnow().year


def _delinquency_year_floor() -> int:
    """
    Highest bill_year that counts as 'delinquent' for our purposes.
    A bill_year == current year is normal payment lag, not stress.
    A bill_year == current_year - 1 is borderline (could still be lag).
    A bill_year <= current_year - 2 is unambiguous stress.

    NOTE: KC's tax cycle issues bills in the calendar year for that year's
    tax. By the time a bill_year is two calendar years behind, the parcel
    has had multiple deadlines pass.
    """
    return _current_year() - 2


def _safe_int(s: str) -> int:
    """Parse a Socrata text-typed integer, defaulting to 0 on empty/garbage."""
    try:
        return int((s or "0").strip())
    except (ValueError, TypeError):
        return 0


class KCDelinquentTaxesHarvester(BaseHarvester):
    """
    Pulls the KC Treasury delinquent-taxes feed and emits one signal
    per materially-delinquent parcel.

    Unlike most other harvesters, this one does its own per-PIN aggregation
    (the source data has multiple line items per parcel — one per tax
    sub-account). The aggregation happens in-memory before emitting.
    """

    source_type = "kc_delinquent_taxes"
    jurisdiction = "WA_KING"

    request_timeout = 120
    retry_attempts = 3
    retry_backoff_s = 3.0

    # Socrata $limit ceiling per request. The full bill_year<=2024 cut is
    # ~28K rows; one request comfortably covers it.
    page_size = 100_000

    def harvest(
        self,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        """
        since/until are accepted for interface compatibility with other
        harvesters but are ignored — the delinquency feed is a point-in-time
        snapshot, not a time-series.
        """
        year_floor = _delinquency_year_floor()

        # Pull all rows where bill_year is the year_floor or earlier.
        # Socrata's bill_year column is text; the <= comparison is
        # lexical, but for 4-digit years '0001'..'9999' lexical order
        # equals numeric order, so this works correctly.
        params = {
            "$where": f"bill_year<='{year_floor}'",
            "$limit": self.page_size,
            "$order": "account_number",  # stable order for reproducibility
        }
        s = self.build_session()

        csv_text = self._fetch_with_retry(s, params)
        if not csv_text:
            log.error("KC Delinquent Taxes: empty response after retries")
            return

        # Parse CSV in-memory and aggregate by PIN
        reader = csv.DictReader(io.StringIO(csv_text))
        agg = self._aggregate_by_pin(reader)
        log.info(
            f"KC Delinquent Taxes: aggregated {len(agg)} distinct parcels "
            f"from feed (year_floor={year_floor})"
        )

        # Emit one RawSignal per qualifying PIN
        fetched_at = datetime.utcnow().isoformat()
        emitted = 0
        skipped_under_threshold = 0
        for pin, info in agg.items():
            unpaid = info["billed_total"] - info["paid_total"]
            if unpaid < MIN_UNPAID_CENTS:
                skipped_under_threshold += 1
                continue

            # Tier classification (per product decision: hybrid)
            multi_year = len(info["years"]) >= 2
            if (
                unpaid >= PRIORITY_UNPAID_CENTS
                and (multi_year or not PRIORITY_REQUIRES_MULTI_YEAR)
            ):
                tier = "priority"
            else:
                tier = "monitoring"

            # Sentinel party: parcel_only signals don't have a name to gate
            # on. The matcher's _DISPATCH for tax_delinquency bypasses the
            # surname gate.
            party = Party(
                raw="(Tax Delinquency — parcel match)",
                role="parcel_only",
            )

            yield RawSignal(
                source_type=self.source_type,
                signal_type="tax_delinquency",
                trust_level="high",
                party_names=[party],
                event_date=None,  # feed has no single "as of" date per parcel
                jurisdiction=self.jurisdiction,
                property_hint={"parcel_id": pin},
                document_ref=f"kc_delinquent_taxes::{pin}",
                raw_data={
                    "parcel":            pin,
                    "delinquent_years":  sorted(info["years"]),
                    "year_count":        len(info["years"]),
                    "billed_cents":      info["billed_total"],
                    "paid_cents":        info["paid_total"],
                    "unpaid_cents":      unpaid,
                    "unpaid_dollars":    round(unpaid / 100.0, 2),
                    "receivable_types":  sorted(info["receivable_types"]),
                    "senior_flag":       info["senior_flag"],
                    "tier":              tier,
                    "source":            "kc_delinquent_taxes_soda",
                    "soda_dataset":      "dsv3-ct3e",
                    "source_url":        SODA_CSV_URL,
                    "source_page":       SOURCE_PAGE,
                    "fetched_at":        fetched_at,
                    "year_floor":        year_floor,
                },
            )
            emitted += 1

        log.info(
            f"KC Delinquent Taxes: emitted {emitted} signals "
            f"(skipped {skipped_under_threshold} parcels under "
            f"${MIN_UNPAID_CENTS/100:.0f} unpaid threshold)"
        )

    def _fetch_with_retry(self, session, params) -> str:
        """Single CSV pull with retry on transient failure."""
        last_err: Optional[Exception] = None
        for attempt in range(self.retry_attempts):
            try:
                r = session.get(
                    SODA_CSV_URL,
                    params=params,
                    timeout=self.request_timeout,
                )
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_err = e
                log.warning(
                    f"KC Delinquent Taxes attempt {attempt+1}/"
                    f"{self.retry_attempts}: {type(e).__name__}: {e}"
                )
                if attempt + 1 < self.retry_attempts:
                    time.sleep(self.retry_backoff_s * (attempt + 1))
        if last_err:
            raise last_err
        raise RuntimeError("KC Delinquent Taxes fetch failed (no exception captured)")

    @staticmethod
    def _aggregate_by_pin(reader) -> dict:
        """
        Aggregate Socrata rows by PIN (= account_number[:10]).

        Returns a dict keyed by PIN with this shape:
          {
            "<pin>": {
                "years":             {bill_year, ...},
                "billed_total":      int (cents),
                "paid_total":        int (cents),
                "receivable_types":  {receivable_type_code, ...},
                "senior_flag":       bool,
            },
            ...
          }
        """
        agg: dict = {}
        for row in reader:
            acct = (row.get("account_number") or "").strip()
            if len(acct) < 10:
                continue
            pin = acct[:10]

            entry = agg.get(pin)
            if entry is None:
                entry = {
                    "years":            set(),
                    "billed_total":     0,
                    "paid_total":       0,
                    "receivable_types": set(),
                    "senior_flag":      False,
                }
                agg[pin] = entry

            year = (row.get("bill_year") or "").strip()
            if year:
                entry["years"].add(year)

            entry["billed_total"] += _safe_int(row.get("billed_amount"))
            entry["paid_total"] += _safe_int(row.get("paid_amount"))

            rtype = (row.get("receivable_type") or "").strip()
            if rtype:
                entry["receivable_types"].add(rtype)

            if (row.get("senior_citizen_flag") or "").strip():
                entry["senior_flag"] = True

        return agg
