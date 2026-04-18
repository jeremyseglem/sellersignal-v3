"""
SellerSignal v2 — Zillow Listing History Scraper.

Fetches price history from Zillow property detail pages.
Extracts "Listed for sale" / "Listing removed" / "Price change" / "Sold" events.

The failed_sale_attempt signal fires when a property was listed and then
removed WITHOUT a subsequent sale — "they tried to sell and failed."

This requires no MLS login. The data is rendered server-side in the HTML
price-history table. Proven fetchable via web_fetch on Apr 17, 2026.

Production considerations:
  - Zillow rate-limits on repeated fetches from the same origin
  - Scale play: Serper API for URL discovery + ScraperAPI (rotating residential IPs)
    for bulk fetches. Budget ~$50-200/month for 5-10 ZIPs of coverage
  - Cache zpid → address mapping; only re-fetch when listing status may have changed
  - Redfin returns 403 (bot-blocked). Zillow works.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ListingEvent:
    date: datetime
    event_type: str   # "listed_for_sale", "listing_removed", "price_change",
                     # "sold", "listed_for_rent", "pending", "contingent"
    price: Optional[int] = None
    source: str = "zillow"

    def __str__(self) -> str:
        p = f" @ ${self.price:,}" if self.price else ""
        return f"{self.date:%Y-%m-%d} · {self.event_type}{p}"


# Maps the Event column text we see in Zillow's price-history table to our
# canonical event types.
EVENT_TYPE_MAP = {
    "listed for sale": "listed_for_sale",
    "listing removed": "listing_removed",
    "listed for rent": "listed_for_rent",
    "price change": "price_change",
    "sold": "sold",
    "pending sale": "pending",
    "pending": "pending",
    "contingent": "contingent",
    "back on market": "relisted",
    "relisted": "relisted",
}


def parse_price_history_from_markdown(md_text: str) -> list[ListingEvent]:
    """
    Parse the "Price history" table out of Zillow's rendered markdown.

    The table looks like:
        ## Price history
        | Date | Event | Price |
        | --- | --- | --- |
        | 8/29/2018 | Listing removed | $2,500$2/sqft |
        | 8/22/2018 | Listed for rent | $2,500$2/sqft |
    """
    events: list[ListingEvent] = []

    # Find the price history section
    m = re.search(r'##\s*Price history\s*\n(.*?)(?=\n##\s|\Z)', md_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return events
    section = m.group(1)

    # Walk table rows: | date | event | price |
    row_re = re.compile(
        r'^\s*\|\s*(\d{1,2}/\d{1,2}/\d{4})\s*\|\s*([^|]+?)\s*\|\s*([^|]*)\s*\|',
        re.MULTILINE,
    )
    for match in row_re.finditer(section):
        date_str, event_str, price_str = match.groups()
        try:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        except ValueError:
            continue

        event_key = event_str.strip().lower()
        canonical = None
        for key, value in EVENT_TYPE_MAP.items():
            if key in event_key:
                canonical = value
                break
        if canonical is None:
            continue

        # Parse price. Zillow shows things like "$2,500$2/sqft" or "$2,820,000"
        # Take the first dollar-amount.
        price = None
        pm = re.search(r'\$([\d,]+)', price_str)
        if pm:
            try:
                price = int(pm.group(1).replace(",", ""))
            except ValueError:
                pass

        events.append(ListingEvent(date=dt, event_type=canonical, price=price))

    return sorted(events, key=lambda e: e.date)


# ═══════════════════════════════════════════════════════════════════════
# FAILED SALE DETECTION
# ═══════════════════════════════════════════════════════════════════════
def detect_failed_sale_attempt(
    events: list[ListingEvent],
    lookback_years: float = 2.0,
) -> Optional[dict]:
    """
    Did this property try to sell and fail?

    HARD RULES (fire only when property is truly off-market):
      - Must have a "listed_for_sale" event within the lookback window
      - That listing must be CLOSED by a subsequent "listing_removed" or "sold"
      - If ANY later "listed_for_sale" event has no subsequent "listing_removed"
        or "sold", the property is currently on-market → DISQUALIFIED
      - Any "sold" event anywhere after the lookback cutoff → resolved, not failed

    This fixes two prior bugs:
      1. Relist-DOM-reset pattern (cancelled MLS# → new active MLS#) was firing
         as failed_sale_attempt. Now correctly disqualified as on-market.
      2. "stale_listing_no_movement" (listed but still active, no price change)
         was firing as failed. An actively-listed property is by definition not
         a failed attempt — competing agent already has it. Removed entirely.

    Returns a dict with {listed_date, removed_date, last_price, dom_days} or None.
    """
    now = datetime.utcnow()
    cutoff = now.replace(year=now.year - int(lookback_years))
    events = sorted(events, key=lambda e: e.date)

    # HARD FILTER: is the property currently on-market?
    # Walk events chronologically. Track open listing cycles.
    # An open cycle = a listed_for_sale not followed by listing_removed or sold.
    open_cycle = False
    for e in events:
        if e.event_type == "listed_for_sale":
            open_cycle = True
        elif e.event_type in ("listing_removed", "sold") and open_cycle:
            open_cycle = False
    if open_cycle:
        return None  # currently listed — do not pitch

    # If ever sold within lookback, it's resolved
    recent_sold = [e for e in events if e.event_type == "sold" and e.date >= cutoff]
    if recent_sold:
        return None

    # Find most recent CLOSED listing cycle (listed → removed, no later activity)
    last_listing_idx = None
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        if e.event_type == "listed_for_sale" and e.date >= cutoff:
            last_listing_idx = i
            break
    if last_listing_idx is None:
        return None

    listing = events[last_listing_idx]
    after = events[last_listing_idx + 1:]

    removed = [e for e in after if e.event_type == "listing_removed"]
    if not removed:
        return None  # shouldn't happen given the open-cycle check above, but defensive

    removed_ev = removed[-1]
    dom = (removed_ev.date - listing.date).days
    return {
        "listed_date": listing.date.strftime("%Y-%m-%d"),
        "removed_date": removed_ev.date.strftime("%Y-%m-%d"),
        "last_price": listing.price,
        "dom_days": dom,
        "pattern": "listing_removed_no_sale",
    }


def detect_price_decrease_struggle(
    events: list[ListingEvent],
    lookback_years: float = 1.5,
) -> Optional[dict]:
    """
    Property has been listed with multiple price drops and no sale —
    the seller is actively motivated but can't find the market.
    """
    now = datetime.utcnow()
    cutoff = now.replace(year=now.year - int(lookback_years))
    events = sorted(events, key=lambda e: e.date)

    # Get most recent listing cycle
    last_listing_idx = None
    for i in range(len(events) - 1, -1, -1):
        if events[i].event_type == "listed_for_sale" and events[i].date >= cutoff:
            last_listing_idx = i
            break
    if last_listing_idx is None:
        return None

    after = events[last_listing_idx + 1:]
    if any(e.event_type == "sold" for e in after):
        return None

    drops = [e for e in after if e.event_type == "price_change" and e.price]
    if len(drops) < 2:
        return None

    initial_price = events[last_listing_idx].price or 0
    final_price = drops[-1].price or 0
    if initial_price and final_price and final_price < initial_price:
        drop_pct = (initial_price - final_price) / initial_price * 100
        return {
            "listed_date": events[last_listing_idx].date.strftime("%Y-%m-%d"),
            "initial_price": initial_price,
            "current_price": final_price,
            "drop_pct": round(drop_pct, 1),
            "price_reductions": len(drops),
            "pattern": "price_struggle_no_sale",
        }
    return None


# ═══════════════════════════════════════════════════════════════════════
# PRODUCTION-SCRAPER NOTES (not executed in this session)
# ═══════════════════════════════════════════════════════════════════════
"""
For bulk scraping at ZIP scale (6,000+ parcels per run):

1. Use Serper/Google Custom Search for zpid discovery:
     query = f'site:zillow.com "{address}" "{zip}"'
     Extract /homedetails/.../<zpid>_zpid/ from results

2. Cache zpid per parcel PIN in owners_db. This is stable — only needs
   refresh when a property changes addresses (rare) or a new parcel appears.

3. For actual page fetches, use ScraperAPI / Bright Data / Zyte
   (rotating residential IPs + headless-browser rendering):
     - ScraperAPI: ~$49/mo for 100k API calls, plenty for daily per-ZIP
     - Bright Data: higher cost, better reliability
     - Zyte Smart Proxy Manager: middle

4. Parse with `parse_price_history_from_markdown` on the server-rendered HTML
   (or pull JSON from window.__INITIAL_STATE__ which Zillow embeds).

5. Incremental daily: only re-fetch properties whose last-checked is > 7d
   OR that we've detected a state change for. Saves 95% of bandwidth.

6. Fallback chain:
     Zillow (primary) → Realtor.com (some data) → Trulia (same as Zillow group)
     Redfin returns 403 to unauth'd scrapers — needs different approach.

Estimated cost for full 98004 coverage on daily refresh:
  - Initial: 6,000 zpid discoveries × 1 Serper credit = $3
  - Ongoing: ~1,000 active fetches/day × $0.001/fetch = $1/day = $30/mo
  - All in: ~$50/mo per ZIP for daily-fresh MLS-equivalent coverage
"""
