"""
KC Treasury tax-foreclosure harvester.

Pulls the "Foreclosure parcels" dataset from KC Open Data (Socrata SODA
API) and emits each parcel as a RawSignal with signal_type=tax_foreclosure.

Source: https://data.kingcounty.gov/resource/nx4x-daw6.json
Provenance: King County Treasury (official). Updated daily-to-weekly by
the county treasurer's office as properties enter and exit tax-foreclosure
status (delinquent property taxes, typically 3+ years delinquent).

Signal semantics:
  - signal_type='tax_foreclosure'
  - trust_level='high' (KC Treasury is authoritative — this IS the
    record of tax foreclosure status; no parsing or inference)
  - party_names: a single sentinel party with role='parcel_only'
    (the matcher bypasses the surname gate for this signal — the parcel
    identity itself is the match signal, not the owner name)
  - property_hint.parcel_id = the parcel number; this is what the
    dispatcher uses to generate match candidates
  - document_ref is the parcel id itself (unique by definition — you
    either are or aren't in foreclosure at any given moment)

Dedup & updates:
  - Same parcel appearing across multiple runs upserts to the same
    raw_signals_v3 row (conflict on source_type + document_ref).
  - A parcel that LEAVES foreclosure (pays taxes) drops out of the
    SODA feed. We do NOT auto-expire old matches — a past tax-
    foreclosure event is still a meaningful distress indicator.
  - Future: add a companion job that nightly-diffs the feed and stamps
    a `resolved_at` on raw_data when a parcel exits.

Coverage context:
  - Dataset is all KC-wide, typically 100-200 parcels total. Tax
    foreclosure is low-volume because WA law requires 3 years of
    delinquent taxes before seizure.
  - Most foreclosures are NOT in 98004 (Bellevue) — Bellevue owners
    rarely lose homes to unpaid property taxes. But if ONE shows up,
    it's an extraordinarily strong seller-distress signal.
  - Useful signal for ZIP expansion: Kent, Renton, Auburn, SeaTac
    carry most of the county's tax-foreclosure inventory.

Why not the KC Recorder portal (Landmark):
  - The portal is captcha-gated above the ToS language. Testing confirmed
    HTTP 200 returns "Invalid Captcha" on a naive POST. Bypassing a
    security control crosses a line we don't cross. This Treasury feed
    is the official county-published alternative.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterator, Optional

import requests

from .base import BaseHarvester, Party, RawSignal

log = logging.getLogger(__name__)

SODA_URL = "https://data.kingcounty.gov/resource/nx4x-daw6.json"
# KC Treasury's public page describing this dataset (for raw_data audit)
SOURCE_PAGE = (
    "https://kingcounty.gov/depts/finance-business-operations/"
    "treasury/foreclosure/current-foreclosure-action/"
    "foreclosure-properties.aspx"
)


class KCTreasuryForeclosureHarvester(BaseHarvester):
    """Pulls the current KC Treasury tax-foreclosure parcel list."""

    source_type = "kc_treasury"
    jurisdiction = "WA_KING"

    request_timeout = 30
    # The SODA endpoint supports up to 50,000 rows/page by default, with
    # a maximum page size of 50,000. We use a generous limit because the
    # dataset is small (currently ~167 rows). If the dataset ever grows
    # above 50k, we paginate with $offset.
    page_size = 50000
    # Retry on transient 5xx from Socrata (we've observed sporadic 503s
    # that succeed on immediate retry).
    retry_attempts = 3
    retry_backoff_s = 2.0

    def harvest(
        self,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> Iterator[RawSignal]:
        """
        since/until are accepted for interface compatibility with other
        harvesters but are ignored — the Treasury feed is a
        point-in-time snapshot, not a time-series. "since=yesterday"
        returns the same list as "since=30 days ago."
        """
        import time
        s = self.build_session()
        offset = 0
        total_emitted = 0

        while True:
            params = {
                "$limit":  self.page_size,
                "$offset": offset,
                "$order":  "parcels",  # stable order for reproducibility
            }
            rows = None
            last_err = None
            for attempt in range(self.retry_attempts):
                try:
                    r = s.get(
                        SODA_URL,
                        params=params,
                        timeout=self.request_timeout,
                    )
                    r.raise_for_status()
                    rows = r.json()
                    break
                except Exception as e:
                    last_err = e
                    log.warning(
                        f"KC Treasury attempt {attempt+1}/{self.retry_attempts} "
                        f"failed at offset={offset}: {type(e).__name__}: {e}"
                    )
                    if attempt + 1 < self.retry_attempts:
                        time.sleep(self.retry_backoff_s * (attempt + 1))
            if rows is None:
                log.exception("KC Treasury fetch failed after all retries")
                raise last_err or RuntimeError("KC Treasury fetch failed")

            if not rows:
                break

            fetched_at = datetime.utcnow().isoformat()
            for row in rows:
                pin = (row.get("parcels") or "").strip()
                if not pin:
                    continue

                # Normalize: KC Treasury emits 10-digit parcel strings with
                # leading zeros (e.g. "0040000044"). Our parcels_v3.pin
                # uses the same convention (verified against current DB
                # samples: '1802000050', '0627600085'). No conversion.

                # Sentinel party: the matcher dispatcher for this signal
                # type bypasses the surname gate because the match signal
                # is the parcel identity, not a name. We emit a single
                # placeholder party so downstream code that iterates
                # party_names doesn't crash on an empty list.
                party = Party(
                    raw="(Tax Foreclosure — parcel match)",
                    role="parcel_only",
                )

                yield RawSignal(
                    source_type="kc_treasury",
                    signal_type="tax_foreclosure",
                    trust_level="high",
                    party_names=[party],
                    event_date=None,  # Treasury doesn't expose the foreclosure-start date in the feed
                    jurisdiction="WA_KING",
                    property_hint={"parcel_id": pin},
                    document_ref=f"kc_treasury_foreclosure::{pin}",
                    raw_data={
                        "parcel":       pin,
                        "source":       "kc_treasury_soda",
                        "soda_dataset": "nx4x-daw6",
                        "source_url":   SODA_URL,
                        "source_page":  SOURCE_PAGE,
                        "fetched_at":   fetched_at,
                    },
                )
                total_emitted += 1

            # If we got less than a full page, we've seen everything
            if len(rows) < self.page_size:
                break
            offset += len(rows)
            # Safety bound (dataset is ~200 rows; if we ever loop past
            # 10k something is wrong with pagination logic)
            if offset > 10000:
                log.warning(
                    f"KC Treasury harvester hit safety bound at offset={offset}"
                )
                break

        log.info(f"KC Treasury harvester emitted {total_emitted} signals")
