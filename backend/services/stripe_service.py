"""
Stripe service — thin wrappers around the Stripe Python SDK.

All raw `stripe.*` calls live in this module so the rest of the codebase
imports named helpers instead of touching the SDK directly. That keeps
mocking easy in tests and makes the dependency surface obvious.

Environment variables consumed:
    STRIPE_SECRET_KEY          — sk_test_... or sk_live_...
    STRIPE_WEBHOOK_SECRET      — whsec_... for verifying webhook signatures
    STRIPE_TERRITORY_PRICE_ID  — price_... for the $299/mo recurring SKU
    STRIPE_COMMITMENT_DAYS     — integer; default 90. Length of the
                                 commitment block (cancel_at = now + N days
                                 at subscription creation).

The module loads the secret key lazily on each call rather than at import
time so a missing env var produces a clear error from the affected endpoint
instead of crashing the whole backend at boot.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Optional

import stripe


log = logging.getLogger("stripe_service")


# ── Configuration ────────────────────────────────────────────────────────

def _api_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not set in the environment. "
            "Set it in Railway env vars before calling billing endpoints."
        )
    return key


def _webhook_secret() -> str:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError(
            "STRIPE_WEBHOOK_SECRET is not set. Webhook signature "
            "verification cannot proceed without it."
        )
    return secret


def territory_price_id() -> str:
    pid = os.environ.get("STRIPE_TERRITORY_PRICE_ID")
    if not pid:
        raise RuntimeError(
            "STRIPE_TERRITORY_PRICE_ID is not set. Cannot create a "
            "checkout session without the Price ID."
        )
    return pid


def commitment_days() -> int:
    return int(os.environ.get("STRIPE_COMMITMENT_DAYS", "90"))


def _configure_sdk() -> None:
    """Set the SDK's global api_key. Called at the top of every public
    function so the key is current even if env was updated in-process."""
    stripe.api_key = _api_key()


# ── Customers ────────────────────────────────────────────────────────────

def get_or_create_customer(
    user_id: str,
    email: str,
    full_name: Optional[str] = None,
    existing_customer_id: Optional[str] = None,
) -> str:
    """
    Return a Stripe Customer ID for this agent.

    If existing_customer_id is provided (from agent_profiles_v3), reuse it.
    Otherwise create a new Customer and return the new ID. Caller is
    responsible for persisting the ID back to agent_profiles_v3.

    `user_id` (the Supabase auth UUID) is recorded in customer.metadata.
    user_id so we can reconcile webhook events back to the agent without
    relying on email matching.
    """
    _configure_sdk()

    if existing_customer_id:
        try:
            # Confirm the Customer still exists (could have been deleted
            # from the Stripe dashboard during testing). If it doesn't,
            # fall through and create a fresh one.
            stripe.Customer.retrieve(existing_customer_id)
            return existing_customer_id
        except stripe.error.InvalidRequestError:
            log.warning(
                "Stripe customer %s on profile %s no longer exists; "
                "creating replacement",
                existing_customer_id, user_id,
            )

    customer = stripe.Customer.create(
        email=email,
        name=full_name or None,
        metadata={"sellersignal_user_id": user_id},
    )
    return customer.id


# ── Checkout ─────────────────────────────────────────────────────────────

def create_checkout_session(
    customer_id: str,
    user_id: str,
    zip_code: str,
    success_url: str,
    cancel_url: str,
) -> stripe.checkout.Session:
    """
    Create a Stripe Checkout Session for the territory subscription.

    Mode is 'subscription' — Stripe collects payment and creates a recurring
    Subscription on the configured monthly Price. After the session
    completes, Stripe fires `customer.subscription.created` to our webhook
    which is where the agent_territories_v3 row gets inserted.

    Metadata on the Session is mirrored onto the Subscription so the
    webhook handler can read user_id + zip_code without a separate lookup.
    """
    _configure_sdk()

    metadata = {
        "sellersignal_user_id": user_id,
        "sellersignal_zip_code": zip_code,
        "sellersignal_commitment_days": str(commitment_days()),
    }

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{
            "price": territory_price_id(),
            "quantity": 1,
        }],
        # Both the session and the resulting subscription get this metadata
        # so the webhook can read it regardless of which object Stripe sends.
        metadata=metadata,
        subscription_data={"metadata": metadata},
        success_url=success_url,
        cancel_url=cancel_url,
        # Disable Stripe's address collection — we don't need shipping
        # for a digital subscription. Tax can be enabled later via Stripe
        # Tax when there's a real US-wide tax footprint.
        billing_address_collection="auto",
        # Allow promotion codes so coupons we ship later just work.
        allow_promotion_codes=True,
    )
    return session


# ── Commitment enforcement ───────────────────────────────────────────────

def set_subscription_commitment(
    subscription_id: str,
    days_from_now: Optional[int] = None,
) -> stripe.Subscription:
    """
    Set the subscription's cancel_at to N days from now.

    Used in two places:
      1. Webhook on customer.subscription.created — sets the initial
         90-day cancel_at so the subscription auto-cancels at end of
         commitment unless renewed.
      2. Renewal endpoint — pushes cancel_at out another 90 days.

    `days_from_now` defaults to STRIPE_COMMITMENT_DAYS (90).
    """
    _configure_sdk()

    if days_from_now is None:
        days_from_now = commitment_days()

    cancel_at = int(time.time()) + (days_from_now * 24 * 60 * 60)

    return stripe.Subscription.modify(
        subscription_id,
        cancel_at=cancel_at,
        # proration_behavior=none so extending the commitment doesn't
        # generate a prorated invoice.
        proration_behavior="none",
    )


def extend_subscription_commitment(
    subscription_id: str,
    extension_days: Optional[int] = None,
) -> stripe.Subscription:
    """
    Renewal — push cancel_at out by `extension_days` from its CURRENT
    cancel_at value (not from now). Differs from set_subscription_commitment
    in that the new endpoint stacks onto the existing commitment instead
    of replacing it.

    If cancel_at is currently None (commitment was somehow cleared),
    falls back to set_subscription_commitment.
    """
    _configure_sdk()

    if extension_days is None:
        extension_days = commitment_days()

    sub = stripe.Subscription.retrieve(subscription_id)
    current_cancel_at = sub.cancel_at

    if not current_cancel_at:
        return set_subscription_commitment(subscription_id, extension_days)

    new_cancel_at = int(current_cancel_at) + (extension_days * 24 * 60 * 60)

    return stripe.Subscription.modify(
        subscription_id,
        cancel_at=new_cancel_at,
        proration_behavior="none",
    )


# ── Customer Portal ──────────────────────────────────────────────────────

def create_portal_session(customer_id: str, return_url: str) -> str:
    """
    Create a Stripe Customer Portal session and return its URL. The agent
    is redirected to the portal where they can update their payment
    method, view invoices, and cancel the subscription. We don't host any
    of that UI ourselves — Stripe owns it.

    On cancellation from the portal, Stripe fires
    customer.subscription.deleted which our webhook catches to release
    the ZIP.
    """
    _configure_sdk()

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


# ── Webhook verification ─────────────────────────────────────────────────

def construct_webhook_event(payload: bytes, signature: str) -> stripe.Event:
    """
    Verify the webhook signature and return the parsed Event. Raises
    stripe.error.SignatureVerificationError if the signature is invalid
    (which means either our STRIPE_WEBHOOK_SECRET is wrong or the request
    is forged).
    """
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature,
        secret=_webhook_secret(),
    )
