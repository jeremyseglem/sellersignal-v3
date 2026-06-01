"""
Billing API.

  POST /api/billing/create-checkout
       Body: { zip_code: string, success_path?: string, cancel_path?: string }
       Auth: required (agent only — operators excluded)
       Returns: { checkout_url: string }
       Validates the ZIP is live and unclaimed. Gets-or-creates the agent's
       Stripe Customer and persists the ID on agent_profiles_v3. Creates a
       Checkout Session for the $299/mo recurring territory subscription
       and returns its URL — frontend redirects the agent there.

  POST /api/billing/webhook
       Stripe-only. Verifies signature, processes subscription events.
       Subscription.created   — sets the 90-day cancel_at, inserts the
                                agent_territories_v3 row, sets the
                                profile's assigned_zip. If the ZIP got
                                claimed by another agent between checkout
                                creation and now (true race), logs an
                                ERROR and skips the insert — manual
                                refund needed (rare; the pre-checkout
                                check catches the common cases).
       Subscription.deleted   — marks agent_territories_v3 row cancelled,
                                clears the profile's assigned_zip. ZIP is
                                immediately available for re-claim per
                                the locked spec.
       Invoice.payment_failed — logs for visibility. Stripe handles dunning
                                automatically; our renewal notification
                                task picks up subscriptions that are at
                                risk and emails the agent.
       Other events           — accepted and ignored.

  POST /api/billing/portal-link
       Body: { return_path?: string }
       Auth: required
       Returns: { portal_url: string }
       For agents who already have a Stripe Customer, creates a Customer
       Portal session and returns its URL. Agent can update card,
       view invoices, cancel from the portal.

The existing /api/agent/claim-zip endpoint is UNCHANGED by this slice.
Beta agents and operators still use it. Once the frontend is migrated to
the new flow in the next slice, /claim-zip will become legacy/admin-only.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Header, Request, HTTPException
from pydantic import BaseModel

from backend.api.db import get_supabase_client
from backend.api.auth import user_from_authorization as _user_from_authorization
from backend.services import stripe_service


router = APIRouter()
log = logging.getLogger("billing")


# Public site URL — Stripe needs absolute URLs for success/cancel/return.
# Falls back to the production domain if not set.
SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://sellersignal.co")


# ── Models ───────────────────────────────────────────────────────────

class CreateCheckoutBody(BaseModel):
    zip_code: str
    # Optional relative paths the agent should land on after checkout
    # success or cancellation. Defaults are sensible — success goes to
    # the briefing for the claimed ZIP, cancel back to the territories
    # page.
    success_path: Optional[str] = None
    cancel_path: Optional[str] = None


class PortalLinkBody(BaseModel):
    return_path: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────

def _load_profile(user_id: str) -> dict:
    """Fetch the agent profile row. Raises 404 if missing."""
    supa = get_supabase_client()
    if supa is None:
        raise HTTPException(503, "Database unavailable")
    res = (
        supa.table("agent_profiles_v3")
            .select("id, email, full_name, role, assigned_zip, stripe_customer_id")
            .eq("id", user_id)
            .single()
            .execute()
    )
    if not res.data:
        raise HTTPException(404, "Profile not found")
    return res.data


def _zip_is_live(zip_code: str) -> bool:
    supa = get_supabase_client()
    if supa is None:
        return False
    res = (
        supa.table("zip_coverage_v3")
            .select("status")
            .eq("zip_code", zip_code)
            .single()
            .execute()
    )
    return bool(res.data) and res.data.get("status") == "live"


def _zip_is_claimed(zip_code: str) -> Optional[dict]:
    """
    Returns the active territory row if the ZIP is currently claimed,
    None otherwise. Used both at checkout creation (block) and in the
    webhook (race-condition check).
    """
    supa = get_supabase_client()
    if supa is None:
        return None
    res = (
        supa.table("agent_territories_v3")
            .select("agent_id, zip_code, status, stripe_subscription_id")
            .eq("zip_code", zip_code)
            .eq("status", "active")
            .limit(1)
            .execute()
    )
    if res.data:
        return res.data[0]
    return None


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/create-checkout")
async def create_checkout(
    body: CreateCheckoutBody,
    authorization: Optional[str] = Header(None),
):
    user = _user_from_authorization(authorization)
    profile = _load_profile(user.id)

    # Operators bypass billing entirely — they have role-based access to
    # every ZIP. Returning 400 keeps the surface honest: if an operator
    # ends up hitting this endpoint, the frontend is wrong.
    if profile.get("role") == "operator":
        raise HTTPException(
            400,
            "Operators do not claim territories. Use the operator "
            "dashboard to access ZIPs.",
        )

    if profile.get("assigned_zip"):
        raise HTTPException(
            409,
            f"You already have a territory: {profile['assigned_zip']}. "
            "Cancel your existing subscription before claiming a new ZIP.",
        )

    zip_code = body.zip_code.strip()
    if not zip_code:
        raise HTTPException(400, "zip_code is required")

    if not _zip_is_live(zip_code):
        raise HTTPException(
            404,
            f"{zip_code} is not a live territory.",
        )

    existing_claim = _zip_is_claimed(zip_code)
    if existing_claim:
        # Pre-checkout block. Common case — another agent already paid.
        # The true-race case (two agents complete checkout within seconds
        # of each other) is handled separately in the webhook below.
        raise HTTPException(
            409,
            f"{zip_code} has already been claimed.",
        )

    # Get-or-create the Stripe Customer and persist the ID. We do this
    # BEFORE checkout so the same Customer is reused on any retry — no
    # orphan Customers piling up on abandoned checkouts.
    customer_id = stripe_service.get_or_create_customer(
        user_id=user.id,
        email=profile["email"],
        full_name=profile.get("full_name"),
        existing_customer_id=profile.get("stripe_customer_id"),
    )

    if customer_id != profile.get("stripe_customer_id"):
        supa = get_supabase_client()
        supa.table("agent_profiles_v3").update(
            {"stripe_customer_id": customer_id}
        ).eq("id", user.id).execute()

    success_path = body.success_path or f"/zip/{zip_code}?welcome=1"
    cancel_path = body.cancel_path or "/territories?checkout=cancelled"

    try:
        session = stripe_service.create_checkout_session(
            customer_id=customer_id,
            user_id=user.id,
            zip_code=zip_code,
            success_url=f"{SITE_URL}{success_path}",
            cancel_url=f"{SITE_URL}{cancel_path}",
        )
    except stripe.error.StripeError as e:
        log.exception("Stripe checkout creation failed for user %s", user.id)
        raise HTTPException(502, f"Stripe error: {e.user_message or str(e)}")

    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint. NOT auth-gated by our own auth — instead we
    verify the Stripe signature using STRIPE_WEBHOOK_SECRET. Any request
    that fails verification is rejected with 400.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(payload, signature)
    except stripe.error.SignatureVerificationError:
        log.warning("Webhook signature verification failed")
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        log.exception("Webhook payload could not be parsed")
        raise HTTPException(400, f"Bad payload: {e}")

    event_type = event["type"]
    obj = event["data"]["object"]
    log.info("[webhook] %s id=%s", event_type, event.get("id"))

    if event_type == "customer.subscription.created":
        _handle_subscription_created(obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(obj)
    elif event_type == "customer.subscription.updated":
        # Useful for catching status transitions (e.g. unpaid). For now
        # we just log; the renewal task picks up at-risk subs separately.
        log.info(
            "[webhook] sub %s status=%s cancel_at=%s",
            obj.get("id"), obj.get("status"), obj.get("cancel_at"),
        )
    elif event_type == "invoice.payment_failed":
        log.warning(
            "[webhook] payment_failed customer=%s sub=%s",
            obj.get("customer"), obj.get("subscription"),
        )
    elif event_type == "invoice.payment_succeeded":
        log.info(
            "[webhook] payment_succeeded customer=%s sub=%s",
            obj.get("customer"), obj.get("subscription"),
        )
    # All other event types are silently accepted (Stripe expects 2xx
    # responses to avoid retry storms).

    return {"received": True}


@router.post("/portal-link")
async def portal_link(
    body: PortalLinkBody,
    authorization: Optional[str] = Header(None),
):
    user = _user_from_authorization(authorization)
    profile = _load_profile(user.id)

    customer_id = profile.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(
            404,
            "No Stripe customer on file. The portal is only available to "
            "agents who have completed a checkout at least once.",
        )

    return_path = body.return_path or "/profile"
    try:
        url = stripe_service.create_portal_session(
            customer_id=customer_id,
            return_url=f"{SITE_URL}{return_path}",
        )
    except stripe.error.StripeError as e:
        log.exception("Portal session creation failed for user %s", user.id)
        raise HTTPException(502, f"Stripe error: {e.user_message or str(e)}")

    return {"portal_url": url}


# ── Webhook handlers ─────────────────────────────────────────────────

def _handle_subscription_created(sub: dict) -> None:
    """
    A Stripe Subscription was just created. Source of truth for the
    sellersignal_user_id and sellersignal_zip_code lives in the
    subscription's metadata (set at checkout creation).

    Steps:
      1. Verify the ZIP is still unclaimed (race-condition guard).
      2. Set the 90-day cancel_at on the Subscription.
      3. Insert the agent_territories_v3 row with status='active'.
      4. Set agent_profiles_v3.assigned_zip.

    On race conflict (another agent claimed the ZIP between checkout
    creation and webhook delivery), logs ERROR and skips inserts.
    The customer has paid; ops needs to manually issue a refund. This
    is rare — the pre-checkout block in /create-checkout catches the
    common case.
    """
    sub_id = sub.get("id")
    metadata = sub.get("metadata") or {}
    user_id = metadata.get("sellersignal_user_id")
    zip_code = metadata.get("sellersignal_zip_code")

    if not user_id or not zip_code:
        log.error(
            "[webhook] subscription %s missing metadata; cannot reconcile. "
            "Manual intervention required.",
            sub_id,
        )
        return

    supa = get_supabase_client()
    if supa is None:
        log.error("[webhook] Supabase unavailable; cannot record sub %s", sub_id)
        return

    existing = _zip_is_claimed(zip_code)
    if existing and existing.get("stripe_subscription_id") != sub_id:
        log.error(
            "[webhook] RACE CONFLICT: ZIP %s already claimed by agent %s "
            "with sub %s, but webhook received for sub %s (agent %s). "
            "MANUAL REFUND REQUIRED.",
            zip_code,
            existing.get("agent_id"),
            existing.get("stripe_subscription_id"),
            sub_id,
            user_id,
        )
        return

    # Set the 90-day commitment on the subscription. Stripe will auto-
    # cancel at this time unless the agent renews before then.
    try:
        stripe_service.set_subscription_commitment(sub_id)
    except stripe.error.StripeError:
        log.exception(
            "[webhook] Failed to set commitment on sub %s; continuing "
            "with territory insert anyway.",
            sub_id,
        )

    # Insert (or update if already present from a retry) the territory.
    # Stripe webhook deliveries can repeat — idempotency matters.
    try:
        (
            supa.table("agent_territories_v3")
                .upsert({
                    "agent_id": user_id,
                    "zip_code": zip_code,
                    "status": "active",
                    "stripe_subscription_id": sub_id,
                }, on_conflict="zip_code,status")
                .execute()
        )
    except Exception:
        log.exception(
            "[webhook] Failed to insert territory for sub %s zip %s",
            sub_id, zip_code,
        )
        return

    # Set assigned_zip on the profile. Same idempotency — repeats are
    # no-ops because the value is the same.
    try:
        supa.table("agent_profiles_v3").update(
            {"assigned_zip": zip_code}
        ).eq("id", user_id).execute()
    except Exception:
        log.exception(
            "[webhook] Failed to set assigned_zip for user %s",
            user_id,
        )

    log.info(
        "[webhook] Activated territory: user=%s zip=%s sub=%s",
        user_id, zip_code, sub_id,
    )


def _handle_subscription_deleted(sub: dict) -> None:
    """
    Subscription cancelled — by the agent in the Customer Portal, by
    payment failure (after Stripe's dunning), or by us via cancel_at
    when the agent didn't renew. Release the ZIP immediately per spec.
    """
    sub_id = sub.get("id")
    if not sub_id:
        return

    supa = get_supabase_client()
    if supa is None:
        log.error("[webhook] Supabase unavailable; cannot release sub %s", sub_id)
        return

    # Find the territory by subscription_id (not by metadata — Stripe may
    # strip metadata on some event shapes).
    res = (
        supa.table("agent_territories_v3")
            .select("agent_id, zip_code")
            .eq("stripe_subscription_id", sub_id)
            .eq("status", "active")
            .limit(1)
            .execute()
    )

    if not res.data:
        log.info(
            "[webhook] sub %s deletion: no active territory found "
            "(may have been released already)",
            sub_id,
        )
        return

    row = res.data[0]
    agent_id = row["agent_id"]
    zip_code = row["zip_code"]

    # Mark the territory cancelled. Keep the row for history rather than
    # deleting — the agent's claim history is auditable.
    try:
        (
            supa.table("agent_territories_v3")
                .update({"status": "cancelled"})
                .eq("stripe_subscription_id", sub_id)
                .eq("status", "active")
                .execute()
        )
    except Exception:
        log.exception(
            "[webhook] Failed to mark territory cancelled for sub %s",
            sub_id,
        )
        return

    # Clear assigned_zip on the profile so the agent can claim again.
    try:
        supa.table("agent_profiles_v3").update(
            {"assigned_zip": None}
        ).eq("id", agent_id).execute()
    except Exception:
        log.exception(
            "[webhook] Failed to clear assigned_zip for user %s",
            agent_id,
        )

    log.info(
        "[webhook] Released territory: user=%s zip=%s sub=%s",
        agent_id, zip_code, sub_id,
    )
