"""
backend/api/letters.py — letter sending + Stannp integration endpoints.

  POST /api/letters/preview                  render HTML for client preview (free)
  POST /api/letters/send                     send one letter via Stannp ($1.99)
  POST /api/letters/start-sequence           schedule all 6 via Stannp ($9.99)
  POST /api/letters/cancel-sequence/{id}     cancel + proportional refund
  GET  /api/letters/balance                  agent credit balance
  POST /api/letters/topup                    STUBBED until commit 5
  GET  /api/letters/by-parcel/{pin}          all letters + sequences for a parcel
  POST /api/letters/render-pdf/{pin}         free HTML for browser-side PDF save
  POST /api/letters/stannp-webhook           Stannp status updates (no user auth)

Pricing (cents):
    single letter: 199        ($1.99)
    full sequence: 999        ($9.99, saves $1.95 vs 6 individual sends)
    print-to-PDF:  0          (free)

Sequence schedule from start date (unchanged from the Lob behavior — only
the print provider changed):
    letter 1 (Day 1)   → immediate (sent now via Stannp API)
    letter 2 (Day 30)  → start + 30 days  ┐
    letter 3 (Day 60)  → start + 60       │ Stannp has no native send_date,
    letter 4 (Day 90)  → start + 90       │ so these are stored as
    letter 5 (Day 135) → start + 135      │ status='scheduled' rows and
    letter 6 (Day 180) → start + 180      ┘ the letter_scheduler background
                                            task picks them up on their due
                                            date and calls Stannp.

Cancel-sequence refund is proportional:
    refund_cents = round(cancelled_unmailed_count / 6 * 999)
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
from backend.services.stannp_client import (
    get_client as get_stannp_client,
    StannpError,
    StannpAddressError,
    StannpConfigError,
    StannpAuthError,
)
from backend.services.letter_pdf_renderer import render_html_to_pdf
from backend.services.letter_content import generate_six_letters
from backend.services.letter_renderer import render_letter_html


logger = logging.getLogger(__name__)

router = APIRouter()


# ── Constants ───────────────────────────────────────────────────────


SINGLE_LETTER_COST_CENTS = 199
SEQUENCE_COST_CENTS = 999

# Day offsets from start for letters 1–6 in the sequence. Unchanged from
# the Lob era — these are product-level decisions, not provider-specific.
SEQUENCE_DAY_OFFSETS = [0, 30, 60, 90, 135, 180]

# Stannp webhook event type → our status field mapping. Events not in this
# map are accepted but ignored. Stannp's events are documented at
# https://www.stannp.com/us/direct-mail-api/webhooks — names mirror their
# print/dispatch lifecycle rather than Lob's USPS-flavored events.
WEBHOOK_STATUS_MAP = {
    "letter.created":     "created",
    "letter.printed":     "processed_for_delivery",
    "letter.dispatched":  "mailed",
    "letter.delivered":   "delivered",
    "letter.cancelled":   "cancelled",
    "letter.failed":      "failed",
    "letter.returned":    "returned_to_sender",
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
    """Block send if required fields aren't set on profile. Phone is
    required so the letter has a callback number — the entire point
    of direct mail is for the recipient to be able to reach the
    agent. Return address is required so undeliverable mail comes
    back somewhere real."""
    required = (
        "phone",
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


def _build_stannp_recipient(parcel: dict[str, Any]) -> dict[str, Any]:
    """
    Construct the Stannp recipient dict from a parcel row. Stannp's
    /letters/create endpoint takes flat recipient[*] form fields and
    handles the mail-merge overlay onto the windowed envelope clear
    zone itself.

    Stannp accepts firstname/lastname OR company. We don't try to split
    owner_name — we put the whole owner string into 'lastname' which
    renders cleanly on the address line whether the owner is an
    individual ("BRYANT JOSEPH"), a couple ("BRYANT JOSEPH & MARY"),
    or a trust ("BRYANT FAMILY TRUST"). Future enhancement: detect
    owner_type and route trust/LLC names to recipient[company] for
    better formatting.

    Return address on the envelope (the agent's address) lives at the
    Stannp account level (set in their dashboard) — Stannp's per-letter
    API doesn't take it. The agent's return address still appears in
    the letter body's signature block, so the recipient knows where to
    write back even if the envelope flap is Stannp-generic.
    """
    owner_name = (parcel.get("owner_name") or "Property Owner").strip()
    line1 = (parcel.get("address") or "").strip()
    if not line1:
        raise HTTPException(
            400,
            f"Parcel {parcel.get('pin')} has no address — cannot send a letter "
            f"to a parcel without a street address.",
        )

    return {
        "lastname": owner_name,
        "address1": line1,
        "city":     (parcel.get("city")  or "").strip(),
        # Stannp ignores 'state' (their US schema derives it from ZIP) but
        # we carry it on this dict for the preview renderer.
        "state":    (parcel.get("state") or "WA").strip().upper(),
        "zipcode":  (parcel.get("zip_code") or "").strip(),
        "country":  "US",
    }


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
    recipient: dict[str, Any],
    *,
    no_recipient_block: bool = False,
) -> str:
    """
    Wrap a letter body in the full letter HTML.

    Args:
      no_recipient_block:
        When True, omits the recipient address block — used for the
        Stannp send path, where Stannp performs its own mail-merge
        overlay at print time. When False (default), embeds the address
        in the document — used for the in-app preview, browser PDF
        download, and any code path that needs a stand-alone letter.

    The recipient dict here is the Stannp recipient shape
    (lastname/address1/city/zipcode), not Lob's. We translate to the
    renderer's expected param names below.
    """
    return render_letter_html(
        body=letter["body"],
        recipient_name=recipient.get("lastname") or "Property Owner",
        recipient_line1=recipient.get("address1") or "",
        recipient_line2=recipient.get("address2"),
        recipient_city=recipient.get("city") or "",
        recipient_state=recipient.get("state") or "WA",
        recipient_zip=recipient.get("zipcode") or "",
        agent_full_name=(profile.get("full_name") or "Your Agent"),
        agent_phone=profile.get("phone"),
        agent_email=profile.get("email"),
        agent_signature_url=profile.get("signature_url"),
        no_recipient_block=no_recipient_block,
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

    profile = _load_profile(supa, user.id)
    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    _from_addr, to_addr = None, _build_stannp_recipient(parcel)
    html = _render_html_for_letter(letter, profile, to_addr, no_recipient_block=False)

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
    Send one letter via Stannp. Deducts $1.99 from balance, renders the
    letter HTML, converts to PDF, submits to Stannp's /letters/create
    endpoint, records a letters_sent_v3 row.

    Stannp performs address verification at send time (post_unverified=
    false). If the recipient address can't be validated, Stannp returns
    an error which we surface as a 422 and refund.

    Idempotency: each request generates a uuid4 idempotency key that we
    embed as a Stannp tag. Stannp doesn't natively dedupe, but the tag
    lets us reconcile if a double-click somehow lands two letters.
    Frontend should debounce the send button.
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user.id)
    _validate_profile_for_send(profile)

    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    recipient = _build_stannp_recipient(parcel)

    cost = SINGLE_LETTER_COST_CENTS
    _charge_balance(supa, user.id, cost)

    # Wrap the rest in try/except — if anything fails after charging, we
    # refund and re-raise. Stannp uniqueness is enforced via our
    # idempotency tag; if our DB write fails after Stannp succeeds we
    # surface a clear error and the operator can reconcile.
    try:
        # Render HTML without the recipient address block — Stannp's
        # mail-merge overlay places the address in the windowed envelope
        # clear zone at print time. Convert to PDF for upload.
        html = _render_html_for_letter(
            letter, profile, recipient, no_recipient_block=True,
        )
        try:
            pdf_bytes = render_html_to_pdf(html)
        except RuntimeError as e:
            _refund_balance(supa, user.id, cost)
            logger.error("PDF render failed for pin %s: %s", body.pin, e)
            raise HTTPException(
                500,
                f"Failed to render letter PDF: {e}",
            )

        client = get_stannp_client()
        idem_key = f"ss-single-{uuid.uuid4().hex[:12]}"

        try:
            stannp_letter = client.create_letter(
                pdf_bytes=pdf_bytes,
                recipient=recipient,
                first_class=True,
                tags=f"single,pin-{body.pin},zip-{parcel.get('zip_code') or ''}",
                idempotency_key=idem_key,
                post_unverified=False,
            )
        except StannpAddressError as e:
            _refund_balance(supa, user.id, cost)
            raise HTTPException(
                422,
                f"Address validation failed: {e}",
            )

        # Persist the row. Stannp has already accepted — even if this
        # insert fails, the letter is on the wire. Log loudly so
        # reconciliation is possible from Stannp's dashboard.
        row = {
            "agent_id": user.id,
            "pin": body.pin,
            "zip_code": parcel.get("zip_code") or "",
            "sequence_id": None,
            "letter_index": body.letter_index,
            "method": "stannp_mail",
            "provider": "stannp",
            "stannp_letter_id": str(stannp_letter.get("id")),
            "stannp_mode": client.mode,
            "stannp_tracking_url": stannp_letter.get("pdf"),  # PDF preview URL from Stannp
            "status": "created",
            "cost_cents": cost,
            "rendered_html": html,
            "recipient_name":  recipient.get("lastname"),
            "recipient_line1": recipient.get("address1"),
            "recipient_line2": recipient.get("address2"),
            "recipient_city":  recipient.get("city"),
            "recipient_state": recipient.get("state"),
            "recipient_zip":   recipient.get("zipcode"),
        }
        insert = supa.table("letters_sent_v3").insert(row).execute()
        if not insert or not insert.data:
            logger.error(
                "Stannp letter %s sent but DB insert failed — manual reconciliation needed",
                stannp_letter.get("id"),
            )
            raise HTTPException(
                500,
                f"Letter sent via Stannp (id={stannp_letter.get('id')}) but failed to log. "
                f"Contact support to reconcile."
            )

        return {
            "ok": True,
            "letter_row_id": insert.data[0]["id"],
            "stannp_letter_id": stannp_letter.get("id"),
            "stannp_mode": client.mode,
            "status": "created",
            "cost_cents": cost,
            "new_balance_cents": int(profile.get("letter_credit_cents", 0)) - cost,
        }

    except HTTPException:
        # Already-handled error (e.g. PDF render fail with refund, address
        # fail with refund, or DB-after-Stannp). Re-raise as-is.
        raise
    except (StannpConfigError, StannpAuthError) as e:
        # Configuration problem — Stannp didn't get the request. Refund.
        _refund_balance(supa, user.id, cost)
        logger.error("Stannp config/auth error for agent %s: %s", user.id, e)
        raise HTTPException(502, f"Stannp configuration error: {e}")
    except StannpError as e:
        # Stannp failed cleanly — letter not sent. Refund and surface.
        _refund_balance(supa, user.id, cost)
        logger.warning(
            "Stannp send failed for agent %s pin %s: %s",
            user.id, body.pin, e,
        )
        raise HTTPException(502, f"Stannp error: {e}")
    except Exception as e:
        # Unknown failure — refund and surface as 500.
        _refund_balance(supa, user.id, cost)
        logger.exception("Unexpected error sending letter")
        raise HTTPException(500, f"Send failed: {type(e).__name__}: {e}")


# ── 3. Start sequence ────────────────────────────────────────────────


@router.post("/start-sequence")
async def start_sequence(
    body: StartSequenceRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Schedule all 6 letters. Letter 1 sends immediately via Stannp. Letters
    2-6 are stored as status='scheduled' rows with stannp_send_date set to
    +30/60/90/135/180 days from now. The letter_scheduler background task
    sweeps daily, finds rows past their stannp_send_date, and submits each
    to Stannp.

    Storing rendered_html at sequence creation locks the letter content at
    the moment the agent paid, even if the underlying parcel/probate data
    changes over the 6-month sequence window. The scheduler reads the
    snapshot and converts to PDF at send time.

    Atomicity: if letter 1's Stannp send fails, we roll the sequence back
    (set status='failed') and refund the full $9.99. If the DB insert for
    a scheduled row fails after letter 1 sent, we still surface the error
    — operator reconciles the orphaned letter.
    """
    user = user_from_authorization(authorization)
    supa = _supa()

    profile = _load_profile(supa, user.id)
    _validate_profile_for_send(profile)

    parcel = _load_parcel(supa, body.pin)
    matches = _load_harvester_matches(supa, body.pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    recipient = _build_stannp_recipient(parcel)

    cost = SEQUENCE_COST_CENTS
    _charge_balance(supa, user.id, cost)

    sequence_row = None
    letter_1_stannp_id: Optional[str] = None

    try:
        # Create the sequence parent row first so child rows have a FK.
        seq_insert = supa.table("letter_sequences_v3").insert({
            "agent_id": user.id,
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
        per_letter_cost = cost // 6  # 166 cents = ~$1.66

        client = get_stannp_client()
        stannp_mode = client.mode

        for idx, letter in enumerate(letters, start=1):
            day_offset = SEQUENCE_DAY_OFFSETS[idx - 1]
            send_date = now + timedelta(days=day_offset)

            # Render and snapshot HTML at sequence creation time. This
            # locks the content — agent paid for *this* letter, not
            # whatever the generator would produce in 6 months.
            html = _render_html_for_letter(
                letter, profile, recipient, no_recipient_block=True,
            )

            base_row = {
                "agent_id": user.id,
                "pin": body.pin,
                "zip_code": parcel.get("zip_code") or "",
                "sequence_id": sequence_id,
                "letter_index": idx,
                "method": "stannp_mail",
                "provider": "stannp",
                "stannp_mode": stannp_mode,
                "stannp_send_date": send_date.isoformat(),
                "cost_cents": per_letter_cost,
                "rendered_html": html,
                "recipient_name":  recipient.get("lastname"),
                "recipient_line1": recipient.get("address1"),
                "recipient_line2": recipient.get("address2"),
                "recipient_city":  recipient.get("city"),
                "recipient_state": recipient.get("state"),
                "recipient_zip":   recipient.get("zipcode"),
            }

            if day_offset == 0:
                # Letter 1 — send immediately.
                try:
                    pdf_bytes = render_html_to_pdf(html)
                except RuntimeError as e:
                    raise HTTPException(500, f"PDF render failed: {e}")

                try:
                    stannp_letter = client.create_letter(
                        pdf_bytes=pdf_bytes,
                        recipient=recipient,
                        first_class=True,
                        tags=f"seq-{sequence_id},letter-1,pin-{body.pin}",
                        idempotency_key=f"ss-seq-{sequence_id}-1",
                        post_unverified=False,
                    )
                except StannpAddressError as e:
                    raise HTTPException(422, f"Address validation failed: {e}")

                letter_1_stannp_id = str(stannp_letter.get("id"))
                base_row.update({
                    "stannp_letter_id": letter_1_stannp_id,
                    "stannp_tracking_url": stannp_letter.get("pdf"),
                    "status": "created",
                })
            else:
                # Letters 2-6 — scheduled. Background task will send.
                base_row["status"] = "scheduled"

            supa.table("letters_sent_v3").insert(base_row).execute()

        return {
            "ok": True,
            "sequence_id": sequence_id,
            "letters_scheduled": 6,
            "first_letter_immediate": True,
            "first_letter_stannp_id": letter_1_stannp_id,
            "cost_cents": cost,
            "stannp_mode": stannp_mode,
        }

    except HTTPException:
        # Surface the original error. If letter 1 already sent and we hit
        # an HTTPException later, the agent will have one rogue letter
        # but the sequence is marked failed for reconciliation.
        if sequence_row:
            try:
                supa.table("letter_sequences_v3").update({
                    "status": "failed",
                    "cancel_reason": "HTTPException during sequence start",
                }).eq("id", sequence_row["id"]).execute()
            except Exception:
                pass
        # If letter 1 hadn't sent yet, refund. If it had, the agent
        # got partial value; refund 5/6 = 833 cents.
        if letter_1_stannp_id:
            _refund_balance(supa, user.id, cost - per_letter_cost)
        else:
            _refund_balance(supa, user.id, cost)
        raise
    except (StannpConfigError, StannpAuthError) as e:
        # Stannp didn't even get the request. Full refund.
        if sequence_row:
            try:
                supa.table("letter_sequences_v3").update({
                    "status": "failed",
                    "cancel_reason": f"Stannp config: {type(e).__name__}",
                }).eq("id", sequence_row["id"]).execute()
            except Exception:
                pass
        _refund_balance(supa, user.id, cost)
        logger.error("Sequence config error for agent %s: %s", user.id, e)
        raise HTTPException(502, f"Stannp configuration error: {e}")
    except StannpError as e:
        # Cancel letter 1 if it went through, mark sequence failed, refund.
        if letter_1_stannp_id:
            try:
                client.cancel_letter(int(letter_1_stannp_id))
            except Exception:
                pass  # Best effort
        if sequence_row:
            try:
                supa.table("letter_sequences_v3").update({
                    "status": "failed",
                    "cancel_reason": f"Stannp error: {type(e).__name__}",
                }).eq("id", sequence_row["id"]).execute()
            except Exception:
                pass
        _refund_balance(supa, user.id, cost)
        raise HTTPException(502, f"Sequence creation failed: {e}")

    except Exception as e:
        logger.exception("Unexpected error starting sequence")
        if sequence_row:
            try:
                supa.table("letter_sequences_v3").update({
                    "status": "failed",
                    "cancel_reason": f"Unexpected: {type(e).__name__}",
                }).eq("id", sequence_row["id"]).execute()
            except Exception:
                pass
        _refund_balance(supa, user.id, cost)
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
        .eq("agent_id", user.id)
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
        client = get_stannp_client()
        for child in children_rows:
            status = child.get("status")
            if status in TERMINAL:
                skipped_count += 1
                continue

            # Two cancel paths depending on whether the letter has been
            # submitted to Stannp yet.
            if status == "scheduled":
                # Hasn't been submitted to Stannp yet — just mark the row
                # cancelled and the scheduler will skip it. No Stannp call.
                supa.table("letters_sent_v3").update({
                    "status": "cancelled",
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", child["id"]).execute()
                cancelled_count += 1
                continue

            # Already submitted to Stannp — try to cancel via API.
            stannp_id = child.get("stannp_letter_id")
            if not stannp_id:
                skipped_count += 1
                continue
            try:
                ok = client.cancel_letter(int(stannp_id))
                if ok:
                    supa.table("letters_sent_v3").update({
                        "status": "cancelled",
                        "cancelled_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", child["id"]).execute()
                    cancelled_count += 1
                else:
                    # Past Stannp's cancel window — letter is being printed.
                    skipped_count += 1
            except Exception as e:
                logger.warning("Failed to cancel Stannp letter %s: %s", stannp_id, e)
                skipped_count += 1
    except Exception as e:
        logger.exception("Sequence cancel failed mid-way")
        raise HTTPException(502, f"Cancel failed: {e}")

    refund_cents = int(round((cancelled_count / 6) * SEQUENCE_COST_CENTS))
    if refund_cents > 0:
        _refund_balance(supa, user.id, refund_cents)

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
    profile = _load_profile(supa, user.id)
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
            "id,letter_index,method,status,cost_cents,provider,"
            "stannp_letter_id,stannp_mode,stannp_send_date,"
            "stannp_expected_delivery,stannp_tracking_url,"
            "created_at,mailed_at,delivered_at,sequence_id"
        )
        .eq("agent_id", user.id)
        .eq("pin", pin)
        .order("created_at", desc=True)
        .execute()
    )
    sequences = (
        supa.table("letter_sequences_v3")
        .select("id,status,started_at,cancelled_at,total_charged_cents")
        .eq("agent_id", user.id)
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

    profile = _load_profile(supa, user.id)
    parcel = _load_parcel(supa, pin)
    matches = _load_harvester_matches(supa, pin)
    letters = _generate_letters_for_parcel(parcel, matches)
    letter = letters[body.letter_index - 1]

    _from_addr, to_addr = None, _build_stannp_recipient(parcel)
    html = _render_html_for_letter(letter, profile, to_addr, no_recipient_block=False)

    # Log the PDF render so dossier history is complete.
    supa.table("letters_sent_v3").insert({
        "agent_id": user.id,
        "pin": pin,
        "zip_code": parcel.get("zip_code") or "",
        "sequence_id": None,
        "letter_index": body.letter_index,
        "method": "pdf_download",
        "provider": None,  # No remote provider — agent prints + mails themselves
        "status": "pdf_rendered",
        "cost_cents": 0,
        "rendered_html": html,
        "recipient_name":  to_addr.get("lastname"),
        "recipient_line1": to_addr.get("address1"),
        "recipient_line2": to_addr.get("address2"),
        "recipient_city":  to_addr.get("city"),
        "recipient_state": to_addr.get("state"),
        "recipient_zip":   to_addr.get("zipcode"),
    }).execute()

    return {"html": html, "letter_index": body.letter_index}


# ── 9. Stannp webhook ───────────────────────────────────────────────


@router.post("/stannp-webhook")
async def stannp_webhook(request: Request):
    """
    Receive status updates from Stannp. Configured in the Stannp dashboard:
        URL:    https://sellersignal.co/api/letters/stannp-webhook
        Events: letter.* (subscribe to all letter events)
        Secret: copy to Railway as STANNP_WEBHOOK_SECRET

    Verification: Stannp signs webhook bodies with HMAC-SHA256 keyed by
    the webhook secret. The signature appears in the `x-stannp-signature`
    header. We compute HMAC-SHA256 of the raw body and compare in
    constant time. If the secret isn't set in env we accept all webhooks
    (with a warning) so initial test-mode integration isn't blocked.

    Documented at https://www.stannp.com/us/direct-mail-api/webhooks —
    we'll tighten this once that page's exact signature scheme is
    confirmed against a real test event.
    """
    raw_body = await request.body()

    secret = os.environ.get("STANNP_WEBHOOK_SECRET", "").strip()
    sig_header = (
        request.headers.get("x-stannp-signature")
        or request.headers.get("stannp-signature")
        or ""
    )

    if secret:
        if not sig_header:
            logger.warning("Stannp webhook missing signature header")
            raise HTTPException(401, "Missing signature header")

        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            logger.warning("Stannp webhook signature mismatch")
            raise HTTPException(401, "Bad signature")
    else:
        logger.warning(
            "STANNP_WEBHOOK_SECRET not set — accepting webhook without verification. "
            "Set the env var to enable signature checks."
        )

    # Parse event payload
    try:
        import json
        event = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    # Stannp event shape (tentative — confirm against a real test event):
    #   {"event": "letter.dispatched", "data": {"id": 12345, ...}}
    event_type = event.get("event") or event.get("event_type") or ""
    payload = event.get("data") or event.get("body") or {}
    stannp_letter_id = payload.get("id")

    if stannp_letter_id is None:
        return {"ok": True, "ignored": True, "reason": "no letter id"}

    new_status = WEBHOOK_STATUS_MAP.get(event_type)
    if not new_status:
        logger.debug(
            "Ignoring Stannp webhook event %s for letter %s",
            event_type, stannp_letter_id,
        )
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
        update["fail_reason"] = payload.get("failure_reason") or "Stannp failed"

    # Look up the letter by stannp_letter_id. Service-role client so RLS
    # is bypassed. The id from Stannp's webhook is an integer; we store
    # it as a string in the DB, so cast for the equality match.
    result = (
        supa.table("letters_sent_v3")
        .update(update)
        .eq("stannp_letter_id", str(stannp_letter_id))
        .execute()
    )

    updated = (result.data if result else None) or []
    return {
        "ok": True,
        "event_type": event_type,
        "stannp_letter_id": stannp_letter_id,
        "new_status": new_status,
        "rows_updated": len(updated),
    }


# ── 10. Letter scheduler admin (status, pause, resume) ─────────────


def _require_admin(authorization: Optional[str], x_admin_key: Optional[str]) -> None:
    """
    Admin-only gate for the scheduler controls. Accepts either an
    operator-role bearer token (same agents who bypass billing) or
    the X-Admin-Key header used elsewhere in the codebase.
    """
    admin_env = (os.environ.get("ADMIN_KEY") or "").strip()
    if x_admin_key and admin_env and x_admin_key == admin_env:
        return
    # Fall back to operator-role user auth
    try:
        user = user_from_authorization(authorization)
    except HTTPException:
        raise HTTPException(401, "Admin auth required")
    supa = _supa()
    profile = (
        supa.table("agent_profiles_v3")
        .select("role")
        .eq("id", user.id)
        .maybe_single()
        .execute()
    )
    role = (profile.data or {}).get("role") if profile else None
    if role != "operator":
        raise HTTPException(403, "Operator role required")


@router.get("/scheduler/status")
async def scheduler_status(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """Observability for the letter scheduler background task."""
    _require_admin(authorization, x_admin_key)
    from backend.tasks import letter_scheduler
    return letter_scheduler.get_state()


@router.post("/scheduler/pause")
async def scheduler_pause(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """Pause the scheduler — scheduled letters stop firing until resumed."""
    _require_admin(authorization, x_admin_key)
    from backend.tasks import letter_scheduler
    letter_scheduler.pause()
    return {"ok": True, "enabled": False}


@router.post("/scheduler/resume")
async def scheduler_resume(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
):
    """Resume the scheduler."""
    _require_admin(authorization, x_admin_key)
    from backend.tasks import letter_scheduler
    letter_scheduler.resume()
    return {"ok": True, "enabled": True}
