#!/usr/bin/env python3
"""
Maricopa County Recorder harvester (Phase 2) — recorded-document signals via
doc-code + date discovery -> PDF fetch -> OCR -> parse -> APN match.

Structural analog of the King County court harvester (list -> detail -> parse),
with one substitution: KC rendered parties as HTML; the Maricopa Recorder serves
the recorded document as a scanned PDF, so the parse step is OCR.

PIPELINE
  1. discover(doc_code, begin, end)  ->  recording numbers
       GET legacy.recorder.maricopa.gov/recdocdata/GetRecDataRecentPgDn.aspx
       ?cde={code}&doc1={code}&bdt={mm/dd/yyyy}&edt={mm/dd/yyyy}&max=N&res=True
  2. fetch_pdf(recnum)               ->  document bytes (all pages)
       GET .../UnofficialPdfDocs.aspx?rec={recnum}&pg={n}&cls=RecorderDocuments
  3. ocr_pdf(bytes)                  ->  text  (pdftoppm 300dpi -> tesseract)
  4. parse_<type>(text)              ->  structured fields
  5. APN match against parcels (parcels_v3 / seed APN set)

DOC CODES -> SIGNAL TYPES (verified against the live code dropdown 2026-06-08):
  NS  Notice of Trustee's Sale        -> foreclosure   (parser implemented)
  PD  Probate Deed (transfer)         -> probate       (parser TODO)
  JP  Decree of Distribution w/ RP    -> probate       (parser TODO)
  DC  Death Certificate               -> death         (parser TODO)
  BB  Beneficiary Deed                -> transfer_on_death (parser TODO)

DEPLOYMENT NOTE: requires `tesseract-ocr` + `poppler-utils` system packages.
These MUST be installed in the Railway build (nixpacks aptPkgs / Aptfile), not
just locally — cf. the pypdf-vs-pdftotext lesson (verify the dependency on
Railway, not only in a dev container) before wiring the background task.

VALIDATION GATES (OCR is imperfect — never trust blindly):
  - APN must match the \\d{3}-\\d{2}-\\d{3} pattern AND exist in the parcel set
    to be promoted to a matched signal; otherwise recorded as unmatched/low-conf.
  - trustor/owner name must be non-empty.
  - a `confidence` flag is set when any key field is missing.
"""
from __future__ import annotations

import http.cookiejar
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

LEGACY_BASE = "https://legacy.recorder.maricopa.gov/recdocdata/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
POLITE_DELAY = 1.0  # seconds between document fetches

DOC_CODE_SIGNALS = {
    "NS": "foreclosure",
    "PD": "probate",
    "JP": "probate",
    "DC": "death",
    "BB": "transfer_on_death",
}


# ── session ────────────────────────────────────────────────────────────────

def new_session() -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    op.open(LEGACY_BASE, timeout=60).read()  # establish session cookies
    return op


def _get(op, url: str, referer: str = LEGACY_BASE, binary: bool = False):
    req = urllib.request.Request(url, headers={"Referer": referer})
    with op.open(req, timeout=90) as r:
        return r.read() if binary else r.read().decode("utf-8", "ignore")


# ── 1. discover ──────────────────────────────────────────────────────────────

def discover(op, doc_code: str, begin: str, end: str, max_results: int = 200) -> list[str]:
    """Return recording numbers for `doc_code` recorded between begin/end (mm/dd/yyyy)."""
    qs = urllib.parse.urlencode({
        "rec": "0", "suf": "", "nm": "",
        "bdt": begin, "edt": end,
        "cde": doc_code, "max": str(max_results), "res": "True",
        "doc1": doc_code, "doc2": "", "doc3": "", "doc4": "", "doc5": "",
    })
    html = _get(op, LEGACY_BASE + "GetRecDataRecentPgDn.aspx?" + qs)
    recnums = re.findall(r'GetRecDataRecentDetail\.aspx\?rec=(\d+)', html)
    # dedupe, preserve order
    seen, out = set(), []
    for r in recnums:
        if r not in seen:
            seen.add(r); out.append(r)
    return out


# ── 2. fetch + 3. OCR ────────────────────────────────────────────────────────

def fetch_pdf(op, recnum: str, max_pages: int = 6) -> bytes:
    """Fetch the unofficial document PDF (concatenate available pages)."""
    # warm the detail page (sets the right session context for the image handler)
    _get(op, LEGACY_BASE + f"GetRecDataRecentDetail.aspx?rec={recnum}")
    # page 1 is usually the full multi-page PDF for these notices; fetch pg=1
    url = (LEGACY_BASE + f"UnofficialPdfDocs.aspx?rec={recnum}"
           f"&pg=1&cls=RecorderDocuments&suf=")
    return _get(op, url, referer=LEGACY_BASE + f"GetRecDataRecentDetail.aspx?rec={recnum}",
                binary=True)


def ocr_pdf(pdf_bytes: bytes, dpi: int = 300) -> str:
    """Rasterize all pages (pdftoppm) and OCR (tesseract). Returns combined text."""
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "d.pdf"
        pdf.write_bytes(pdf_bytes)
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(Path(td) / "pg")],
                       check=True, capture_output=True)
        texts = []
        for png in sorted(Path(td).glob("pg*.png")):
            out = subprocess.run(["tesseract", str(png), "stdout"],
                                 capture_output=True, text=True)
            texts.append(out.stdout)
        return "\n".join(texts)


# ── 4. parse ──────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def normalize_apn(raw: str) -> str | None:
    """Extract a canonical NNN-NN-NNN APN from OCR text fragment."""
    if not raw:
        return None
    m = re.search(r"(\d{3})\s*[-\s]\s*(\d{2})\s*[-\s]\s*(\d{3})", raw)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


_APN_RE = re.compile(r"\b(\d{3})\s*-\s*(\d{2})\s*-\s*(\d{3})\b")
_ADDR_RE = re.compile(
    r"\b(\d{2,6}\s+[NSEW]?\.?\s*[A-Z0-9][A-Za-z0-9 .#'/-]{3,40}?,?\s+"
    r"[A-Za-z .]+?,\s*AZ\s*\d{5})", re.I)
_MARITAL = (r"an?\s+(?:un)?married|husband\s+and\s+wife|a\s+single|a\s+widow|"
            r"as\s+(?:joint|community)|trustee|,?\s*\d{2,6}\s")


def _all_apns(flat: str) -> list[str]:
    """Every NNN-NN-NNN candidate (labeled or not); doc/TS/order numbers don't match this shape."""
    seen, out = set(), []
    for m in _APN_RE.finditer(flat):
        a = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if a not in seen:
            seen.add(a); out.append(a)
    return out


def _all_addresses(flat: str) -> list[str]:
    seen, out = set(), []
    for m in _ADDR_RE.finditer(flat):
        a = _clean(m.group(1))
        if a not in seen:
            seen.add(a); out.append(a)
    return out


def parse_ns(text: str) -> dict:
    """
    Parse a Notice of Trustee's Sale. NS docs come in several trustee-firm
    templates (Tiffany & Bosco, Western Progressive, NATST, ...), so this is
    label-agnostic: collect ALL APN and address candidates and let the APN
    match against the parcel set decide the link, rather than relying on one
    firm's field labels.
    """
    flat = _clean(text.replace("\r", ""))

    apn_candidates = _all_apns(flat)
    addr_candidates = _all_addresses(flat)

    # Owner / trustor: prefer a labeled capture, else the name before the first
    # marital-status/address marker. Cap length to avoid over-capture.
    trustor = re.search(r"(?:Original\s+)?Trustor(?:\(s\))?:?\s*(.{3,80}?)(?:" + _MARITAL + r")",
                        flat, re.I)
    if not trustor:
        # firms that lead with NAME then ADDRESS at the top of the notice
        trustor = re.search(r"(?:NOTICE OF TRUSTEE.?S SALE\s+)?([A-Z][A-Z .'-]{4,60}?)\s+(?:" + _MARITAL + r")",
                            flat)
    owner = _clean(trustor.group(1)) if trustor else None
    if owner and len(owner) > 70:
        owner = None  # over-capture guard

    sale_dt = re.search(r"(?:public auction on|Date of Sale:?|will be sold.*?on)\s+"
                        r"([A-Z][a-z]+\s+\d{1,2},?\s+20\d{2})", flat)
    balance = re.search(r"(?:Original\s+)?Principal Balance(?:\s+as shown[^:]*)?:?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
                        flat, re.I)
    orig_dot = re.search(r"recorded on\s+(\d{2}/\d{2}/\d{4})\s+as Document No\.?\s*(\d+)", flat, re.I)

    rec = {
        "signal_type": "foreclosure", "doc_code": "NS",
        "apn": apn_candidates[0] if apn_candidates else None,
        "apn_candidates": apn_candidates,
        "owner_name": owner,
        "address_candidates": addr_candidates,
        "property_address": addr_candidates[0] if addr_candidates else None,
        "sale_date": _clean(sale_dt.group(1)) if sale_dt else None,
        "principal_balance": _clean(balance.group(1)) if balance else None,
        "orig_dot_date": orig_dot.group(1) if orig_dot else None,
        "orig_dot_docnum": orig_dot.group(2) if orig_dot else None,
    }
    # confidence: high if we have at least one APN (the parcel join key) + an owner
    rec["missing_fields"] = [k for k in ("apn", "owner_name") if not rec[k]]
    rec["confidence"] = "high" if not rec["missing_fields"] else (
        "medium" if (apn_candidates or addr_candidates) else "low")
    return rec


def strip_leading_name_junk(name: str) -> str:
    """
    Remove case-header / OCR junk from the FRONT of an extracted party name.

    Observed pollution (2026-07): "PB PB 2026~-0053797 ALFRED MOSTARDO",
    "PB2026-0047%¢ JEFFREY WILLIAM MOORE" — case numbers grew to 7 digits
    and OCR injects ~ % ¢ etc., so the old \\d{6}-anchored strip missed them.
    Strategy: drop leading tokens until the first token that looks like a
    name word (letters plus . ' - only). Keeps everything after that intact.
    """
    tokens = (name or "").split()
    JUNK = {"PB", "NO", "CASE", "ESTATE", "OF", "MATTER", "IN", "RE"}

    def _edge_trim(t: str) -> str:
        # strip quotes/brackets/OCR symbols glued to token edges,
        # keep interior name chars (letters . ' -)
        return re.sub(r"^[^A-Za-z]+|[^A-Za-z.'’‘\-]+$", "", t)

    # leading junk
    while tokens and len(tokens) > 1:
        t = _edge_trim(tokens[0])
        if t and re.fullmatch(r"[A-Za-z][A-Za-z.\-'’‘]*", t) \
                and not (t.upper().rstrip(".") in JUNK and len(tokens) > 2):
            tokens[0] = t          # keep, minus glued punctuation
            break
        tokens.pop(0)
    # trailing junk (incl. trailing case-header words like "NO. PB")
    while len(tokens) > 1:
        t = _edge_trim(tokens[-1])
        if t and re.fullmatch(r"[A-Za-z][A-Za-z.\-'’‘]*", t) \
                and t.upper().rstrip(".") not in JUNK:
            tokens[-1] = t
            break
        tokens.pop()
    return " ".join(tokens).strip()


def parse_pd(text: str) -> dict:
    """
    Parse a Probate Deed / Deed of Distribution. The lead is the Personal
    Representative (the family member handling the estate); the decedent is the
    prior owner-of-record (a secondary match key against parcels_v3). Multiple
    templates (attorney-drafted vs self-filed AOC forms), so label-agnostic.
    """
    flat = _clean(text.replace("\r", ""))
    apns = _all_apns(flat)
    addrs = _all_addresses(flat)

    # case number (tolerate OCR spacing/dash loss: "PB 2025-005885", "PB_PB2025-...")
    cm = re.search(r"PB[_\s]*(?:PB)?\s*(\d{4})[~\s]*-?\s*(\d{5,8})", flat)
    case_number = f"PB{cm.group(1)}-{cm.group(2)}" if cm else None

    # decedent: capture broadly between "Estate of" and the distribution/deceased
    # terminator, then strip the case-header / line-number noise the OCR injects
    # ahead of the name. Handles ALL-CAPS and Title case.
    decedent = None
    dm = re.search(r"Matter of the Estate of\b[:\s]*(.{4,75}?)\s*,?\s*"
                   r"(?:DEED OF DISTRIBUTION|DEED OR INSTRUMENT|OF DISTRIBUTION|Deceased|deceased)",
                   flat)
    if dm:
        chunk = re.sub(
            r"(?i)^(?:case\s*no\.?:?|no\.?|=|\.|\)|\(|distribution|instrument|or|deed|"
            r"pb[_\s]*(?:pb)?\s*\d{4}\s*-?\s*\d{6}|\d+[}\])]?|[\s:=.)(}\]]+)+", "", dm.group(1)).strip()
        chunk = re.sub(r"\s{2,}", " ", chunk)
        chunk = strip_leading_name_junk(chunk)
        if 4 <= len(chunk) <= 45 and re.search(r"[A-Za-z]{2}", chunk):
            decedent = chunk
    if not decedent:  # "Personal Representative of the ESTATES OF [NAME]" variant
        em = re.search(r"ESTATES? OF\s+([A-Z][A-Za-z.\-' ]{4,40}?)(?:,|\s+(?:Deceased|deceased|and\b))", flat)
        decedent = strip_leading_name_junk(_clean(em.group(1))) if em else None

    # PR (the lead): follows "undersigned PR" / "Person Filing" / "Attorney for",
    # or precedes "Personal Representative" in a signature/caption line.
    pr_name = None
    for pat in (r"undersigned Personal Representatives?,?\s+([A-Z][A-Za-z.\-' ]{4,45}?)(?:,|\s+in order|\s+whose|\s+hereby|\s+a\s)",
                r"Person Filing:?\s*([A-Z][A-Za-z.\-' ]{4,45}?)(?:\s+Address|\s+City|,)",
                r"Attorney for\s+([A-Z][A-Za-z.\-' ]{4,45}?),\s*(?:as\s+)?Personal Representative",
                r"([A-Z][A-Za-z.\-' ]{4,45}?),\s*(?:as\s+)?(?:the\s+)?Personal Representatives?\b"):
        m = re.search(pat, flat)
        if m:
            cand = _clean(m.group(1))
            if cand.lower() not in ("personal", "the", "as") and "Personal Represent" not in cand:
                pr_name = cand
                break

    grantee = re.search(
        r"(?:assigns?,?\s*transfers?\s+and\s+releases?|transfer\s+and\s+release)"
        r"(?:\s+all\s+right[^.]*?)?\s+to\s+([A-Z][A-Za-z .'-]{4,45}?)"
        r"(?:,|\s+an?\s|\s+whose|\s+a\s+(?:married|single|widow))", flat, re.I)

    rec = {
        "signal_type": "probate", "doc_code": "PD",
        "apn": apns[0] if apns else None, "apn_candidates": apns,
        "decedent": decedent,
        "owner_name": pr_name,           # PR = the lead / decision-maker
        "grantee": _clean(grantee.group(1)) if grantee else None,
        "case_number": case_number,
        "address_candidates": addrs,
        "property_address": addrs[0] if addrs else None,
    }
    rec["missing_fields"] = [k for k in ("decedent", "owner_name") if not rec[k]]
    rec["confidence"] = ("high" if (decedent and pr_name)
                         else "medium" if (decedent or pr_name or case_number) else "low")
    return rec


PARSERS = {"NS": parse_ns, "PD": parse_pd}  # JP/DC/BB added as those signals are built


# ── 5. harvest (discover -> fetch -> ocr -> parse -> match) ───────────────────

def harvest(doc_code: str, begin: str, end: str, parcel_apns: set[str],
            limit: int | None = None, verbose: bool = True) -> dict:
    parser = PARSERS.get(doc_code)
    if parser is None:
        raise ValueError(f"no parser implemented for doc_code {doc_code!r}")
    op = new_session()
    recnums = discover(op, doc_code, begin, end)
    if limit:
        recnums = recnums[:limit]
    if verbose:
        print(f"[discover] {doc_code} {begin}..{end}: {len(recnums)} recordings"
              + (f" (capped to {limit})" if limit else ""))

    records, matched, errors = [], [], 0
    for i, rec in enumerate(recnums, 1):
        try:
            pdf = fetch_pdf(op, rec)
            text = ocr_pdf(pdf)
            parsed = parser(text)
            parsed["recording_number"] = rec
            parsed["apn_matched"] = bool(parsed["apn"] and parsed["apn"] in parcel_apns)
            records.append(parsed)
            if parsed["apn_matched"]:
                matched.append(parsed)
            if verbose:
                flag = "✓MATCH" if parsed["apn_matched"] else ("conf=" + parsed["confidence"])
                print(f"  [{i}/{len(recnums)}] rec={rec} apn={parsed['apn']} "
                      f"owner={(parsed['owner_name'] or '')[:32]!r} {flag}")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [{i}/{len(recnums)}] rec={rec} ERROR {type(e).__name__}: {e}")
        time.sleep(POLITE_DELAY)

    return {
        "doc_code": doc_code, "window": [begin, end],
        "discovered": len(recnums), "parsed": len(records),
        "high_conf": sum(1 for r in records if r["confidence"] == "high"),
        "apn_matched_in_zip": len(matched), "errors": errors,
        "records": records, "matched": matched,
    }


def _normalize_party_name(raw: str) -> str:
    return re.sub(r"[^A-Z ]", " ", (raw or "").upper()).strip()


def discover_dated(op, doc_code: str, begin: str, end: str, max_results: int = 400):
    """Like discover() but returns (recording_number, recording_date_iso) pairs."""
    qs = urllib.parse.urlencode({
        "rec": "0", "suf": "", "nm": "", "bdt": begin, "edt": end,
        "cde": doc_code, "max": str(max_results), "res": "True",
        "doc1": doc_code, "doc2": "", "doc3": "", "doc4": "", "doc5": "",
    })
    html = _get(op, LEGACY_BASE + "GetRecDataRecentPgDn.aspx?" + qs)
    text = re.sub(r"<[^>]+>", " ", html)
    out, seen = [], set()
    for m in re.finditer(r"(\d{11})\s+(\d{2}/\d{2}/\d{4})", text):
        rec = m.group(1)
        if rec in seen:
            continue
        seen.add(rec)
        try:
            iso = datetime.strptime(m.group(2), "%m/%d/%Y").date().isoformat()
        except ValueError:
            iso = None
        out.append((rec, iso))
    return out


def to_signal_row(parsed: dict):
    """
    Map a parsed record to a raw_signals_v3 row in the proven shape.

    PROBATE ONLY for now: the matcher's _dispatch_probate reads party_names[0]
    as the decedent and matches it (strict full name) against parcels_v3 owners.
    NS/foreclosure (trustee sale) has no matcher dispatcher yet, so emitting it
    would never match — add a foreclosure dispatcher before harvesting NS to DB.
    """
    if parsed.get("signal_type") != "probate":
        return None
    decedent = parsed.get("decedent")
    if not decedent or not parsed.get("recording_number"):
        return None
    parties = [{"raw": decedent, "normalized": _normalize_party_name(decedent),
                "role": "decedent", "matchable": True}]
    pr = parsed.get("owner_name")  # the Personal Representative (lead contact)
    if pr:
        parties.append({"raw": pr, "normalized": _normalize_party_name(pr),
                        "role": "personal_representative", "matchable": False})
    return {
        "source_type": "az_maricopa_recorder",
        "signal_type": "probate",
        "trust_level": "high",
        "party_names": parties,
        "event_date": parsed.get("event_date"),
        "jurisdiction": "AZ_MARICOPA",
        "property_hint": parsed.get("legal_description") or parsed.get("property_address"),
        "document_ref": parsed.get("recording_number"),
        "raw_data": {
            "recording_number": parsed.get("recording_number"),
            "doc_code": parsed.get("doc_code"),
            "case_number": parsed.get("case_number"),
            "pr_name": pr,
            "decedent": decedent,
            "apn": parsed.get("apn"),
            "property_address": parsed.get("property_address"),
            "legal_description": parsed.get("legal_description"),
            "harvester": "maricopa_recorder",
        },
    }


if __name__ == "__main__":
    import json
    import os
    import sys

    # Load 85254 APN set from the committed seed (keyed by APN_DASH)
    seed = Path(__file__).resolve().parents[2] / "data" / "seeds" / "az-maricopa-85254-owners.json"
    apns = set(json.load(open(seed)).keys()) if seed.exists() else set()
    print(f"loaded {len(apns):,} APNs from 85254 seed")

    end = datetime.now()
    begin = end - timedelta(days=int(os.environ.get("DAYS", "45")))
    res = harvest(
        os.environ.get("CODE", "NS"),
        begin.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"),
        apns, limit=int(os.environ.get("LIMIT", "10")),
    )
    print("\n=== SUMMARY ===")
    print(json.dumps({k: v for k, v in res.items() if k not in ("records", "matched")}, indent=2))
    print("\n=== sample parsed records ===")
    for r in res["records"][:4]:
        print(json.dumps({k: r[k] for k in
              ("recording_number", "apn", "owner_name", "property_address",
               "sale_date", "principal_balance", "confidence", "apn_matched")}, indent=2))
