"""
Email helper — sends transactional email via Resend.

Why Resend: simplest API in the space, generous free tier (3K emails/month
on the free plan, plenty for beta). No SMTP juggling, no SES sandbox. If
you outgrow it the API surface is portable to any HTTP-API mailer
(Postmark, SendGrid, etc.) by swapping the request body.

Required env vars (all optional in dev — missing key = no-op):
  RESEND_API_KEY        — your Resend API key (re_...)
  RESEND_FROM_EMAIL     — from address, e.g. "alerts@sellersignal.co"
                          (must be on a verified domain in Resend)
  RESEND_FROM_NAME      — display name, defaults to "SellerSignal"

Usage:
  from backend.lib.email import send_email
  result = send_email(
      to="agent@example.com",
      subject="98033 just opened",
      html_body="<p>The Kirkland territory you wanted is now available...</p>",
      text_body="The Kirkland territory you wanted is now available...",
  )
  if result and result.get("id"):
      log.info("sent email %s", result["id"])
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _config() -> Optional[dict]:
    """Read env config. Returns None if the API key isn't set."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return None
    return {
        "api_key":    api_key,
        "from_email": os.environ.get("RESEND_FROM_EMAIL", "alerts@sellersignal.co"),
        "from_name":  os.environ.get("RESEND_FROM_NAME",  "SellerSignal"),
    }


def email_configured() -> bool:
    """Cheap predicate for callers that want to short-circuit when email is off."""
    return _config() is not None


def send_email(
    to:        str | list[str],
    subject:   str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to:  Optional[str] = None,
    tags:      Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Send a single email. Returns the Resend response dict on success
    (which contains an `id` field), or None if email isn't configured
    or the send failed.

    Never raises — failures are logged. Callers should treat None as
    "send didn't happen" without inferring why.
    """
    cfg = _config()
    if not cfg:
        log.warning("[email] RESEND_API_KEY not set; would have sent to=%s subj=%r", to, subject)
        return None

    if isinstance(to, str):
        to = [to]
    if not to:
        log.warning("[email] empty recipient list, skipping")
        return None

    payload = {
        "from":    f"{cfg['from_name']} <{cfg['from_email']}>",
        "to":      to,
        "subject": subject,
        "html":    html_body,
    }
    if text_body:
        payload["text"] = text_body
    if reply_to:
        payload["reply_to"] = reply_to
    if tags:
        # Resend accepts a list of {name, value} tag dicts; we model
        # tags as flat strings here for caller simplicity.
        payload["tags"] = [{"name": "category", "value": t} for t in tags]

    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                RESEND_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
        if r.status_code >= 400:
            log.warning("[email] send failed: %s %s — to=%s", r.status_code, r.text[:200], to)
            return None
        return r.json()
    except Exception as e:
        log.exception("[email] send raised: %s — to=%s", e, to)
        return None
