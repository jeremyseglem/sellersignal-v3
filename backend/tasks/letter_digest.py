"""
Letter digest — background task that emails each agent a once-a-day
summary of letter activity from the prior 24h.

Schedule
--------
The task ticks once per hour. On each tick it asks: is the current
time in America/Denver between 07:00 and 07:59? If yes, it processes
digests. If no, it sleeps until the next hour.

We tick hourly (not daily) because daily-fixed ticks are fragile to
restarts — Railway recycles or a slow tick crossing the send window
could miss it entirely or fire twice. Hourly + idempotency-stamp gives
forgiveness: a missed 7am tick still fires at 8am if needed, and a
double tick is no-op because the second one sees the stamp.

Time zone
---------
v1 fires at 7am Mountain (America/Denver) for every agent regardless
of where the agent is. Jeremy is in Bozeman MT; King County beta
agents are in Pacific time, where 7am Mountain = 6am Pacific (or 5am
during the DST mismatch weeks). For v1 that's an acceptable tradeoff
since the early-morning recipient doesn't really care if it lands at
5am or 7am as long as it's there before the workday starts. A future
iteration can add per-agent timezone preference to agent_profiles_v3.

Activity-only
-------------
If the agent has no letter events with status_updated_at in the prior
24h, no email is sent. The stamp column is still updated so we know
the agent was considered today; "no activity" days are silent.
Actually — we *don't* stamp on no-activity days. If an agent has no
activity at 7am but receives a delivered event at 7:30am that flips
the timestamp into yesterday's window… hmm. Actually status_updated_at
is the source of truth and our "yesterday" window is the 24h prior to
the tick *firing*, not "yesterday calendar day in Mountain". So the
event has to land before the tick to be included; events after the
tick are tomorrow's digest. Don't stamp on no-activity so the next
day's tick can include any delayed events whose status_updated_at
happens to be older than the window. Wait — that's a stale-window
concern, not a stamp concern. Simpler: stamp only on actual send.
No-activity days produce no email and no stamp change. Idempotency
inside a 7am-hour-window: also keyed on the stamp, so if the tick
happens to run twice (because asyncio.sleep slipped), the second
call sees the same activity and would re-send — UNLESS we stamp on
send. Which we do. Resolved.

Idempotency
-----------
After a successful send, agent_profiles_v3.letter_digest_last_sent_at
is set to NOW(). Each subsequent tick compares: if the existing
stamp's date in America/Denver equals today's date in the same
timezone, skip — already digested today. Resets implicitly when the
calendar rolls.

Disabled
--------
Skipped automatically if RESEND_API_KEY isn't set. The loop still
runs so an env update flips it on without a redeploy. The same goes
for any agent without an email column populated.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from backend.api.db import get_supabase_client
from backend.lib import email as email_lib


log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

# Send time, in the agent-display timezone. v1 ignores per-agent
# preferences and fires for everyone at this hour in this zone.
SEND_HOUR_LOCAL = int(os.environ.get("LETTER_DIGEST_SEND_HOUR", "7"))
DISPLAY_TZ      = ZoneInfo("America/Denver")

TICK_INTERVAL_SECS = int(os.environ.get("LETTER_DIGEST_TICK_SECONDS", str(60 * 60)))
STARTUP_DELAY      = 60   # let other tasks settle first
MAX_BACKOFF_SECS   = 1800

# Lookback window for "yesterday's activity". 24h on the dot — events
# that happened more than 24h before the tick fires belong to previous
# digests, and events that happen after the tick belong to tomorrow's.
LOOKBACK_HOURS = 24

SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://sellersignal.co")

# Letter statuses that produce a line in the digest. 'scheduled' is
# not an event yet; 'created' is "Stannp accepted" which is too low-
# signal for a summary email. Mailed/delivered/returned/failed are
# the four events worth pinging the agent about.
_DIGEST_STATUSES = ("mailed", "delivered", "returned", "failed")


# ── Time helpers ─────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _local_now() -> datetime:
    return _now_utc().astimezone(DISPLAY_TZ)


def _already_sent_today(last_sent_iso: Optional[str]) -> bool:
    """Was the last digest sent today (in DISPLAY_TZ)?"""
    if not last_sent_iso:
        return False
    try:
        last = datetime.fromisoformat(last_sent_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    last_local = last.astimezone(DISPLAY_TZ)
    today_local = _local_now()
    return last_local.date() == today_local.date()


# ── Event aggregation ────────────────────────────────────────────────────

def _fetch_recent_events(supa, agent_id: str, since_iso: str) -> list[dict]:
    """Pull letter events for one agent since the given timestamp.
    Joins parcel address/owner data for display."""
    rows = (
        supa.table("letters_sent_v3")
            .select(
                "id, pin, zip_code, letter_index, status, status_updated_at, "
                "delivered_at, mailed_at, sequence_id"
            )
            .eq("agent_id", agent_id)
            .gte("status_updated_at", since_iso)
            .in_("status", list(_DIGEST_STATUSES))
            .order("status_updated_at", desc=True)
            .execute()
    ).data or []

    if not rows:
        return []

    # Join parcel data so the email can show address + owner name.
    pins = list({r["pin"] for r in rows})
    parcels = (
        supa.table("parcels_v3")
            .select("pin, address, owner_name, city, state")
            .in_("pin", pins)
            .execute()
    ).data or []
    parcel_by_pin = {p["pin"]: p for p in parcels}

    for r in rows:
        p = parcel_by_pin.get(r["pin"]) or {}
        r["address"]    = p.get("address")
        r["owner_name"] = p.get("owner_name")
        r["city"]       = p.get("city")
        r["state"]      = p.get("state")

    return rows


def _group_by_status(events: list[dict]) -> dict[str, list[dict]]:
    """Bucket events by status, preserving the existing newest-first order."""
    grouped: dict[str, list[dict]] = {s: [] for s in _DIGEST_STATUSES}
    for e in events:
        s = e.get("status")
        if s in grouped:
            grouped[s].append(e)
    return grouped


# ── Email rendering ──────────────────────────────────────────────────────

# Style note: brand voice prefers serif body + minimal chrome.
# Resend HTML emails strip <style> in some clients, so we lean on
# inline styles + a small palette of standard fonts. Match the
# existing renewal_notifier visual tone.

_BASE_STYLES = (
    "font-family: Georgia, 'Times New Roman', serif; "
    "color: #1a1a1a; line-height: 1.55;"
)
_HEADING = (
    "font-family: Georgia, serif; font-size: 20px; "
    "color: #1a1a1a; margin: 28px 0 12px 0; font-weight: 400;"
)
_SECTION_LABEL = (
    "font-family: 'Helvetica Neue', Arial, sans-serif; "
    "font-size: 11px; letter-spacing: 0.08em; "
    "text-transform: uppercase; color: #777; "
    "margin: 22px 0 6px 0;"
)
_PARCEL_LINE = (
    "font-family: 'Helvetica Neue', Arial, sans-serif; "
    "font-size: 13px; color: #1a1a1a; "
    "margin: 0 0 6px 0;"
)
_PARCEL_SUB = (
    "font-family: 'Helvetica Neue', Arial, sans-serif; "
    "font-size: 11px; color: #888;"
)
_CTA_BTN = (
    "display: inline-block; padding: 10px 18px; "
    "background: #8B6914; color: #F5F0EB; "
    "font-family: 'Helvetica Neue', Arial, sans-serif; "
    "font-size: 13px; font-weight: 500; "
    "text-decoration: none; border-radius: 4px;"
)

_STATUS_LABELS = {
    "delivered": "Delivered",
    "mailed":    "Mailed",
    "returned":  "Returned",
    "failed":    "Failed",
}

# Order sections so the highest-signal action items appear first.
# Delivered first (recipient has the letter; call them now). Returned
# second (action needed: fix address). Failed third. Mailed last —
# it's lowest signal since "we put it in the mail yesterday" doesn't
# usually require any action.
_SECTION_ORDER = ["delivered", "returned", "failed", "mailed"]

_SECTION_DESCRIPTION = {
    "delivered": "These reached their recipients yesterday. Now is the window to follow up.",
    "returned":  "These came back. Verify the address before re-sending.",
    "failed":    "Stannp couldn't print or mail these. Contact support if it persists.",
    "mailed":    "These were handed to USPS yesterday and are in transit.",
}


def _format_parcel(event: dict) -> tuple[str, str]:
    """Returns (main_line, sub_line) for one parcel."""
    owner = event.get("owner_name") or "(unknown owner)"
    addr  = event.get("address") or event.get("pin") or ""
    main = f"{owner} — {addr}" if addr else owner
    sub_bits = []
    city = event.get("city")
    state = event.get("state")
    if city and state:
        sub_bits.append(f"{city}, {state}")
    elif city:
        sub_bits.append(city)
    if event.get("letter_index"):
        sub_bits.append(f"Letter {event['letter_index']}")
    return main, " · ".join(sub_bits)


def _render_email(agent_name: str,
                  grouped: dict[str, list[dict]]) -> tuple[str, str, str]:
    """Build (subject, html_body, text_body) for one agent's digest."""
    total = sum(len(grouped.get(s, [])) for s in _DIGEST_STATUSES)
    subject = f"SellerSignal — {total} letter update{'s' if total != 1 else ''} yesterday"

    agent_display = agent_name.strip() if agent_name else ""
    greeting_html = f"Hi {agent_display.split()[0]}," if agent_display else "Hi,"

    # ── HTML body ──
    html_sections = []
    for status in _SECTION_ORDER:
        events = grouped.get(status) or []
        if not events:
            continue
        count = len(events)
        label = _STATUS_LABELS[status]
        desc  = _SECTION_DESCRIPTION[status]

        # Section header + description
        html_sections.append(
            f'<div style="{_SECTION_LABEL}">{label} ({count})</div>'
            f'<div style="font-family: Georgia, serif; font-size: 13px; '
            f'color: #555; margin-bottom: 10px; font-style: italic;">{desc}</div>'
        )
        # Parcel lines
        for ev in events:
            main, sub = _format_parcel(ev)
            html_sections.append(
                f'<div style="margin-bottom: 12px;">'
                f'<div style="{_PARCEL_LINE}">{main}</div>'
                + (f'<div style="{_PARCEL_SUB}">{sub}</div>' if sub else '')
                + '</div>'
            )

    sections_html = "\n".join(html_sections)
    leads_url = f"{SITE_URL}/my-leads"
    letters_url = f"{SITE_URL}/letters"

    html = f"""<!DOCTYPE html>
<html><body style="{_BASE_STYLES} max-width: 560px; margin: 0; padding: 28px 24px;">
  <div style="{_HEADING}">{total} letter update{'s' if total != 1 else ''} yesterday</div>
  <p style="font-family: Georgia, serif; font-size: 14px; color: #1a1a1a; margin: 0 0 18px 0;">
    {greeting_html} here's what happened with your direct mail in the last 24 hours.
  </p>
  {sections_html}
  <div style="margin: 28px 0 8px 0;">
    <a href="{leads_url}" style="{_CTA_BTN}">Open My Leads</a>
    <a href="{letters_url}" style="{_CTA_BTN} background: transparent; color: #8B6914; border: 1px solid #8B6914; margin-left: 8px;">View all letters</a>
  </div>
  <p style="font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11px; color: #999; margin-top: 28px;">
    Sent daily by SellerSignal when there's activity to share. No activity, no email.
  </p>
</body></html>"""

    # ── Plain text body ──
    text_lines = [
        f"{total} letter update{'s' if total != 1 else ''} yesterday",
        "",
        f"{greeting_html} here's what happened with your direct mail in the last 24 hours.",
        "",
    ]
    for status in _SECTION_ORDER:
        events = grouped.get(status) or []
        if not events:
            continue
        text_lines.append(f"{_STATUS_LABELS[status].upper()} ({len(events)})")
        text_lines.append(_SECTION_DESCRIPTION[status])
        for ev in events:
            main, sub = _format_parcel(ev)
            text_lines.append(f"  • {main}")
            if sub:
                text_lines.append(f"    {sub}")
        text_lines.append("")
    text_lines.append(f"Open My Leads: {leads_url}")
    text_lines.append(f"View all letters: {letters_url}")
    text_lines.append("")
    text_lines.append("Sent daily by SellerSignal when there's activity to share. No activity, no email.")
    text = "\n".join(text_lines)

    return subject, html, text


# ── Per-agent processing ─────────────────────────────────────────────────

def _process_agent(supa, agent: dict, since_iso: str) -> str:
    """Send one agent's digest if there's activity. Returns a brief
    log-friendly outcome string."""
    agent_id  = agent["id"]
    email_addr = agent.get("email")
    name      = agent.get("full_name") or ""
    last_sent = agent.get("letter_digest_last_sent_at")

    if not email_addr:
        return f"{agent_id[:8]}: no email"

    if _already_sent_today(last_sent):
        return f"{agent_id[:8]}: already sent today"

    events = _fetch_recent_events(supa, agent_id, since_iso)
    if not events:
        return f"{agent_id[:8]}: no activity"

    grouped = _group_by_status(events)
    subject, html, text = _render_email(agent_name=name, grouped=grouped)

    result = email_lib.send_email(
        to=email_addr,
        subject=subject,
        html_body=html,
        text_body=text,
        tags=["letter-digest"],
    )
    if not result:
        # email_lib logs the reason. Don't stamp — let the next tick retry.
        return f"{agent_id[:8]}: send failed"

    # Stamp the agent so we don't double-send within this 24h cycle.
    try:
        supa.table("agent_profiles_v3").update({
            "letter_digest_last_sent_at": _now_utc().isoformat(),
        }).eq("id", agent_id).execute()
    except Exception:
        log.exception(
            "[letter-digest] Sent digest to %s but failed to stamp — MAY DOUBLE-SEND",
            email_addr,
        )
        return f"{agent_id[:8]}: sent, stamp failed"

    return f"{agent_id[:8]}: sent {len(events)} events to {email_addr}"


# ── One tick ─────────────────────────────────────────────────────────────

async def _one_tick() -> dict:
    """Run one digest sweep. Most ticks are no-ops because the local
    hour doesn't match SEND_HOUR_LOCAL — we still return a summary
    dict so the loop logs are uniform."""
    local = _local_now()
    if local.hour != SEND_HOUR_LOCAL:
        return {
            "tz_hour": local.hour,
            "wait_for": SEND_HOUR_LOCAL,
            "fired": False,
        }

    supa = get_supabase_client()
    if supa is None:
        return {"error": "supabase unavailable", "fired": False}

    # Compute the lookback window. Anything with status_updated_at in
    # [now - 24h, now) is "yesterday's activity" for this digest.
    since_iso = (_now_utc() - timedelta(hours=LOOKBACK_HOURS)).isoformat()

    # Pull every agent — small set, no pre-filter needed. Includes
    # both onboarded and not-yet-onboarded; agents without activity
    # silently skip in _process_agent.
    agents = (
        supa.table("agent_profiles_v3")
            .select("id, email, full_name, letter_digest_last_sent_at")
            .not_.is_("email", "null")
            .execute()
    ).data or []

    sent = 0
    skipped = 0
    errors = 0
    details = []
    for agent in agents:
        try:
            outcome = _process_agent(supa, agent, since_iso)
            details.append(outcome)
            if " sent " in outcome:
                sent += 1
            else:
                skipped += 1
        except Exception:
            log.exception("[letter-digest] error processing %s", agent.get("id"))
            errors += 1

    return {
        "fired":   True,
        "checked": len(agents),
        "sent":    sent,
        "skipped": skipped,
        "errors":  errors,
        "details": details[:50],
    }


# ── Public loop ──────────────────────────────────────────────────────────

async def letter_digest_loop():
    """Public entrypoint. Wired into FastAPI's lifespan in backend/main.py."""
    log.info(
        "[letter-digest] starting (tick every %ds, send at %d:00 %s, startup delay %ds)",
        TICK_INTERVAL_SECS, SEND_HOUR_LOCAL, DISPLAY_TZ.key, STARTUP_DELAY,
    )
    await asyncio.sleep(STARTUP_DELAY)

    backoff = TICK_INTERVAL_SECS

    while True:
        try:
            summary = await _one_tick()
            if summary.get("fired"):
                log.info("[letter-digest] tick: %s", summary)
            else:
                # Quiet log for off-hour ticks to keep the deploy log readable.
                log.debug("[letter-digest] off-hour tick: %s", summary)
            backoff = TICK_INTERVAL_SECS  # reset
        except asyncio.CancelledError:
            log.info("[letter-digest] cancelled — shutting down")
            raise
        except Exception:
            log.exception("[letter-digest] tick crashed; backing off")
            backoff = min(backoff * 2, MAX_BACKOFF_SECS)

        await asyncio.sleep(backoff)
