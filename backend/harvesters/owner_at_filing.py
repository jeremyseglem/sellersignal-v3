"""
Owner of record ON THE FILING DATE — King County probate matching.

Why (Signal lab H1; Harvester queue #9): the matcher checks a court
filing against TODAY's owner of record. King County puts the buyer on
title within weeks of a sale, so once a decedent's home has sold the
filing is checked against the buyer's name: the real seller is lost and
a buyer who shares the name becomes a false lead. Backtested on 7,225
KC market sales (claude/SIGNAL_LAB.md runs 1-3): matching the grantor
on the first deed recorded after the filing instead of today's owner
raised strict lift over chance from 4.5x to 6.8x and estate recall from
7/48 to 19/48, with the second key (PR #11) in place.

Data: sales_history_v3 (KC public sales file loaded 2026-10-29 by PR #8,
plus the eReal sweep). Rows are the parser's shape: pin, sale_date
(ISO), sale_price, seller_name (KC 'LAST FIRST M+CO-OWNER' form),
instrument and sale_reason as the county's description strings
(EXTR_LookUp LUType 6 / 5).

The rule, per pin and filing date F:
  - no deed recorded after F  -> today's owner (unchanged behaviour);
  - else                       -> the grantor(s) of the FIRST deed
                                  recorded after F;
  - and if any deed after F is a market sale, the match is a catch,
    written retired ('retired_sold_before_match'), never a live lead.
    A non-market retitle after F (to an estate, heir or trust) keeps
    the match live.

Pure functions only; the matcher wires them in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

RETIRED_STATUS = "retired_sold_before_match"

# Market sale = the backtest's definition (SIGNAL_LAB runs 1-3, ENGINE_LOG
# scoreboard): price >= $10k, a deed instrument (EXTR_LookUp LUType 6
# codes 2,3,4,5,6,7,19,20,22,24,27), reason None / Executor / Estate
# Settlement (LUType 5 codes 1,6,8). Quit claims, trustees', sheriff's
# and receiver's deeds and contracts are not market sales. Note this is
# wider than ereal_property_parser._classify_arms_length, which counts
# only 'Statutory Warranty Deed' (the Warranty Deed gap, PR #8).
MARKET_MIN_PRICE = 10_000
MARKET_INSTRUMENTS = frozenset({
    "WARRANTY DEED", "STATUTORY WARRANTY DEED", "SPECIAL WARRANTY DEED",
    "CORPORATE WARRANTY DEED", "ASSUMPTION WARRANTY DEED", "GRANT DEED",
    "EXECUTOR'S DEED", "FIDUCIARY DEED", "BARGAIN AND SALES DEED",
    "DEED OF PERSONAL REP", "DEED",
})
MARKET_REASONS = frozenset({
    "", "NONE", "EXECUTOR-TO ADMIN GUARDIAN", "ESTATE SETTLEMENT",
})

# Words on a KC grantor line that describe the capacity, not the person
# ('SMITH JOHN A ESTE', 'SMITH JOHN PR', 'ESTATE OF SMITH JOHN').
_CAPACITY = frozenset({
    "ESTATE", "ESTE", "EST", "OF", "THE", "PR", "PRS", "EXC", "EXEC",
    "EXECUTOR", "EXECUTRIX", "PERSONAL", "REPRESENTATIVE", "REP", "DECD",
    "DECEASED", "DEC", "AKA", "ETAL", "ET", "AL", "ADM", "ADMR", "ADMIN",
    "ADMINISTRATOR", "HEIRS", "HEIR", "JR", "SR", "II", "III", "IV",
})
_ENTITY = re.compile(
    r"\b(LLC|INC|CORP|TRUST|TRST|TR|TRT|TTEE|TTEES|TTE|BANK|CITY|COUNTY|"
    r"STATE|ASSOC|ASSN|PARTNERS|LP|LLP|CO|COMPANY|CHURCH|HOMES|"
    r"PROPERTIES|INVESTMENTS|HOLDINGS|FUND|GROUP|DEVELOPMENT|SCHOOL|"
    r"UNIVERSITY|FAMILY|LIVING|REVOCABLE|FOUNDATION|MORTGAGE|FEDERAL|"
    r"NATIONAL|ASSOCIATION|SECRETARY|HOUSING)\b")
_TOKEN = re.compile(r"[A-Z][A-Z'\-]*")


def is_market_sale(deed: dict) -> bool:
    """True when a sales_history_v3 row is an open-market sale."""
    price = deed.get("sale_price") or 0
    if price < MARKET_MIN_PRICE:
        return False
    instr = (deed.get("instrument") or "").strip().upper()
    reason = (deed.get("sale_reason") or "").strip().upper()
    return instr in MARKET_INSTRUMENTS and reason in MARKET_REASONS


def deed_party_names(raw: Optional[str]) -> list[str]:
    """KC deed party line -> names in the fabric's 'First [M…] Last' order.

    'SMITH JOHN A+JANE B'      -> ['JOHN A SMITH', 'JANE B SMITH']
    'SMITH JOHN A+DOE MARY'    -> ['JOHN A SMITH', 'MARY DOE']
    'SMITH, JOHN A'            -> ['JOHN A SMITH']
    'SMITH JOHN A ESTE'        -> ['JOHN A SMITH']
    'SMITH FAMILY TRUST'       -> ['SMITH FAMILY TRUST'] (entity: as is)

    A co-owner segment of one token, or a given name plus a middle
    initial, inherits the previous segment's surname (the county writes
    a couple as 'LAST FIRST M+FIRST M').
    """
    if not raw:
        return []
    out: list[str] = []
    prev_last: Optional[str] = None
    for seg in re.split(r"\s*[+&]\s*|\s+AND\s+", raw.upper()):
        seg = seg.strip(" ,.;")
        if not seg:
            continue
        if _ENTITY.search(seg):
            out.append(" ".join(seg.split()))
            prev_last = None
            continue
        if "," in seg:
            last, _, given = seg.partition(",")
            seg = f"{last.strip()} {given.strip()}"
        toks = [t for t in _TOKEN.findall(seg) if t not in _CAPACITY]
        if not toks:
            continue
        if len(toks) == 1:
            if prev_last:
                out.append(f"{toks[0]} {prev_last}")
            continue
        if len(toks) == 2 and len(toks[1]) == 1 and prev_last:
            out.append(f"{toks[0]} {toks[1]} {prev_last}")
            continue
        last, given = toks[0], toks[1:]
        out.append(" ".join(given + [last]))
        prev_last = last
    return out


@dataclass(frozen=True)
class OwnerAtFiling:
    names: tuple            # grantor names of the first deed after the filing
    deed_recording: str     # that deed's recording number
    retire_reason: Optional[str]  # set when a market sale followed the filing


def owner_at_filing(deeds: Optional[list], filing_date: str
                    ) -> Optional[OwnerAtFiling]:
    """The owner of record on `filing_date` from the pin's deeds.

    Returns None when no deed was recorded after the filing (today's
    owner still held title then — the caller keeps today's owner).
    `deeds` may be in any order; rows without a sale_date are ignored.
    """
    f = (filing_date or "")[:10]
    if not f or not deeds:
        return None
    after = sorted(
        (d for d in deeds if (d.get("sale_date") or "")[:10] > f),
        key=lambda d: ((d.get("sale_date") or "")[:10],
                       d.get("recording_number") or ""))
    if not after:
        return None
    first = after[0]
    market = next((d for d in after if is_market_sale(d)), None)
    reason = None
    if market is not None:
        reason = (f"market sale {(market.get('sale_date') or '')[:10]} "
                  f"rec {market.get('recording_number') or ''} after the "
                  f"filing; matched on the owner of record at the filing")
    return OwnerAtFiling(
        names=tuple(deed_party_names(first.get("seller_name"))),
        deed_recording=first.get("recording_number") or "",
        retire_reason=reason,
    )
