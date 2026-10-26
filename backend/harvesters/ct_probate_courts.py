"""
CT Probate Courts harvester — statewide public case-lookup service.

Discovery (2026-07-18 recon): ctprobate.gov exposes a plain JSON service
with NO captcha and NO auth:

    GET https://www.ctprobate.gov/services/case-lookup
        ?caseTypeCode=1        (1 = Decedent's Estate, 2 = Trusts)
        &districtNum=PD52      (probate district, e.g. Darien - New Canaan)
        &status=2              (UI default radio; returns open cases)
        &nameLast=SM           (PREFIX match on decedent last name)
        &nameFirst=

Response: {"recordsTotal": N, "data": [{caseId, code, caseNumber,
nameLast, nameFirst, nameMiddle, dateFiled, distNum, courtName}, ...]}

Two constraints shape the sweep strategy:
  1. Results are hard-capped at 1000 rows, oldest-first, and every
     date/sort parameter we probed is ignored server-side.
  2. nameLast is a PREFIX match and returns the COMPLETE slice when it
     fits under the cap (verified: PD52 nameLast=SM -> 56 rows spanning
     1993..2025).

So: sweep each district by last-name prefix A..Z; any slice that comes
back at exactly the 1000 cap is split one letter deeper (AA..AZ, depth
capped). Union the slices, filter client-side by dateFiled >= since.
~30-60 polite requests per district per run.

What this yields TODAY: decedent-tier probate signals (name + filing
date + case number + court). Same day-1 shape as Snohomish daily
reports — leads launch as no_pr_yet and the matcher joins the DECEDENT
name to parcels. The fiduciary/executor tier needs the case-DETAIL
surface, which this module does not yet call: raw_data.case_id is
persisted on every signal specifically so a future detail-enrichment
pass can fetch fiduciaries without re-discovering cases.

Districts covering live CT territories (extend as CT grows — and note
this is intentionally config, not a hidden allowlist; the harvester logs
which districts it sweeps on every run). Town -> court comes from the
live court locator (https://www.ctprobate.gov/court-locator, "Cities /
Towns" per court, read 2026-10-26); the PD codes are the districtNum
values on the case-lookup form the same day.

    PD54  Greenwich Probate Court            06830/06831/06870/06878/06807
    PD52  Darien - New Canaan Probate Court  06820 (pending) / 06840
    PD50  Westport Probate Court             06880 / 06883 (Weston)
    PD51  Norwalk - Wilton Probate Court     06897 (+ Norwalk/Rowayton later)
    PD49  Fairfield Probate Court            06824 / 06825 (town of Fairfield;
                                             06890 Southport is in the town)
    PD46  Trumbull Probate Court             06612 (Easton)
    PD45  Northern Fairfield County          06877 (Ridgefield)
    PD24  Litchfield Hills Probate Court     06757 Kent / 06759 Litchfield /
                                             06069 Sharon / 06039+06068
                                             Lakeville (town of Salisbury)

Added 2026-10-26 (Harvester engineer, Warden Y8 "06824/06825 zero probate"):
PD49/PD46/PD45/PD24 — the live CT footprint had 9 ZIPs outside the
original four-district sweep.
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional

import requests

log = logging.getLogger(__name__)

SERVICE_URL = "https://www.ctprobate.gov/services/case-lookup"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# District -> human label. Sweep set for the live CT footprint.
DISTRICTS = {
    "PD54": "Greenwich",
    "PD52": "Darien - New Canaan",
    "PD50": "Westport (incl. Weston)",
    "PD51": "Norwalk - Wilton",
    # 2026-10-26: the rest of the live CT footprint (see module docstring)
    "PD49": "Fairfield",
    "PD46": "Trumbull (incl. Easton)",
    "PD45": "Northern Fairfield County (incl. Ridgefield)",
    "PD24": "Litchfield Hills (Kent / Litchfield / Salisbury / Sharon)",
}

# caseTypeCode values on the public form. We harvest Decedent's Estate
# only for now; Trusts (2) is a deliberate follow-up once Jeremy signs
# off on how trust FILINGS should map onto the existing signal taxonomy.
CASE_TYPE_DECEDENT_ESTATE = "1"

ROW_CAP = 1000          # server-side hard cap per response
POLITE_DELAY = 0.4      # seconds between requests
MAX_PREFIX_DEPTH = 3    # A -> AB -> ABC; beyond this something is wrong
HTTP_TIMEOUT = 30
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _fetch_slice(session: requests.Session, district: str,
                 prefix: str) -> list[dict]:
    """One service call: all open decedent-estate cases in `district`
    whose decedent last name starts with `prefix`."""
    resp = session.get(
        SERVICE_URL,
        params={
            "caseTypeCode": CASE_TYPE_DECEDENT_ESTATE,
            "districtNum": district,
            "status": "2",
            "nameLast": prefix,
            "nameFirst": "",
        },
        headers={"User-Agent": UA,
                 "Referer": "https://ctprobate.gov/case-lookup"},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data") or []


def sweep_district(session: requests.Session, district: str,
                   prefix: str = "", depth: int = 0,
                   stats: "Optional[HarvestStats]" = None) -> Iterator[dict]:
    """
    Yield every case row in `district` by recursive prefix sweep.
    A slice at exactly ROW_CAP is assumed truncated and split deeper.
    Failed slices are logged, counted on `stats.slice_errors` when a
    stats object is given, and skipped.
    """
    for letter in ALPHABET:
        p = prefix + letter
        try:
            rows = _fetch_slice(session, district, p)
        except Exception as e:
            log.warning(f"ct_probate: slice {district}/{p} failed: "
                        f"{type(e).__name__}: {e}")
            if stats is not None:
                stats.slice_errors += 1
                stats.last_slice_error = f"{district}/{p}: {type(e).__name__}: {e}"
            continue
        if stats is not None:
            stats.slices_ok += 1
        time.sleep(POLITE_DELAY)
        if len(rows) >= ROW_CAP and depth < MAX_PREFIX_DEPTH:
            log.info(f"ct_probate: {district}/{p} hit the {ROW_CAP} cap — "
                     f"splitting deeper")
            yield from sweep_district(session, district, p, depth + 1, stats)
        else:
            if len(rows) >= ROW_CAP:
                log.error(f"ct_probate: {district}/{p} STILL capped at "
                          f"depth {depth} — some rows unreachable")
            yield from rows


def _parse_date_filed(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        return None


@dataclass
class HarvestStats:
    districts: int = 0
    rows_seen: int = 0
    in_window: int = 0
    signals_built: int = 0
    slices_ok: int = 0
    slice_errors: int = 0
    last_slice_error: Optional[str] = None


class CTProbateCourtsHarvester:
    """
    BaseHarvester-shaped adapter for orchestrator.HARVESTERS.
    Yields one decedent-tier RawSignal per qualifying estate case.
    """
    source_type = "ct_probate_courts"
    jurisdiction = "CT_FAIRFIELD"

    def __init__(self, case_types: Optional[list] = None):
        # Accepted for registry-signature compatibility; ignored (we
        # always harvest Decedent's Estate — see module docstring).
        self.case_types = case_types
        self.stats = HarvestStats()

    def harvest(self, since: date, until: Optional[date] = None):
        from backend.harvesters.base import RawSignal, Party

        until = until or date.today()
        session = requests.Session()
        seen_refs: set[str] = set()

        log.info(f"ct_probate: sweeping districts "
                 f"{sorted(DISTRICTS)} for filings {since}..{until}")
        self.stats.districts = len(DISTRICTS)

        for district in sorted(DISTRICTS):
            for row in sweep_district(session, district, stats=self.stats):
                self.stats.rows_seen += 1

                filed = _parse_date_filed(row.get("dateFiled"))
                if filed is None or not (since <= filed <= until):
                    continue
                self.stats.in_window += 1

                case_number = (row.get("caseNumber") or "").strip()
                if not case_number:
                    continue
                # Case numbers embed a court code but prefix with the
                # district anyway — cheap insurance on the dedup key.
                document_ref = f"{district}-{case_number}"
                if document_ref in seen_refs:
                    continue
                seen_refs.add(document_ref)

                last = (row.get("nameLast") or "").strip()
                first = (row.get("nameFirst") or "").strip()
                middle = (row.get("nameMiddle") or "").strip()
                if not last:
                    continue
                raw_name = f"{last}, {first} {middle}".strip().rstrip(",")

                party = Party(
                    raw=raw_name,
                    role="decedent",
                    first=first or None,
                    last=last or None,
                    middle=middle or None,
                )

                self.stats.signals_built += 1
                yield RawSignal(
                    source_type=self.source_type,
                    signal_type="probate",
                    trust_level="high",   # first-party court record
                    party_names=[party],
                    document_ref=document_ref,
                    event_date=filed,
                    jurisdiction=self.jurisdiction,
                    property_hint=None,   # filings don't list properties
                    raw_data={
                        # case_id is the key for future fiduciary
                        # detail-enrichment — do not drop it.
                        "case_id": row.get("caseId"),
                        "case_number": case_number,
                        "code": row.get("code"),
                        "court_name": row.get("courtName"),
                        "district": district,
                        "date_filed": row.get("dateFiled"),
                        "harvester": "ct_probate_courts",
                    },
                )

        log.info(f"ct_probate: done — rows_seen={self.stats.rows_seen} "
                 f"in_window={self.stats.in_window} "
                 f"signals={self.stats.signals_built} "
                 f"slices_ok={self.stats.slices_ok} "
                 f"slice_errors={self.stats.slice_errors}")

        # Silent-zero guard (the in-process analogue of the recorder
        # runners' non-zero exit, eddb913): if every slice errored and
        # nothing was read, raise so run_harvest records the failure in
        # stats["errors"] and the autofill task's last_error — instead of
        # a green tick with harvested=0. Rows already yielded are
        # unaffected (the raise happens after the sweep).
        if self.stats.rows_seen == 0 and self.stats.slice_errors > 0 \
                and self.stats.slices_ok == 0:
            raise RuntimeError(
                f"ct_probate: all {self.stats.slice_errors} slices failed, "
                f"0 rows read — portal/service change? last: "
                f"{self.stats.last_slice_error}")
