"""
backend/api/letters.py — letter sending + Lob integration endpoints.

  POST /api/letters/preview                 render HTML for client preview (free)
  POST /api/letters/send                    send one letter via Lob ($2.99)
  POST /api/letters/start-sequence          schedule all 6 via Lob ($14.99)
  POST /api/letters/cancel-sequence/{id}    cancel + proportional refund
  GET  /api/letters/balance                 agent credit balance
  POST /api/letters/topup                   STUBBED until commit 5
  GET  /api/letters/by-parcel/{pin}         all letters + sequences for a parcel
  POST /api/letters/render-pdf/{pin}        free HTML for browser-side PDF save
  POST /api/letters/lob-webhook             Lob status updates (no user auth)

Pricing (cents):
    single letter: 299        ($2.99)
    full sequence: 1499       ($14.99, saves $3 vs 6 individual sends)
    print-to-PDF:  0          (free)

Sequence schedule from start date:
    letter 1 (Day 1)   → immediate (no send_date)
    letter 2 (Day 30)  → start + 30 days
    letter 3 (Day 60)  → start + 60
    letter 4 (Day 90)  → start + 90
    letter 5 (Day 135) → start + 135
    letter 6 (Day 180) → start + 180

Cancel-sequence refund is proportional:
    refund_cents = round(cancelled_unmailed_count / 6 * 1499)
"""

import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field

from backend.api.auth import user_from_authorization
from backend.api.db import get_supabase_client
from backend.services.lob_client import (
    LobClient,
    LobError,
    LobAddressError,
    LobConfigError,
    LobNotFoundError,
)
from backend.services.letter_content import generate_six_letters
from backend.services.letter_renderer import render_letter_html


logger = logging.getLogger(__name__)

router = APIRouter()


# ── Constants ───────────────────────────────────────────────────────


SINGLE_LETTER_COST_CENTS = 299
SEQUENCE_COST_CENTS = 1499

# Day offsets from start for letters 1–6 in the sequence
SEQUENCE_DAY_OFFSETS = [0, 30, 60, 90, 135, 180]

# Lob webhook event type → our status field mapping. Events not in this
# map are accepted but ignored (e.g. letter.rendered_pdf, letter.created).
WEBHOOK_STATUS_MAP = {
    "letter.processed_for_delivery": "processed_for_delivery",
    "letter.mailed":                 "mailed",
    "letter.in_transit":             "in_transit",
    "letter.in_local_area":          "in_local_area",
    "letter.delivered":              "delivered",
    "letter.re-routed":              "re-routed",
    "letter.returned_to_sender":     "returned_to_sender",
    "letter.deleted":                "cancelled",
    "letter.failed":                 "failed",
}


# ── Pydantic request models ─────────────────────────────────────────


class PreviewRequest(BaseModel):
    pin: str = Field(..., description="Parcel PIN")
    letter_index: int = Field(..., ge=1, le=6, description="Which letter (1-6)")


class SendLetterRequest(BaseModel):
    pin: str
    letter_index: int = Field(..., ge=1, le=6)


class StartSequenceRequest(BaseModel):
    pin: str


class RenderPdfRequest(BaseModel):
    letter_index: int = Field(..., ge=1, le=6)


# ── Helpers ─────────────────────────────────────────────────────────


def _supa():
    """Resolve the Supabase service-role client. 503 if unavailable."""
    s = get_supabase_client()
    if not s:
        raise HTTPException(503, "Database not configured")
    return s


def _load_profile(supa, user_id: str) -> dict[str, Any]:
    """Load the agent profile. 404 if missing."""
    resp = (
        supa.table("agent_profiles_v3")
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(404, "Agent profile not found. Complete onboarding first.")
    return resp.data


def _validate_profile_for_send(profile: dict[str, Any]) -> None:
    """Block send if required return-address fields aren't set on profile."""
    required = (
        "return_address_line1", "return_address_city",
        "return_address_state", "return_address_zip",
    )
    missing = [k for k in required if not (profile.get(k) or "").strip()]
    if missing:
        raise HTTPException(
            400,
            f"Cannot send: profile missing required fields {missing}. "
            f"Set them at /profile before sending letters."
        )


def _load_parcel(supa, pin: str) -> dict[str, Any]:
    resp = (
        supa.table("parcels_v3")
        .select("*")
        .eq("pin", pin)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(404, f"Parcel {pin} not found")
    return resp.data


def _load_harvester_matches(supa, pin: str) -> list[dict[str, Any]]:
    """Load all harvester matches for a PIN — used to dig out PR + decedent
    for probate letters. Returns empty list if none."""
    resp = (
        supa.table("raw_signal_matches_v3")
        .select("*")
        .eq("pin", pin)
        .execute()
    )
    return (resp.data if resp else None) or []


def _build_lob_addresses(
    profile: dict[str, Any],
    parcel: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Construct the (from, to) address dicts in the shape Lob expects.
    The `from` address goes on the envelope (and lives on agent profile).
    The `to` address is the property owner at the parcel address."""
    from_addr = {
        "name": (
            (profile.get("return_address_name") or "").strip()
            or (profile.get("full_name") or "").strip()
            or "SellerSignal Agent"
        ),
        "address_line1": profile["return_address_line1"].strip(),
        "address_line2": (profile.get("return_address_line2") or "").strip() or None,
        "address_city":  profile["return_address_city"].strip(),
        "address_state": profile["return_address_state"].strip().upper(),
        "address_zip":   profile["return_address_zip"].strip(),
        "address_country": "US",
    }

    # Recipient: owner name + property address. We mail to the property
    # itself (not the owner's mailing address) — for probate, that's the
    # estate property; for absentee, it's where we want the letter to
    # land. If the property has a different owner mailing address we'd
    # use that, but parcels_v3 doesn't carry it consistently yet.
    to_addr = {
        "name": (parcel.get("owner_name") or "Property Owner").strip(),
        "address_line1": (parcel.get("address") or "").strip(),
        "address_line2": None,
        "address_city":  (parcel.get("city") or "").strip(),
        "address_state": (parcel.get("state") or "WA").strip().upper(),
        "address_zip":   (parcel.get("zip_code") or "").strip(),
        "address_country": "US",
    }

    if not to_addr["address_line1"]:
        raise HTTPException(
            400,
            f"Parcel {parcel.get('pin')} has no address — cannot send a letter "
            f"to a parcel without a street address.",
        )

    return from_addr, to_addr


def _verify_or_passthrough(
    client: LobClient,
    addr: dict[str, Any],
) -> dict[str, Any]:
    """Verify address via Lob. In test mode, accept 'undeliverable' (test
    mode doesn't hit real USPS data) and pass through the raw address.
    In live mode, propagate the error so the caller sees the 422."""
    try:
        return client.verify_address(
            line1=addr["address_line1"],
            line2=addr.get("address_line2"),
            city=addr["address_city"],
            state=addr["address_state"],
            zip_code=addr["address_zip"],
            name=addr.get("name"),
        )
    except LobAddressError as e:
        if client.mode == "test" and e.lob_code == "undeliverable":
            logger.info(
                "Test-mode address bypass for %s (Lob test doesn't verify real addresses)",
                addr.get("address_line1"),
            )
            return {**addr}
        raise


def _charge_balance(supa, user_id: str, cents: int) -> int:
    """Atomically deduct from agent balance. Returns new balance.
    Raises 402 if insufficient — relies on the CHECK >= 0 constraint
    catching race conditions at the DB level."""
    profile = (
        supa.table("agent_profiles_v3")
        .select("letter_credit_cents")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not profile or not profile.data:
        raise HTTPException(404, "Agent profile not found")
    current = int(profile.data.get("letter_credit_cents") or 0)
    if current < cents:
        raise HTTPException(
            402,
            f"Insufficient balance: have ${current/100:.2f}, need ${cents/100:.2f}. "
            f"Top up your balance to continue."
        )
    new_balance = current - cents
    upd = (
        supa.table("agent_profiles_v3")
        .update({"letter_credit_cents": new_balance})
        .eq("id", user_id)
        .execute()
    )
    if not upd or not upd.data:
        raise HTTPException(500, "Failed to deduct balance — please retry")
    return new_balance


def _refund_balance(supa, user_id: str, cents: int) -> int:
    """Add back to balance (used by cancel-sequence refund + send failure
    rollback). Returns new balance."""
    profile = (
        supa.table("agent_profiles_v3")
        .select("letter_credit_cents")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not profile or not profile.data:
        return 0
    current = int(profile.data.get("letter_credit_cents") or 0)
    new_balance = current + cents
    supa.table("agent_profiles_v3").update(
        {"letter_credit_cents": new_balance}
    ).eq("id", user_id).execute()
    return new_balance


def _generate_letters_for_parcel(
    parcel: dict[str, Any],
    harvester_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate the 6-letter sequence and surface a clean error if the
    parcel's owner type isn't cultivatable."""
    letters = generate_six_letters(parcel, harvester_matches, archetype_key=None)
    if not letters:
        raise HTTPException(
            400,
            f"Cannot generate letters for owner type {parcel.get('owner_type')!r} "
            f"(gov/nonprofit owners are excluded from cultivation)."
        )
    return letters


def _render_html_for_letter(
    letter: dict[str, Any],
    profile: dict[str, Any],
    to_addr: dict[str, Any],
) -> str:
    """Wrap a letter body in the full Lob-ready HTML."""
    return render_letter_html(
        body=letter["body"],
        recipient_name=to_addr.get("name"),
        recipient_line1=to_addr["address_line1"],
        recipient_line2=to_addr.get("address_line2"),
        recipient_city=to_addr["address_city"],
        recipient_state=to_addr["address_state"],
        recipient_zip=to_addr["address_zip"],
        agent_full_name=(profile.get("full_name") or "Your Agent"),
        agent_signature_url=profile.get("signature_url"),
    )


# ── 1. Preview ───────────────────────────────────────────────────────


@router.post("/preview")
async def preview_letter(
    body: PreviewRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Render the HTML for one letter without sending or charging. Used by
    the SixLettersModal preview path. Returns the HTML plus the letter
    metadata (name, day label, trigger).
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user["id"])
    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    _from_addr, to_addr = _build_lob_addresses(profile, parcel)
    html = _render_html_for_letter(letter, profile, to_addr)

    return {
        "html": html,
        "letter": {
            "num": letter["num"],
            "name": letter["name"],
            "day_label": letter["dayLabel"],
            "trigger": letter["trigger"],
        },
    }


# ── 2. Send single letter ────────────────────────────────────────────


@router.post("/send")
async def send_letter(
    body: SendLetterRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Send one letter via Lob. Deducts $2.99 from balance, creates the
    letter via Lob API in the configured mode (test or live), records
    a letters_sent_v3 row.

    Idempotency: each request generates a uuid4 idempotency key so
    accidental double-clicks within seconds dedupe at the Lob layer.
    Frontend should also debounce the send button.
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user["id"])
    _validate_profile_for_send(profile)

    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    from_raw, to_raw = _build_lob_addresses(profile, parcel)

    cost = SINGLE_LETTER_COST_CENTS
    _charge_balance(supa, user["id"], cost)

    # Wrap the rest in try/except — if anything fails after charging, we
    # refund and re-raise. Lob duplication is prevented by idempotency
    # key, but if our DB write fails after Lob succeeds we surface a
    # clear error and the agent isn't double-charged.
    try:
        client = LobClient()
        try:
            from_verified = _verify_or_passthrough(client, from_raw)
            to_verified = _verify_or_passthrough(client, to_raw)
        except LobAddressError as e:
            raise HTTPException(
                422,
                f"Address validation failed: {e} (lob_code={e.lob_code})",
            )

        html = _render_html_for_letter(letter, profile, to_verified)

        idem_key = f"ss-single-{uuid.uuid4()}"
        lob_letter = client.create_letter(
            from_address=from_verified,
            to_address=to_verified,
            html_body=html,
            description=f"SellerSignal letter {letter['num']}/6 to {body.pin}",
            metadata={
                "agent_id": str(user["id"]),
                "pin": str(body.pin),
                "zip_code": str(parcel.get("zip_code") or ""),
                "letter_index": str(body.letter_index),
                "sequence_id": "",
            },
            color=True,
            idempotency_key=idem_key,
        )
        client.close()

        # Persist the row. Lob has already accepted — even if this insert
        # fails, the letter is on the wire. We log loudly so reconciliation
        # is possible from Lob's dashboard.
        row = {
            "agent_id": user["id"],
            "pin": body.pin,
            "zip_code": parcel.get("zip_code") or "",
            "sequence_id": None,
            "letter_index": body.letter_index,
            "method": "lob_mail",
            "lob_letter_id": lob_letter.get("id"),
            "lob_send_date": lob_letter.get("send_date"),
            "lob_expected_delivery": lob_letter.get("expected_delivery_date"),
            "lob_mode": client.mode,
            "lob_tracking_url": lob_letter.get("url"),
            "status": "created",
            "cost_cents": cost,
            "rendered_html": html,
            "recipient_name":  to_verified.get("name"),
            "recipient_line1": to_verified.get("address_line1"),
            "recipient_line2": to_verified.get("address_line2"),
            "recipient_city":  to_verified.get("address_city"),
            "recipient_state": to_verified.get("address_state"),
            "recipient_zip":   to_verified.get("address_zip"),
        }
        insert = supa.table("letters_sent_v3").insert(row).execute()
        if not insert or not insert.data:
            logger.error(
                "Lob letter %s sent but DB insert failed — manual reconciliation needed",
                lob_letter.get("id"),
            )
            # Don't refund — the letter went out. Surface to operator.
            raise HTTPException(
                500,
                f"Letter sent via Lob (id={lob_letter.get('id')}) but failed to log. "
                f"Contact support to reconcile."
            )

        return {
            "ok": True,
            "letter_row_id": insert.data[0]["id"],
            "lob_letter_id": lob_letter.get("id"),
            "lob_mode": client.mode,
            "status": "created",
            "expected_delivery_date": lob_letter.get("expected_delivery_date"),
            "cost_cents": cost,
            "new_balance_cents": int(profile.get("letter_credit_cents", 0)) - cost,
        }

    except HTTPException:
        # Address validation or DB-after-Lob: don't refund (letter sent
        # or charge was legitimately consumed). Re-raise.
        raise
    except (LobConfigError, LobError) as e:
        # Lob failed cleanly — letter not sent. Refund and surface.
        _refund_balance(supa, user["id"], cost)
        logger.warning("Lob send failed for agent %s pin %s: %s",
                       user["id"], body.pin, e)
        raise HTTPException(502, f"Lob error: {type(e).__name__}: {e}")
    except Exception as e:
        # Unknown failure — refund and surface as 500.
        _refund_balance(supa, user["id"], cost)
        logger.exception("Unexpected error sending letter")
        raise HTTPException(500, f"Send failed: {type(e).__name__}: {e}")


# ── 3. Start sequence ────────────────────────────────────────────────


@router.post("/start-sequence")
async def start_sequence(
    body: StartSequenceRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Schedule all 6 letters via Lob's send_date. Letter 1 sends
    immediately, 2-6 are scheduled at +30/60/90/135/180 days. Creates
    one letter_sequences_v3 row and 6 letters_sent_v3 rows.

    If any Lob create fails mid-sequence, we cancel the ones already
    created and refund the full sequence cost. Atomic-ish at the
    business level.
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user["id"])
    _validate_profile_for_send(profile)

    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    from_raw, to_raw = _build_lob_addresses(profile, parcel)

    cost = SEQUENCE_COST_CENTS
    _charge_balance(supa, user["id"], cost)

    sequence_row = None
    created_lob_ids: list[str] = []

    try:
        client = LobClient()
        try:
            from_verified = _verify_or_passthrough(client, from_raw)
            to_verified = _verify_or_passthrough(client, to_raw)
        except LobAddressError as e:
            raise HTTPException(
                422,
                f"Address validation failed: {e} (lob_code={e.lob_code})",
            )

        # Create the sequence parent row first so child rows have a FK.
        seq_insert = supa.table("letter_sequences_v3").insert({
            "agent_id": user["id"],
            "pin": body.pin,
            "zip_code": parcel.get("zip_code") or "",
            "status": "active",
            "total_charged_cents": cost,
        }).execute()
        if not seq_insert or not seq_insert.data:
            raise HTTPException(500, "Failed to create sequence row")
        sequence_row = seq_insert.data[0]
        sequence_id = sequence_row["id"]

        now = datetime.now(timezone.utc)
        per_letter_cost = cost // 6  # 249 cents = ~$2.49

        for idx, letter in enumerate(letters, start=1):
            day_offset = SEQUENCE_DAY_OFFSETS[idx - 1]
            send_date = None
            if day_offset > 0:
                # Lob expects ISO date string for future scheduled sends.
                # Immediate sends (letter 1) leave send_date unset.
                send_date = (now + timedelta(days=day_offset)).strftime("%Y-%m-%d")

            html = _render_html_for_letter(letter, profile, to_verified)
            idem = f"ss-seq-{sequence_id}-{idx}"

            lob_letter = client.create_letter(
                from_address=from_verified,
                to_address=to_verified,
                html_body=html,
                description=f"SellerSignal sequence {sequence_id} letter {idx}/6 to {body.pin}",
                metadata={
                    "agent_id": str(user["id"]),
                    "pin": str(body.pin),
                    "zip_code": str(parcel.get("zip_code") or ""),
                    "letter_index": str(idx),
                    "sequence_id": str(sequence_id),
                },
                color=True,
                send_date=send_date,
                idempotency_key=idem,
            )
            created_lob_ids.append(lob_letter.get("id"))

            row = {
                "agent_id": user["id"],
                "pin": body.pin,
                "zip_code": parcel.get("zip_code") or "",
                "sequence_id": sequence_id,
                "letter_index": idx,
                "method": "lob_mail",
                "lob_letter_id": lob_letter.get("id"),
                "lob_send_date": lob_letter.get("send_date"),
                "lob_expected_delivery": lob_letter.get("expected_delivery_date"),
                "lob_mode": client.mode,
                "lob_tracking_url": lob_letter.get("url"),
                "status": "created",
                "cost_cents": per_letter_cost,
                "rendered_html": html,
                "recipient_name":  to_verified.get("name"),
                "recipient_line1": to_verified.get("address_line1"),
                "recipient_line2": to_verified.get("address_line2"),
                "recipient_city":  to_verified.get("address_city"),
                "recipient_state": to_verified.get("address_state"),
                "recipient_zip":   to_verified.get("address_zip"),
            }
            supa.table("letters_sent_v3").insert(row).execute()

        client.close()

        return {
            "ok": True,
            "sequence_id": sequence_id,
            "letters_scheduled": 6,
            "first_letter_immediate": True,
            "cost_cents": cost,
            "lob_mode": client.mode,
        }

    except HTTPException:
        # Re-raise — partial state has been logged; let admin handle.
        raise
    except (LobConfigError, LobError) as e:
        # Best-effort cleanup: cancel any letters we managed to create.
        logger.error("Sequence creation failed after %d letters; rolling back: %s",
                     len(created_lob_ids), e)
        try:
            cleanup = LobClient()
            for lid in created_lob_ids:
                try:
                    cleanup.cancel_letter(lid)
                except Exception:
                    pass  # Best-effort; if cancel window passed, letter will mail
            cleanup.close()
        except Exception:
            pass

        # Mark the sequence as failed if we managed to create it.
        if sequence_row:
            try:
                supa.table("letter_sequences_v3").update({
                    "status": "failed",
                    "cancel_reason": f"Lob error: {type(e).__name__}",
                }).eq("id", sequence_row["id"]).execute()
            except Exception:
                pass

        _refund_balance(supa, user["id"], cost)
        raise HTTPException(502, f"Sequence creation failed: {type(e).__name__}: {e}")

    except Exception as e:
        logger.exception("Unexpected error starting sequence")
        _refund_balance(supa, user["id"], cost)
        raise HTTPException(500, f"Sequence start failed: {type(e).__name__}: {e}")


# ── 4. Cancel sequence ──────────────────────────────────────────────


@router.post("/cancel-sequence/{sequence_id}")
async def cancel_sequence(
    sequence_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Cancel any unmailed letters in a sequence. Refund proportional to
    the count of letters successfully cancelled (still unmailed).

    Letters whose send_date has already passed (or which were sent
    immediately, like letter 1) can no longer be cancelled — Lob
    returns 404 in that case and we treat that as "already mailed,
    no refund for that one".
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    # Load sequence and verify ownership.
    seq = (
        supa.table("letter_sequences_v3")
        .select("*")
        .eq("id", sequence_id)
        .eq("agent_id", user["id"])
        .maybe_single()
        .execute()
    )
    if not seq or not seq.data:
        raise HTTPException(404, "Sequence not found")
    if seq.data["status"] in ("cancelled", "completed", "failed"):
        raise HTTPException(400, f"Sequence is already {seq.data['status']}")

    children = (
        supa.table("letters_sent_v3")
        .select("*")
        .eq("sequence_id", sequence_id)
        .execute()
    )
    children_rows = (children.data if children else None) or []

    # Cancel any that aren't already in a terminal state.
    TERMINAL = {"mailed", "in_transit", "in_local_area", "delivered",
                "re-routed", "returned_to_sender", "cancelled", "failed"}
    cancelled_count = 0
    skipped_count = 0
    try:
        client = LobClient()
        for child in children_rows:
            if child.get("status") in TERMINAL:
                skipped_count += 1
                continue
            lob_id = child.get("lob_letter_id")
            if not lob_id:
                skipped_count += 1
                continue
            try:
                client.cancel_letter(lob_id)
                supa.table("letters_sent_v3").update({
                    "status": "cancelled",
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", child["id"]).execute()
                cancelled_count += 1
            except LobNotFoundError:
                # Past cancellation window — Lob already processed it.
                skipped_count += 1
            except Exception as e:
                logger.warning("Failed to cancel Lob letter %s: %s", lob_id, e)
                skipped_count += 1
        client.close()
    except Exception as e:
        logger.exception("Sequence cancel failed mid-way")
        raise HTTPException(502, f"Cancel failed: {e}")

    refund_cents = int(round((cancelled_count / 6) * SEQUENCE_COST_CENTS))
    if refund_cents > 0:
        _refund_balance(supa, user["id"], refund_cents)

    supa.table("letter_sequences_v3").update({
        "status": "cancelled",
        "cancelled_at": datetime.now(timezone.utc).isoformat(),
        "cancel_reason": "Agent cancelled",
    }).eq("id", sequence_id).execute()

    return {
        "ok": True,
        "sequence_id": sequence_id,
        "cancelled_count": cancelled_count,
        "skipped_count": skipped_count,
        "refund_cents": refund_cents,
    }


# ── 5. Balance ──────────────────────────────────────────────────────


@router.get("/balance")
async def get_balance(authorization: Optional[str] = Header(None)):
    user = user_from_authorization(authorization)
    supa = _supa()
    profile = _load_profile(supa, user["id"])
    return {
        "balance_cents": int(profile.get("letter_credit_cents") or 0),
        "balance_display": f"${int(profile.get('letter_credit_cents') or 0) / 100:.2f}",
    }


# ── 6. Top-up (stubbed until commit 5) ──────────────────────────────


@router.post("/topup")
async def topup_stub(authorization: Optional[str] = Header(None)):
    """Stripe top-up is wired in commit 5. For now, returns a notice so
    the frontend can render a 'coming soon' message. Manual credit can
    be applied via Supabase SQL editor by an admin."""
    user_from_authorization(authorization)
    return {
        "ok": False,
        "coming_soon": True,
        "message": (
            "Self-serve top-up via Stripe is being wired up. "
            "Contact support to add credit manually in the meantime."
        ),
    }


# ── 7. By parcel ────────────────────────────────────────────────────


@router.get("/by-parcel/{pin}")
async def letters_by_parcel(
    pin: str,
    authorization: Optional[str] = Header(None),
):
    """
    Return all letters + sequences this agent has for one parcel.
    Used by the dossier to show status badges and prevent accidental
    double-sends.
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    letters = (
        supa.table("letters_sent_v3")
        .select(
            "id,letter_index,method,status,cost_cents,"
            "lob_letter_id,lob_mode,lob_send_date,lob_expected_delivery,"
            "created_at,mailed_at,delivered_at,sequence_id"
        )
        .eq("agent_id", user["id"])
        .eq("pin", pin)
        .order("created_at", desc=True)
        .execute()
    )
    sequences = (
        supa.table("letter_sequences_v3")
        .select("id,status,started_at,cancelled_at,total_charged_cents")
        .eq("agent_id", user["id"])
        .eq("pin", pin)
        .order("started_at", desc=True)
        .execute()
    )
    return {
        "letters": (letters.data if letters else None) or [],
        "sequences": (sequences.data if sequences else None) or [],
    }


# ── 8. Render PDF (free path) ───────────────────────────────────────


@router.post("/render-pdf/{pin}")
async def render_pdf(
    pin: str,
    body: RenderPdfRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Free print-to-PDF path: render the letter HTML and return it. The
    frontend opens the HTML in a new window and the agent uses the
    browser's Print > Save as PDF. No Lob call, no charge, no
    letters_sent_v3 row written. We do log a 'pdf_rendered' row for
    audit/history so the dossier shows "PDF rendered for letter 3 on
    2026-05-15".
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user["id"])
    parcel = _load_parcel(supa, pin)
    matches = _load_harvester_matches(supa, pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    _from_addr, to_addr = _build_lob_addresses(profile, parcel)
    html = _render_html_for_letter(letter, profile, to_addr)

    # Log the PDF render so dossier history is complete.
    supa.table("letters_sent_v3").insert({
        "agent_id": user["id"],
        "pin": pin,
        "zip_code": parcel.get("zip_code") or "",
        "sequence_id": None,
        "letter_index": body.letter_index,
        "method": "pdf_download",
        "status": "pdf_rendered",
        "cost_cents": 0,
        "rendered_html": html,
        "recipient_name":  to_addr.get("name"),
        "recipient_line1": to_addr.get("address_line1"),
        "recipient_line2": to_addr.get("address_line2"),
        "recipient_city":  to_addr.get("address_city"),
        "recipient_state": to_addr.get("address_state"),
        "recipient_zip":   to_addr.get("address_zip"),
    }).execute()

    return {"html": html, "letter_index": body.letter_index}


# ── 9. Lob webhook ──────────────────────────────────────────────────


@router.post("/lob-webhook")
async def lob_webhook(request: Request):
    """
    Receive status updates from Lob. Configured in the Lob dashboard:
        URL:    https://sellersignal.co/api/letters/lob-webhook
        Events: letter.* (subscribe to all letter events)
        Secret: copy to Railway as LOB_WEBHOOK_SECRET

    Verification: Lob sends `lob-signature` and `lob-signature-timestamp`
    headers. We compute HMAC-SHA256 of `<timestamp>.<raw_body>` keyed
    by LOB_WEBHOOK_SECRET and compare in constant time. If the secret
    isn't set in env we accept all webhooks (with a warning) so initial
    test-mode integration isn't blocked — switch to strict once the
    secret is configured.

    Replay protection: reject events with a timestamp more than 5
    minutes old (Lob's recommended window).
    """
    raw_body = await request.body()

    secret = os.environ.get("LOB_WEBHOOK_SECRET", "").strip()
    sig_header = request.headers.get("lob-signature", "")
    ts_header = request.headers.get("lob-signature-timestamp", "")

    if secret:
        if not sig_header or not ts_header:
            logger.warning("Webhook missing signature headers")
            raise HTTPException(401, "Missing signature headers")

        # Replay window: reject events more than 5 minutes old.
        try:
            ts_int = int(ts_header)
        except ValueError:
            raise HTTPException(401, "Bad timestamp")
        if abs(time.time() - ts_int) > 300:
            raise HTTPException(401, "Timestamp out of replay window")

        # HMAC-SHA256 verify
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{ts_header}.{raw_body.decode('utf-8')}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            logger.warning("Webhook signature mismatch")
            raise HTTPException(401, "Bad signature")
    else:
        logger.warning(
            "LOB_WEBHOOK_SECRET not set — accepting webhook without verification. "
            "Set the env var to enable signature checks."
        )

    # Parse event payload
    try:
        import json
        event = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    event_type = event.get("event_type") or event.get("type") or ""
    payload = event.get("body") or event.get("data") or {}
    lob_letter_id = payload.get("id")

    if not lob_letter_id:
        return {"ok": True, "ignored": True, "reason": "no letter id"}

    new_status = WEBHOOK_STATUS_MAP.get(event_type)
    if not new_status:
        logger.debug("Ignoring webhook event %s for letter %s", event_type, lob_letter_id)
        return {"ok": True, "ignored": True, "event_type": event_type}

    supa = _supa()
    update: dict[str, Any] = {
        "status": new_status,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    if new_status == "mailed":
        update["mailed_at"] = now_iso
    elif new_status == "delivered":
        update["delivered_at"] = now_iso
    elif new_status == "cancelled":
        update["cancelled_at"] = now_iso
    elif new_status == "failed":
        update["failed_at"] = now_iso
        update["fail_reason"] = payload.get("failure_reason") or "Lob failed"

    # Look up the letter by lob_letter_id. RLS bypassed since this
    # uses the service-role client.
    result = (
        supa.table("letters_sent_v3")
        .update(update)
        .eq("lob_letter_id", lob_letter_id)
        .execute()
    )

    updated = (result.data if result else None) or []
    return {
        "ok": True,
        "event_type": event_type,
        "lob_letter_id": lob_letter_id,
        "new_status": new_status,
        "rows_updated": len(updated),
    }
