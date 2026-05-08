"""
Territory release notifications — trigger.

When a ZIP transitions from claimed to available (an agent gives up
their territory, subscription lapses, etc.), call notify_zip_release()
to email everyone on the wait list.

Currently has no automatic caller — the unclaim/release endpoint
doesn't exist yet (no agent has needed it in private beta). When
that endpoint is built, add one line:

    from backend.lib.territory_notify import notify_zip_release
    await notify_zip_release(zip_code)

Until then, the admin test endpoint
POST /api/admin/test-release-notification/{zip} can fire it manually
against the live wait list (or a single test email).

Design notes:
  - Idempotent on retry. If the function is called twice for the
    same ZIP back-to-back, the second call sees the rows are already
    marked notified_at and skips them. So a botched deploy or a
    retry storm doesn't double-email subscribers.
  - All-or-nothing per row. If the email send fails for one
    subscriber, that row is left un-notified and will be retried on
    the next call. Successful sends are marked one-at-a-time.
  - No batching. Resend's API supports it but simpler to send one
    email per call — wait lists per ZIP will be small (likely
    single-digit) and parallelism isn't worth the complexity.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.api.db import get_supabase_client
from backend.lib.email import send_email, email_configured

log = logging.getLogger(__name__)


# ── Email template ────────────────────────────────────────────────────────
SUBJECT_TMPL = "{zip} just opened — claim before someone else does"

HTML_TMPL = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ background: #F5F0EB; margin: 0; padding: 32px 16px;
         font-family: 'DM Sans', -apple-system, sans-serif;
         color: #2C2418; }}
  .wrap {{ max-width: 540px; margin: 0 auto;
           background: #fff; border: 1px solid #DCD2C5;
           box-shadow: 0 8px 24px rgba(44,36,24,0.06); }}
  .accent {{ height: 3px; background: #4F7B57; }}
  .pad   {{ padding: 32px 36px; }}
  .crumb {{ font-size: 11px; text-transform: uppercase;
           letter-spacing: 2px; color: #9A8C76; font-weight: 600;
           margin-bottom: 12px; }}
  h1 {{ font-family: 'Playfair Display', Georgia, serif;
        font-weight: 400; font-size: 30px; line-height: 1.2;
        margin: 0 0 16px; color: #2C2418; }}
  h1 strong {{ color: #8B6914; font-weight: 500; font-style: italic; }}
  p  {{ font-family: 'Source Serif 4', Georgia, serif;
        font-size: 16px; line-height: 1.55; color: #3A3023;
        margin: 0 0 18px; }}
  .stats {{ background: #EDE5DC; padding: 16px 20px;
            border-radius: 2px; margin: 18px 0 24px;
            display: table; width: 100%; box-sizing: border-box; }}
  .stat-row {{ display: table-row; }}
  .stat-cell {{ display: table-cell; padding: 6px 0;
                font-family: 'DM Sans', sans-serif; font-size: 13px; }}
  .stat-cell.k {{ color: #6B5D47; }}
  .stat-cell.v {{ color: #2C2418; font-weight: 600; text-align: right; }}
  .cta {{ display: block; text-align: center; padding: 16px 24px;
          background: #8B6914; color: #F5F0EB !important;
          text-decoration: none; font-family: 'DM Sans', sans-serif;
          font-size: 14px; font-weight: 600; text-transform: uppercase;
          letter-spacing: 2px; border-radius: 2px; }}
  .urgency {{ font-style: italic; font-family: 'Source Serif 4', serif;
              color: #6B5D47; font-size: 13px; line-height: 1.5;
              margin-top: 12px; }}
  .foot {{ padding: 18px 36px 24px; background: #EDE5DC;
           font-family: 'DM Sans', sans-serif; font-size: 11px;
           color: #9A8C76; line-height: 1.6; }}
  .foot a {{ color: #6B5D47; text-decoration: underline; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="accent"></div>
    <div class="pad">
      <div class="crumb">Territory release</div>
      <h1><strong>{zip}</strong> just opened.</h1>
      <p>The territory you asked us to watch in {city}, WA is now available to claim.
      One agent, exclusive — first agent to claim it locks it in.</p>

      <div class="stats">
        <div class="stat-row">
          <div class="stat-cell k">Parcels in territory</div>
          <div class="stat-cell v">{parcel_count}</div>
        </div>
        <div class="stat-row">
          <div class="stat-cell k">Call now leads this week</div>
          <div class="stat-cell v">{call_now}</div>
        </div>
      </div>

      <a href="{claim_url}" class="cta">Claim {zip}</a>

      <p class="urgency">If another agent claims it first, you'll get this email next time it opens.
      We'll keep watching for you.</p>
    </div>
    <div class="foot">
      You're receiving this because you asked us to notify you when {zip} became available.<br>
      <a href="{unsubscribe_url}">Unsubscribe from {zip} alerts</a> &nbsp;·&nbsp; SellerSignal &nbsp;·&nbsp;
      <a href="https://sellersignal.co">sellersignal.co</a>
    </div>
  </div>
</body>
</html>"""

TEXT_TMPL = """\
{zip} just opened.

The territory you asked us to watch in {city}, WA is now available to claim.
One agent, exclusive — first agent to claim it locks it in.

  Parcels in territory:       {parcel_count}
  Call now leads this week:   {call_now}

Claim it: {claim_url}

If another agent claims it first, you'll get this email next time it opens.
We'll keep watching for you.

—
You're receiving this because you asked us to notify you when {zip} became available.
Unsubscribe from {zip} alerts: {unsubscribe_url}

SellerSignal · sellersignal.co
"""


def _coverage_for(zip_code: str) -> dict:
    """Pull stats for the ZIP from coverage. Used to fill the email template."""
    supa = get_supabase_client()
    if not supa:
        return {}
    try:
        r = (supa.table("zip_coverage_v3")
             .select("zip_code, city, state, parcel_count, current_call_now_count")
             .eq("zip_code", zip_code)
             .limit(1)
             .execute())
        if r.data:
            return r.data[0]
    except Exception as e:
        log.warning("[territory-notify] coverage lookup failed for %s: %s",
                    zip_code, e)
    return {}


def _format_email(subscriber: dict, zip_code: str, coverage: dict) -> dict:
    """Build subject + html + text for one subscriber."""
    base = "https://sellersignal.co"
    claim_url = f"{base}/territories?focus={zip_code}"
    unsubscribe_url = f"{base}/api/notifications/unsubscribe?t={subscriber['unsubscribe_token']}"

    fmt = {
        "zip":            zip_code,
        "city":           coverage.get("city", "your area"),
        "parcel_count":   f"{coverage.get('parcel_count', 0):,}",
        "call_now":       f"{coverage.get('current_call_now_count', 0):,}",
        "claim_url":      claim_url,
        "unsubscribe_url": unsubscribe_url,
    }
    return {
        "subject":   SUBJECT_TMPL.format(**fmt),
        "html_body": HTML_TMPL.format(**fmt),
        "text_body": TEXT_TMPL.format(**fmt),
    }


# ── Public entry points ──────────────────────────────────────────────────
def notify_zip_release(
    zip_code: str,
    *,
    test_email: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Email everyone on the wait list for `zip_code`. Returns a summary.

    Args:
      zip_code   — ZIP that just released.
      test_email — if provided, send to this address instead of the
                   real wait list. The wait list is NOT marked notified.
                   Use for end-to-end testing the email delivery.
      dry_run    — if True, look up subscribers and render emails but
                   don't send or mark notified. Returns the formatted
                   email content for inspection.

    Returns:
      {
        "zip_code":      str,
        "subscribers":   int,
        "sent":          int,
        "failed":        int,
        "skipped":       int,   # already notified or test-mode no-op
        "errors":        [str],
        "preview":       {subject, html, text} | None  (dry_run only)
      }
    """
    out = {
        "zip_code":   zip_code,
        "subscribers": 0,
        "sent":       0,
        "failed":     0,
        "skipped":    0,
        "errors":     [],
        "preview":    None,
    }

    if not email_configured() and not dry_run:
        out["errors"].append("RESEND_API_KEY not set — emails would be no-ops")

    supa = get_supabase_client()
    if not supa:
        out["errors"].append("Database unavailable")
        return out

    coverage = _coverage_for(zip_code)
    if not coverage:
        out["errors"].append(f"ZIP {zip_code} not in coverage table")
        return out

    # If test_email is set, fabricate a one-row "subscriber list"
    # and don't touch the database.
    if test_email:
        fake_sub = {
            "id":                "test",
            "email":             test_email,
            "unsubscribe_token": "test-token-not-real",
        }
        formatted = _format_email(fake_sub, zip_code, coverage)
        out["subscribers"] = 1
        if dry_run:
            out["preview"] = formatted
            out["skipped"] = 1
            return out
        result = send_email(
            to=test_email,
            subject=formatted["subject"],
            html_body=formatted["html_body"],
            text_body=formatted["text_body"],
            tags=["territory_release", "test"],
        )
        if result and result.get("id"):
            out["sent"] = 1
        else:
            out["failed"] = 1
            out["errors"].append("send_email returned no id")
        return out

    # Real subscriber list — only those who haven't been notified yet
    try:
        r = (supa.table("zip_release_notifications")
             .select("id, email, unsubscribe_token")
             .eq("zip_code", zip_code)
             .is_("notified_at", "null")
             .execute())
        subscribers = r.data or []
    except Exception as e:
        out["errors"].append(f"subscriber lookup failed: {type(e).__name__}: {e}")
        return out

    out["subscribers"] = len(subscribers)
    if not subscribers:
        return out

    # In dry-run, render one preview and return without sending or marking
    if dry_run:
        out["preview"] = _format_email(subscribers[0], zip_code, coverage)
        out["skipped"] = len(subscribers)
        return out

    now_iso = datetime.now(timezone.utc).isoformat()

    for sub in subscribers:
        formatted = _format_email(sub, zip_code, coverage)
        result = send_email(
            to=sub["email"],
            subject=formatted["subject"],
            html_body=formatted["html_body"],
            text_body=formatted["text_body"],
            tags=["territory_release"],
        )
        if not result or not result.get("id"):
            out["failed"] += 1
            out["errors"].append(f"send failed for {sub['email']}")
            continue

        # Mark this row notified. Done one at a time so a partial
        # failure doesn't lose track of which sends went through.
        try:
            (supa.table("zip_release_notifications")
             .update({"notified_at": now_iso})
             .eq("id", sub["id"])
             .execute())
        except Exception as e:
            # Email sent but we couldn't mark it. Log loudly — next
            # run will re-send to this address. Acceptable failure
            # mode (better than not sending), but worth knowing.
            log.exception("[territory-notify] sent to %s but couldn't mark notified: %s",
                          sub["email"], e)
            out["errors"].append(f"sent to {sub['email']} but mark failed")
        out["sent"] += 1

    return out
