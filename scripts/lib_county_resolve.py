#!/usr/bin/env python3
"""
County-wide decedent->parcel resolution against the full DCAD owner roll.

WHY THIS EXISTS (2026-06-11): probate signals are county-wide; our parcels_v3
covers only live luxury ZIPs (~31K of Dallas County's 862K accounts ≈ 1.2%).
Filtering county-wide death signals through that slice yields ~zero matches
per week — verified twice (recorder heirship: 0/80; TOPICs citations: 0/37),
while a county-wide check of the same decedents immediately found estate-
titled parcels we were blind to ("BURHOE THOMAS ALLEN EST OF", Irving).

THE INVERSION: resolve every decedent against the WHOLE county roll at
harvest time (in the GitHub Action, where the DCAD bulk file lives), and
attach the resolved parcel(s) to the signal. The app-side matcher then
matches by PARCEL IDENTITY for resolved parcels in live ZIPs (precise, like
the tax_foreclosure bypass) — and resolved parcels in non-live ZIPs ride
along in raw_data as expansion intelligence. ZIP-first display is preserved;
only the match layer sees the county.

NAME MATCHING: DCAD OWNER_NAME1 is usually "LAST FIRST MIDDLE [SUFFIX] [&]"
but joint owners and trusts vary, so matching is ORDER-INSENSITIVE token
logic: a resolution requires the decedent's SURNAME and at least one GIVEN
name both present in the owner tokens. Estate-titled owners ("EST OF",
"ESTATE OF") are flagged — those are the strongest possible signal (the
county already titled the parcel to the estate).
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict

# Tokens that are not name evidence.
_NOISE = {
    "JR", "SR", "II", "III", "IV", "MR", "MRS", "MS", "DR",
    "EST", "ESTATE", "OF", "THE", "&", "AND", "ET", "AL", "UX", "VIR",
    "AKA", "FKA", "NKA", "DECEASED", "DECD", "LIFE", "TR", "TRUST",
    "TRUSTEE", "TRUSTEES", "REV", "REVOCABLE", "LIVING", "FAMILY",
}
_SUFFIX_RE = re.compile(r"\b(JR|SR|II|III|IV)\b\.?", re.I)


def _tokens(name: str) -> list[str]:
    n = re.sub(r"[^A-Za-z ]", " ", (name or "").upper())
    return [t for t in n.split() if len(t) > 1 and t not in _NOISE]


def _decedent_parts(decedent: str, order: str = "first_last") -> tuple[str | None, str | None, set]:
    """('SURNAME', 'FIRSTNAME', {given tokens}) from a decedent name.

    order='first_last'  -> 'Mary G Burns'  (TOPICs citations style)
    order='last_first'  -> 'BURNS MARY G'  (recorder grid style)

    Uses only the segment before any a/k/a alias."""
    primary = re.split(r"\ba/?k/?a\b", decedent or "", flags=re.I)[0]
    toks = _tokens(_SUFFIX_RE.sub(" ", primary))
    if len(toks) < 2:
        return None, None, set()
    if order == "last_first":
        return toks[0], toks[1], set(toks[1:])
    return toks[-1], toks[0], set(toks[:-1])


class CountyOwnerIndex:
    """Surname-keyed index over the full DCAD ACCOUNT_INFO roll."""

    def __init__(self):
        self._by_surname: dict = defaultdict(list)
        self.total = 0

    @classmethod
    def from_dcad_zip(cls, dcad_zip_path: str) -> "CountyOwnerIndex":
        idx = cls()
        zf = zipfile.ZipFile(dcad_zip_path)
        r = csv.reader(io.TextIOWrapper(zf.open("ACCOUNT_INFO.CSV"),
                                        encoding="latin-1", newline=""))
        hdr = next(r)
        ix = {h: i for i, h in enumerate(hdr)}
        for row in r:
            if len(row) < len(hdr):
                continue
            owner = (row[ix["OWNER_NAME1"]] or "").strip()
            if not owner:
                continue
            name2 = (row[ix["OWNER_NAME2"]] or "").strip()
            full_owner = f"{owner} & {name2}" if name2 else owner
            snum = (row[ix["STREET_NUM"]] or "").strip()
            sname = (row[ix["FULL_STREET_NAME"]] or "").strip()
            rec = {
                "acct": row[ix["ACCOUNT_NUM"]].strip(),
                "owner_name": full_owner,
                "address": " ".join(p for p in [snum, sname] if p),
                "city": (row[ix["PROPERTY_CITY"]] or "").strip(),
                "zip": (row[ix["PROPERTY_ZIPCODE"]] or "").strip()[:5],
                "division": row[ix["DIVISION_CD"]].strip(),
                "est_of": bool(re.search(r"\bEST(ATE)?\s+OF\b", full_owner.upper())),
            }
            idx.total += 1
            for t in set(_tokens(full_owner)):
                # index by every token; surname position varies in DCAD
                idx._by_surname[t].append(rec)
        return idx

    @classmethod
    def from_tcad_roll(cls, roll_zip_path: str) -> "CountyOwnerIndex":
        """Travis County loader — streams PROP.TXT (TrueProdigy Legacy
        8.0.32 fixed-width) from the TCAD appraisal-roll export zip.
        Same record shape as from_dcad_zip; acct = prop_id with leading
        zeros stripped (matches parcels_v3.pin for TX_TRAVIS and the
        EXTERNAL_tcad_parcel layer's PROP_ID). division='RES' for A* state
        codes so resolve()'s RES-first ordering keeps working."""
        F = {"prop_id": (1, 12), "owner": (609, 678),
             "s_prefix": (1040, 1049), "s_street": (1050, 1099),
             "s_suffix": (1100, 1109), "s_city": (1110, 1139),
             "s_zip": (1140, 1149), "state_cd": (2732, 2741),
             "s_num": (4460, 4474)}

        def fx(line, k):
            s, e = F[k]
            return line[s - 1:e].strip()

        idx = cls()
        seen = set()
        zf = zipfile.ZipFile(roll_zip_path)
        with zf.open("PROP.TXT") as fh:
            for raw in fh:
                line = raw.decode("latin-1", "ignore")
                owner = fx(line, "owner")
                if not owner:
                    continue
                pid = fx(line, "prop_id").lstrip("0") or "0"
                if pid in seen:
                    continue
                seen.add(pid)
                cd = fx(line, "state_cd").upper()
                rec = {
                    "acct": pid,
                    "owner_name": owner,
                    "address": " ".join(p for p in [fx(line, "s_num"),
                                                    fx(line, "s_prefix"),
                                                    fx(line, "s_street"),
                                                    fx(line, "s_suffix")] if p),
                    "city": fx(line, "s_city"),
                    "zip": fx(line, "s_zip")[:5],
                    "division": "RES" if cd.startswith("A") else (cd or "OTH"),
                    "est_of": bool(re.search(r"\bEST(ATE)?\s+OF\b", owner.upper())),
                }
                idx.total += 1
                for tok in set(_tokens(owner)):
                    idx._by_surname[tok].append(rec)
        return idx

    def resolve(self, decedent: str, max_hits: int = 5,
                order: str = "first_last") -> list[dict]:
        """Return county parcels whose owner plausibly IS this decedent.

        Requires: surname AND the decedent's FIRST given name both present in
        the owner tokens. Middle-name-only overlap is rejected — verified
        false-positive shape: 'Billy Ray Garner' must NOT match 'GARNER
        JOHNNY RAY' on the shared middle name RAY.
        """
        surname, first, givens = _decedent_parts(decedent, order=order)
        if not surname or not first:
            return []
        hits = []
        seen_accts = set()
        for rec in self._by_surname.get(surname, []):
            if rec["acct"] in seen_accts:
                continue
            otoks = set(_tokens(rec["owner_name"]))
            if surname not in otoks or first not in otoks:
                continue
            given_overlap = givens & otoks
            seen_accts.add(rec["acct"])
            hits.append({
                **rec,
                "given_overlap": sorted(given_overlap),
                # strength: 2+ given-name corroboration or estate-titled
                # = strong; single given name = standard.
                "strength": ("strong" if (len(given_overlap) >= 2
                                          or rec["est_of"]) else "standard"),
            })
        # Prefer residential + strong first; cap the list.
        hits.sort(key=lambda h: (h["division"] != "RES",
                                 h["strength"] != "strong"))
        return hits[:max_hits]
