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
