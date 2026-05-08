"""
Territory release notifications API.

  POST /api/notifications/subscribe
       body: { zip_code, email }
       Subscribes an email to be notified when the given ZIP releases.

  GET /api/notifications/unsubscribe?t=<unsubscribe_token>
       Marks the matching subscription as notified (effectively
       unsubscribed without deleting the audit row).

  GET /api/notifications/zip/{zip_code}/queue-size
       Returns how many people are waiting for this ZIP. Public —
       agents can see "12 others are waiting" on a claimed territory
       without any PII leaking.

The actual email send happens elsewhere (when a territory releases).
This module only manages the queue.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

from backend.api.db import get_supabase_client

log = logging.getLogger(__name__)

router = APIRouter()

ZIP_RE = re.compile(r"^\d{5}$")


class SubscribeRequest(BaseModel):
    zip_code: str = Field(..., min_length=5, max_length=5)
    email:    EmailStr


@router.post("/subscribe")
async def subscribe_to_zip(payload: SubscribeRequest, request: Request):
    """
    Add an email to the wait list for a ZIP. Idempotent — repeat
    subscriptions for the same (zip, email) silently dedup via the
    partial unique index, and return ok=True regardless.
    """
    if not ZIP_RE.match(payload.zip_code):
        raise HTTPException(400, "zip_code must be 5 digits")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Verify the ZIP is one we actually cover. Subscribing to a ZIP we
    # don't recognize is a UX hint that something's off.
    cov = (supa.table("zip_coverage_v3")
           .select("zip_code, status")
           .eq("zip_code", payload.zip_code)
           .limit(1)
           .execute())
    if not cov.data:
        raise HTTPException(404, f"ZIP {payload.zip_code} is not in our coverage")

    # Capture lightweight context for fraud / abuse review later. Not
    # surfaced to agents and not used by trigger logic.
    user_agent = (request.headers.get("user-agent") or "")[:500]
    forwarded_for = request.headers.get("x-forwarded-for") or ""
    ip_address = forwarded_for.split(",")[0].strip() or (
        request.client.host if request.client else None
    )

    row = {
        "zip_code":   payload.zip_code,
        "email":      str(payload.email),
        "source":     "territories_map",
        "user_agent": user_agent or None,
        "ip_address": ip_address,
    }

    # Upsert — but the unique index is partial (notified_at IS NULL),
    # so a plain insert that conflicts will raise. Catch the duplicate
    # error gracefully and still return ok=True (the user just subscribed
    # twice for the same ZIP — fine, it's already in the queue).
    try:
        result = supa.table("zip_release_notifications").insert(row).execute()
        was_new = bool(result.data)
        log.info("[notify] subscribed %s to %s (new=%s)",
                 row["email"], payload.zip_code, was_new)
        return {"ok": True, "already_subscribed": not was_new}
    except Exception as e:
        # Duplicate-key violation = already subscribed. supabase-py
        # surfaces these with a string match in the error message.
        msg = str(e).lower()
        if "duplicate" in msg or "23505" in msg or "unique" in msg:
            return {"ok": True, "already_subscribed": True}
        log.exception("[notify] subscribe failed: %s", e)
        raise HTTPException(500, "Subscribe failed")


@router.get("/unsubscribe")
async def unsubscribe(t: str = Query(..., min_length=8, max_length=64)):
    """
    Mark a subscription as notified (which removes it from the active
    queue per the partial index). Public endpoint — anyone with the
    token can unsubscribe themselves. Returns a tiny HTML confirmation
    so the email-clicker sees something useful.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (supa.table("zip_release_notifications")
                  .update({"notified_at": now_iso})
                  .eq("unsubscribe_token", t)
                  .is_("notified_at", "null")
                  .execute())
        updated = len(result.data or [])
    except Exception as e:
        log.exception("[notify] unsubscribe failed: %s", e)
        raise HTTPException(500, "Unsubscribe failed")

    # Return a friendly HTML page. Email clients open in a browser, so
    # giving them visual confirmation is much better than a JSON 200.
    if updated:
        body = (
            "<h2>You're unsubscribed.</h2>"
            "<p>You won't be notified about that ZIP again.</p>"
        )
    else:
        # Either bad token or already unsubscribed — same UI either way.
        body = (
            "<h2>Already unsubscribed.</h2>"
            "<p>This subscription was already cleared. No action needed.</p>"
        )

    from fastapi.responses import HTMLResponse
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SellerSignal — Unsubscribed</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ background: #F5F0EB; color: #2C2418;
         font-family: 'DM Sans', system-ui, sans-serif;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; padding: 20px; }}
  .card {{ background: #fff; border: 1px solid #DCD2C5; border-radius: 4px;
           padding: 32px 36px; max-width: 480px; box-shadow: 0 8px 24px rgba(44,36,24,0.08); }}
  h2 {{ font-family: 'Playfair Display', serif; font-weight: 400;
        font-size: 26px; margin: 0 0 12px; color: #2C2418; }}
  p {{ font-size: 15px; line-height: 1.5; color: #6B5D47; }}
  a {{ color: #8B6914; text-decoration: none; font-weight: 500; }}
</style>
</head>
<body><div class="card">{body}<p style="margin-top:20px;"><a href="https://sellersignal.co">Return to SellerSignal</a></p></div></body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@router.get("/zip/{zip_code}/queue-size")
async def queue_size_for_zip(zip_code: str):
    """
    How many people are waiting for this ZIP. Public — useful UX hint
    on the territories map ("8 others are waiting") without leaking
    who they are.
    """
    if not ZIP_RE.match(zip_code):
        raise HTTPException(400, "zip_code must be 5 digits")

    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    try:
        r = (supa.table("zip_release_notifications")
             .select("id", count="exact")
             .eq("zip_code", zip_code)
             .is_("notified_at", "null")
             .limit(1)
             .execute())
        return {"zip_code": zip_code, "queue_size": r.count or 0}
    except Exception as e:
        log.exception("[notify] queue-size lookup failed: %s", e)
        raise HTTPException(500, "Lookup failed")
