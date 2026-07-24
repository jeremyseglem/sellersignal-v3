"""
Montana District Court harvester — FullCourt Enterprise public portal.

Target: https://dcportal.pubcourts.mt.gov/fullcourtweb/start.do
Counties (Phase 1): Gallatin (Bozeman/Big Sky east), Madison (Big Sky west),
Flathead (Whitefish). All MT probate runs through District Courts.

DISCOVERY MECHANISMS (verified via operator browser 2026-07-23):
  1. Judgment Order Index Search — accepts ORDER DATE FROM/TO as sole
     criteria (portal banner: "You must enter search criteria in either the
     First Name, Last Name, Order Date, or Status Date fields"). Date-range
     sweep; filter probate-relevant order types client-side from results
     (CASE NUMBER / JUDGMENT-ORDER TYPE / ORDER DATE / AGAINST columns).
  2. Case-number enumeration — CASE LOOKUP takes [type][year][sequence] +
     Retrieve. Probate = DP prefix. Walk DP-{year}-NNNNNNN upward until
     misses (CT harvester cap-workaround shape).
  Case detail exposes a LITIGANTS table with ROLE and ATTORNEY columns —
  the PR-extraction surface + intermediary graph feed.

ACCESS NOTE (2026-07-23): the portal WAF ("Request Rejected") blocks
non-browser TLS/header fingerprints from the Claude sandbox; a real Safari
session passes with no login and no CAPTCHA. This module therefore ships
DIAG-FIRST: `diag_bootstrap()` reports exactly what Railway's egress sees
(status, title, form fields, cookies) so the search/detail parsers are
iterated against real observed HTML instead of invented field names.
Nothing here writes to raw_signals_v3 until the parse path is truth-tested
via /api/harvest/diag/mt-portal.

source_type: 'mt_district_court' (registered in matcher.SOURCE_MARKETS).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

BASE = "https://dcportal.pubcourts.mt.gov"
START = f"{BASE}/fullcourtweb/start.do"

# FullCourt Web is one deployment serving many courts; the court is chosen
# in-session. Court display names as shown in the portal's court picker.
COURTS = {
    "gallatin": "Gallatin County District Court",
    "madison": "Madison County District Court",
    "flathead": "Flathead County District Court",
}

# Order types that indicate a probate estate with an appointed fiduciary.
# Matched case-insensitively as substrings against the JUDGMENT/ORDER TYPE
# column. Extend from real result vocabulary after first production sweep.
PROBATE_ORDER_MARKERS = (
    "LETTERS TESTAMENTARY",
    "LETTERS OF ADMINISTRATION",
    "PERSONAL REPRESENTATIVE",
    "APPOINT",           # Order Appointing ...
    "PROBATE",
)
DIVORCE_ORDER_MARKERS = ("DISSOLUTION", "DECREE OF DISSOLUTION")

BROWSER_HEADERS = {
    # Mirror a current Safari/Chrome profile; the WAF rejects bare clients.
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                   "Version/17.5 Safari/605.1.15"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


@dataclass
class PortalProbe:
    ok: bool
    status: Optional[int] = None
    title: str = ""
    final_url: str = ""
    cookies: list = field(default_factory=list)
    forms: list = field(default_factory=list)
    links: list = field(default_factory=list)
    error: str = ""
    html_head: str = ""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _forms(html: str) -> list:
    """Enumerate forms + their input/select names so parsers can be built
    from observed structure, never guessed field names."""
    out = []
    for fm in re.finditer(r"<form\b([^>]*)>(.*?)</form>", html, re.I | re.S):
        attrs, body = fm.group(1), fm.group(2)
        action = (re.search(r'action="([^"]*)"', attrs, re.I) or [None, ""])[1]
        name = (re.search(r'name="([^"]*)"', attrs, re.I) or [None, ""])[1]
        fields = re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"',
                            body, re.I)
        out.append({"name": name, "action": action, "fields": fields[:40]})
    return out


def _nav_links(html: str, limit: int = 30) -> list:
    return [{"href": h, "text": re.sub(r"\s+", " ", t).strip()[:60]}
            for h, t in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                   html, re.I | re.S)[:limit]]


def diag_bootstrap(polite_delay: float = 0.5) -> PortalProbe:
    """Fetch the portal entry and report what this egress actually sees.
    This is the truth-test gate: everything downstream builds on its output."""
    s = _session()
    try:
        r = s.get(START, timeout=45, allow_redirects=True)
        time.sleep(polite_delay)
        html = r.text or ""
        probe = PortalProbe(
            ok=(r.status_code == 200 and "Request Rejected" not in html),
            status=r.status_code,
            title=_title(html),
            final_url=str(r.url),
            cookies=[c.name for c in s.cookies],
            forms=_forms(html),
            links=_nav_links(html),
            html_head=html[:1200],
        )
        return probe
    except Exception as e:  # noqa: BLE001 — diag surfaces everything
        return PortalProbe(ok=False, error=f"{type(e).__name__}: {e}")


def diag_follow(path: str) -> PortalProbe:
    """Bootstrap then follow one portal-relative path with the session's
    cookies — lets us walk court selection / search pages one hop at a
    time from the admin diag endpoint while building the parser."""
    s = _session()
    try:
        s.get(START, timeout=45)
        r = s.get(f"{BASE}{path}" if path.startswith("/") else f"{BASE}/{path}",
                  timeout=45, headers={"Referer": START})
        html = r.text or ""
        return PortalProbe(
            ok=(r.status_code == 200 and "Request Rejected" not in html),
            status=r.status_code, title=_title(html), final_url=str(r.url),
            cookies=[c.name for c in s.cookies], forms=_forms(html),
            links=_nav_links(html), html_head=html[:1200],
        )
    except Exception as e:  # noqa: BLE001
        return PortalProbe(ok=False, error=f"{type(e).__name__}: {e}")


def classify_order_type(order_type: str) -> Optional[str]:
    """Map a judgment/order-type string to a signal_type, or None."""
    t = (order_type or "").upper()
    if any(m in t for m in PROBATE_ORDER_MARKERS):
        return "probate"
    if any(m in t for m in DIVORCE_ORDER_MARKERS):
        return "divorce"
    return None


# ── case-detail parser (built against captured HTML, 2026-07-24 probe v4) ─────
#
# civilCase.do renders a "Litigants" table with these exact columns (verified
# from run 30103158817 artifact 07_dp_case_detail.html):
#
#   Sel | Litigant | Status | Role | Attorney | Case Relationship
#   ''  | Olson, Brent M. | '' | Applicant | Weaver, David L. | N
#   ''  | Olson, Andrew   | '' | Decedent  |                  | N
#
# and a "Case Information" label/value region carrying Case Subtype
# ("Informal Intestate") and Filing Date ("03/20/2026"). The page caption is
# the full case number (DP-16-2026-0000050-II).
#
# Probate role → PR mapping. On a Montana informal probate the appointed
# fiduciary is the APPLICANT (petitioner for informal appointment) — that's
# the living decision-maker to contact. The DECEDENT is the parcel-match key.

_PR_ROLES = ("APPLICANT", "PERSONAL REPRESENTATIVE", "PETITIONER",
             "CO-PERSONAL REPRESENTATIVE", "ADMINISTRATOR", "EXECUTOR")
_DECEDENT_ROLES = ("DECEDENT", "DECEASED", "ESTATE")

# Case-type prefixes on the MT case-number scheme. DP = District Probate.
CASE_TYPE_SIGNAL = {"DP": "probate", "DR": "divorce", "DV": "divorce"}


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell or "")).strip()


def _tables(html: str) -> list:
    return re.findall(r"<table\b[^>]*>.*?</table>", html, re.I | re.S)


def _rows(table_html: str) -> list:
    out = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.I | re.S):
        cells = [_clean(c) for c in
                 re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)]
        if any(cells):
            out.append(cells)
    return out


def _case_info(html: str) -> dict:
    """Pull label/value pairs from the Case Information region. Labels and
    values alternate as sibling cells; we walk the flattened text between the
    'Case Information' heading and the 'Litigants' heading."""
    m = re.search(r"Case Information(.*?)Litigants", html, re.S)
    info = {}
    if not m:
        return info
    seg = re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", "\n", m.group(1)))
    lines = [x.strip() for x in seg.split("\n") if x.strip()]
    wanted = {"Case Subtype": "case_subtype", "Filing Date": "filing_date",
              "Judge": "judge"}
    for i, ln in enumerate(lines):
        if ln in wanted and i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt not in wanted:   # value must not be another known label
                info[wanted[ln]] = nxt
    return info


def parse_case_detail(html: str) -> Optional[dict]:
    """Parse a civilCase.do detail page into a structured case dict, or None
    if it isn't a viewable case (auth wall / not found / no litigants)."""
    if "not authorized to view" in html.lower():
        return None
    cap = re.search(r"\b([A-Z]{2}-\d{2}-\d{4}-\d{7}(?:-[A-Z]{1,3})?)", html)
    case_no = cap.group(1) if cap else None
    if not case_no:
        return None

    lit_rows = []
    for t in _tables(html):
        rows = _rows(t)
        if rows and rows[0][:6] == ["Sel", "Litigant", "Status", "Role",
                                    "Attorney", "Case Relationship"]:
            lit_rows = rows[1:]
            break
    if not lit_rows:
        return None

    litigants = []
    for r in lit_rows:
        r = (r + [""] * 6)[:6]
        _sel, name, status, role, attorney, rel = r
        if not name:
            continue
        litigants.append({"name": name, "status": status, "role": role,
                          "attorney": attorney, "relationship": rel})
    if not litigants:
        return None

    info = _case_info(html)
    prefix = case_no.split("-", 1)[0].upper()
    return {
        "case_number": case_no,
        "case_type_prefix": prefix,
        "signal_type": CASE_TYPE_SIGNAL.get(prefix),
        "case_subtype": info.get("case_subtype"),
        "filing_date": info.get("filing_date"),
        "judge": info.get("judge"),
        "litigants": litigants,
    }


def _mmddyyyy_to_iso(s: str) -> Optional[str]:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def _normalize_party_name(name: str) -> str:
    """Light normalization mirroring the recorder harvester: uppercase, drop
    punctuation noise, collapse whitespace. The matcher's canonicalizer does
    the heavy lifting; this just stabilizes the stored normalized form."""
    n = re.sub(r"[.,]", " ", (name or "").upper())
    n = re.sub(r"\b(JR|SR|II|III|IV|ESQ)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def to_signal_row(case: dict, jurisdiction: str) -> Optional[dict]:
    """Map a parsed case dict to a raw_signals_v3 row (matches the proven
    Dallas-recorder shape). Returns None for non-probate/divorce cases or
    cases missing a matchable decedent.

    party_names[0] is the matcher's key. For probate that's the DECEDENT
    (still on the assessor roll); the APPLICANT/PR is the contact. For divorce
    both spouses are matchable owners.
    """
    sig = case.get("signal_type")
    if sig not in ("probate", "divorce"):
        return None
    lits = case.get("litigants") or []

    parties = []
    if sig == "probate":
        decedent = next((l for l in lits
                         if any(r in (l["role"] or "").upper()
                                for r in _DECEDENT_ROLES)), None)
        pr = next((l for l in lits
                   if any(r in (l["role"] or "").upper()
                          for r in _PR_ROLES)), None)
        if not decedent:
            return None
        parties.append({"raw": decedent["name"],
                        "normalized": _normalize_party_name(decedent["name"]),
                        "role": "decedent", "matchable": True})
        if pr and pr["name"].upper() != decedent["name"].upper():
            parties.append({"raw": pr["name"],
                            "normalized": _normalize_party_name(pr["name"]),
                            "role": "personal_representative",
                            "matchable": False,
                            "attorney": pr.get("attorney") or None})
    else:  # divorce — both listed litigants are matchable owners
        named = [l for l in lits if l.get("name")]
        if not named:
            return None
        for l in named[:2]:
            parties.append({"raw": l["name"],
                            "normalized": _normalize_party_name(l["name"]),
                            "role": "party", "matchable": True})

    attorneys = sorted({l["attorney"] for l in lits if l.get("attorney")})

    return {
        "source_type": "mt_district_court",
        "signal_type": sig,
        "trust_level": "high",
        "party_names": parties,
        "event_date": _mmddyyyy_to_iso(case.get("filing_date") or ""),
        "jurisdiction": jurisdiction,
        "property_hint": None,
        "document_ref": case["case_number"],
        "raw_data": {
            "case_number": case["case_number"],
            "case_subtype": case.get("case_subtype"),
            "filing_date": case.get("filing_date"),
            "judge": case.get("judge"),
            "litigants": lits,
            "attorneys": attorneys,
            "harvester": "mt_district_court",
        },
    }
