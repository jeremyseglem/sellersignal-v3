"""
Renewal notifier — background task that emails agents whose territory
subscription's 90-day commitment is approaching its cancel_at.

Three reminder windows: T-30 (advance notice), T-7 (urgency), T-1 (last call).
Each window fires once per (territory, window). State is tracked in the
renewal_notified_{30d,7d,1d}_at columns on agent_territories_v3 — once set,
that window will never fire again for that territory. When the agent renews
and Stripe pushes cancel_at out by another 90 days, the columns are reset
to NULL (in the renew endpoint) so the next cycle's reminders can fire.

Cadence: once per day. The notification windows are 1-3 days wide each
(28-32 days, 5-8 days, 0-2 days), giving the task forgiveness if a tick
is skipped — but a missed window past the wide edge stays missed (we
don't backfill T-30 emails 25 days into the commitment).

Disabled (skipped) automatically if RESEND_API_KEY is not set; the task
still loops so a later env update flips it on without a redeploy.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import stripe

from backend.api.db import get_supabase_client
from backend.lib import email as email_lib
from backend.services import stripe_service


log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

TICK_INTERVAL_HOURS = int(os.environ.get("RENEWAL_NOTIFIER_TICK_HOURS", "24"))
STARTUP_DELAY       = 60   # seconds — wait after boot before first tick
MAX_BACKOFF_SECS    = 1800  # 30 min on repeated errors

# Public URL used in renewal CTAs.
SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://sellersignal.co")

# Window boundaries (inclusive). Days until cancel_at.
#   T-30 window: cancel_at is 28..32 days out
#   T-7  window: cancel_at is 5..8 days out
#   T-1  window: cancel_at is 0..2 days out
WINDOWS = [
    {"key": "30d", "label": "T-30", "min": 28, "max": 32, "column": "renewal_notified_30d_at"},
    {"key": "7d",  "label": "T-7",  "min":  5, "max":  8, "column": "renewal_notified_7d_at"},
    {"key": "1d",  "label": "T-1",  "min":  0, "max":  2, "column": "renewal_notified_1d_at"},
]


# ── Email templates ──────────────────────────────────────────────────────

def _render_email(window_key: str, agent_name: str, zip_code: str,
                  brokerage: Optional[str], cancel_at_iso: str) -> tuple[str, str, str]:
    """
    Returns (subject, html_body, text_body) for the given window.
    Tone scales with urgency: T-30 advisory, T-7 urgent, T-1 last call.
    """
    cta_url = f"{SITE_URL}/profile?renew=1"
    agent_display = agent_name or "there"
    brokerage_line = f" — {brokerage}" if brokerage else ""

    # Render the cancel date as a friendly format like "August 30, 2026"
    try:
        dt = datetime.fromisoformat(cancel_at_iso.replace("Z", "+00:00"))
        date_friendly = dt.strftime("%B %-d, %Y")
    except Exception:
        date_friendly = cancel_at_iso

    if window_key == "30d":
        subject = f"Your {zip_code} territory renews in 30 days"
        lede = (
            f"Hi {agent_display}, your territory subscription for {zip_code}"
            f"{brokerage_line} renews in 30 days, on {date_friendly}. "
            f"Renew now to extend your exclusive access by another 3 months."
        )
        cta = "Renew now"
    elif window_key == "7d":
        subject = f"{zip_code} expires in 7 days — renew to keep your territory"
        lede = (
            f"Hi {agent_display}, your exclusive access to {zip_code}"
            f"{brokerage_line} ends in 7 days, on {date_friendly}. "
            f"After that, the territory opens up to other agents. "
            f"Renew now to lock in another 3 months."
        )
        cta = "Renew {zip_code}".format(zip_code=zip_code)
    else:  # 1d
        subject = f"Final notice: {zip_code} expires tomorrow"
        lede = (
            f"Hi {agent_display}, this is your final reminder. "
            f"Your exclusive access to {zip_code}{brokerage_line} ends "
            f"tomorrow, on {date_friendly}. "
            f"If you don't renew, {zip_code} will become available to "
            f"other agents at midnight."
        )
        cta = "Renew now to keep your territory"

    html_body = f"""
<!doctype html>
<html>
<body style="font-family: Georgia, 'Times New Roman', serif; color: #2a2620; max-width: 560px; margin: 0 auto; padding: 32px 24px; line-height: 1.6;">
  <div style="font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: #8c6d3a; font-weight: 600; font-family: -apple-system, sans-serif; margin-bottom: 12px;">
    Subscription Renewal
  </div>
  <h1 style="font-size: 24px; font-weight: 600; margin: 0 0 18px 0; color: #2a2620;">
    {subject}
  </h1>
  <p style="font-size: 15px; margin: 0 0 24px 0;">
    {lede}
  </p>
  <p style="margin: 28px 0;">
    <a href="{cta_url}"
       style="display: inline-block; padding: 12px 28px; background: #8c6d3a; color: #fff; text-decoration: none; font-family: -apple-system, sans-serif; font-size: 14px; font-weight: 600; border-radius: 4px;">
      {cta}
    </a>
  </p>
  <p style="font-size: 13px; color: #6a5d4d; font-style: italic; margin-top: 32px; border-top: 1px solid #e6dfd2; padding-top: 16px;">
    Questions? Just reply to this email.
  </p>
  <p style="font-size: 11px; color: #9a8c78; margin-top: 24px;">
    SellerSignal &middot; <a href="{SITE_URL}" style="color: #8c6d3a;">sellersignal.co</a>
  </p>
</body>
</html>
""".strip()

    text_body = (
        f"{subject}\n\n"
        f"{lede}\n\n"
        f"Renew: {cta_url}\n\n"
        f"Questions? Just reply to this email.\n\n"
        f"SellerSignal — sellersignal.co"
    )

    return subject, html_body, text_body


# ── Core tick ────────────────────────────────────────────────────────────

def _due_window(days_until_cancel: int, territory_row: dict) -> Optional[dict]:
    """
    Returns the first WINDOW dict whose range contains days_until_cancel
    AND whose column on the territory row is still NULL. If multiple
    windows are due (e.g., the task missed a tick and now both T-7 and
    T-1 are eligible), returns the most-urgent unfilled one.
    """
    for window in WINDOWS:
        if not (window["min"] <= days_until_cancel <= window["max"]):
            continue
        if territory_row.get(window["column"]) is not None:
            continue
        return window
    return None


def _process_one_territory(territory_row: dict) -> str:
    """
    For one active territory, check Stripe for cancel_at, decide if a
    notification window is due, send if so, mark the row. Returns a
    short status string for the tick log.
    """
    sub_id = territory_row.get("stripe_subscription_id")
    zip_code = territory_row.get("zip_code")
    agent_id = territory_row.get("agent_id")

    if not sub_id:
        # Beta-claimed territories have no Stripe subscription — skip silently.
        return f"{zip_code}: no subscription (beta)"

    try:
        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        sub = stripe.Subscription.retrieve(sub_id)
    except KeyError:
        return f"{zip_code}: STRIPE_SECRET_KEY not set"
    except stripe.error.StripeError as e:
        log.warning("[renewal-notifier] Stripe error on sub %s: %s", sub_id, e)
        return f"{zip_code}: stripe error"

    cancel_at = sub.cancel_at
    if not cancel_at:
        return f"{zip_code}: no cancel_at on sub {sub_id}"

    now_ts = int(time.time())
    days_until_cancel = (cancel_at - now_ts) // 86400

    window = _due_window(days_until_cancel, territory_row)
    if not window:
        return f"{zip_code}: no window due (t-{days_until_cancel} days)"

    # Look up agent profile for email + name.
    supa = get_supabase_client()
    if supa is None:
        return f"{zip_code}: supabase unavailable"

    prof = (
        supa.table("agent_profiles_v3")
            .select("email, full_name, brokerage")
            .eq("id", agent_id)
            .single()
            .execute()
    )
    if not prof.data:
        return f"{zip_code}: profile not found for {agent_id}"

    email_addr = prof.data.get("email")
    if not email_addr:
        return f"{zip_code}: no email on profile {agent_id}"

    cancel_iso = datetime.fromtimestamp(cancel_at, tz=timezone.utc).isoformat()
    subject, html, text = _render_email(
        window_key=window["key"],
        agent_name=prof.data.get("full_name") or "",
        zip_code=zip_code,
        brokerage=prof.data.get("brokerage"),
        cancel_at_iso=cancel_iso,
    )

    result = email_lib.send_email(
        to=email_addr,
        subject=subject,
        html_body=html,
        text_body=text,
        tags=["renewal", f"renewal-{window['key']}"],
    )

    if not result:
        # send_email logs the reason. Don't mark notified — we want to
        # retry on the next tick.
        return f"{zip_code}: send failed (window {window['label']})"

    # Mark notified so this window never fires again for this period.
    try:
        supa.table("agent_territories_v3").update({
            window["column"]: datetime.now(timezone.utc).isoformat(),
        }).eq("id", territory_row["id"]).execute()
    except Exception:
        log.exception(
            "[renewal-notifier] sent email to %s but failed to mark %s — "
            "MAY DOUBLE-SEND ON NEXT TICK",
            email_addr, window["column"],
        )
        return f"{zip_code}: sent {window['label']}, mark failed"

    log.info(
        "[renewal-notifier] Sent %s reminder for %s to %s",
        window["label"], zip_code, email_addr,
    )
    return f"{zip_code}: sent {window['label']} to {email_addr}"


async def _one_tick() -> dict:
    """Run one notification sweep. Returns a summary dict for the log."""
    supa = get_supabase_client()
    if supa is None:
        return {"error": "supabase unavailable"}

    # Pull every active territory with a subscription. Cheap query —
    # at scale this is still O(thousands of rows), not enough to
    # justify a stricter pre-filter.
    res = (
        supa.table("agent_territories_v3")
            .select("id, agent_id, zip_code, stripe_subscription_id, "
                    "renewal_notified_30d_at, renewal_notified_7d_at, "
                    "renewal_notified_1d_at")
            .eq("status", "active")
            .not_.is_("stripe_subscription_id", "null")
            .execute()
    )
    territories = res.data or []

    sent = 0
    skipped = 0
    errors = 0
    details = []
    for row in territories:
        try:
            outcome = _process_one_territory(row)
            details.append(outcome)
            if "sent" in outcome:
                sent += 1
            else:
                skipped += 1
        except Exception:
            log.exception("[renewal-notifier] error processing %s", row.get("zip_code"))
            errors += 1

    return {
        "checked": len(territories),
        "sent":    sent,
        "skipped": skipped,
        "errors":  errors,
        "details": details[:50],  # cap log line size
    }


# ── Loop ─────────────────────────────────────────────────────────────────

async def renewal_notifier_loop():
    """Public entrypoint. Wired into FastAPI's lifespan in backend/main.py."""
    log.info(
        "[renewal-notifier] starting (tick every %dh, startup delay %ds)",
        TICK_INTERVAL_HOURS, STARTUP_DELAY,
    )
    await asyncio.sleep(STARTUP_DELAY)

    backoff = TICK_INTERVAL_HOURS * 3600

    while True:
        try:
            summary = await _one_tick()
            log.info("[renewal-notifier] tick: %s", summary)
            backoff = TICK_INTERVAL_HOURS * 3600  # reset
        except asyncio.CancelledError:
            log.info("[renewal-notifier] cancelled — shutting down")
            raise
        except Exception:
            log.exception("[renewal-notifier] tick crashed; backing off")
            backoff = min(backoff * 2, MAX_BACKOFF_SECS)

        await asyncio.sleep(backoff)
