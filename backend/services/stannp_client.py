"""
backend/services/stannp_client.py — Stannp API HTTP client.

Stannp is the production replacement for Lob (see backend/services/
lob_client.py for the predecessor). Same general shape: HTTP Basic auth
with the API key as username, REST endpoints, JSON responses.

Endpoints used:
  POST /v1/letters/create        — create a letter with mail merge
  GET  /v1/letters/get/{id}      — fetch current state
  POST /v1/letters/cancel        — cancel before processing

The mail-merge endpoint (/letters/create) is preferred over /letters/post
(pre-merged) because Stannp owns the address clear zone — they overlay
the recipient address onto our PDF at print time, so positioning is
always correct regardless of our renderer's exact pixel math.

Authentication: HTTP Basic, API key as the username, empty password.
  curl -u {API_KEY}: ...

Mode switching:
  STANNP_MODE=test  → adds test=1 to every send. PDFs are produced but
                      not dispatched and no charge is taken. Good for
                      dev + sandbox testing.
  STANNP_MODE=live  → real mail, real charges.

This module does NOT touch the database. Callers (backend/api/letters.py)
are responsible for persistence, billing, and webhook reconciliation.
"""

from __future__ import annotations

import os
import time
import uuid
import logging
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


# US Stannp endpoint. They route per region — api-us1 for the US, api-eu1
# for UK/EU. Our customers are US-only so we hardcode US.
STANNP_BASE_URL = "https://api-us1.stannp.com/v1"

# Network timeouts. Stannp's letter creation accepts file uploads, so the
# write timeout needs to be generous to handle 100-500 KB PDFs over slow
# connections.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)

# Retry policy. Stannp is reliable in production but transient 5xx during
# their deploys is rare-but-real. 3 attempts with exponential backoff.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


# ────────────────────────────────────────────────────────────────────
# Exceptions — structured failure types so the API layer can return
# appropriate HTTP status codes without parsing error strings.
# ────────────────────────────────────────────────────────────────────


class StannpError(Exception):
    """Base for all Stannp-related errors."""

    def __init__(self, message: str, status_code: int = 0, stannp_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.stannp_data = stannp_data or {}


class StannpConfigError(StannpError):
    """Misconfigured client: missing key, bad mode."""


class StannpAuthError(StannpError):
    """401/403 from Stannp — key invalid or insufficient permissions."""


class StannpAddressError(StannpError):
    """Address verification failed or address is undeliverable."""


class StannpRateLimitError(StannpError):
    """429 from Stannp. Growth tier has 600/min limit."""


# ────────────────────────────────────────────────────────────────────
# Client
# ────────────────────────────────────────────────────────────────────


class StannpClient:
    """
    Stannp HTTP client. Construct once and reuse — internally pools
    httpx connections. Mode (test/live) comes from STANNP_MODE env var
    by default but can be overridden per-instance.

    Usage:
        from backend.services.stannp_client import StannpClient
        client = StannpClient()
        letter = client.create_letter(
            pdf_bytes=pdf,
            recipient={
                'firstname': 'Joseph',
                'lastname':  'Bryant',
                'address1':  '12345 NE 8th St',
                'city':      'Bellevue',
                'zipcode':   '98004',
                'country':   'US',
            },
            first_class=True,
            tags='probate,98004',
        )
        print(letter['id'], letter['cost'])
    """

    def __init__(self, mode: Optional[str] = None):
        resolved_mode = (mode or os.environ.get("STANNP_MODE") or "test").strip().lower()
        if resolved_mode not in ("test", "live"):
            raise StannpConfigError(
                f"STANNP_MODE must be 'test' or 'live', got {resolved_mode!r}"
            )
        self.mode = resolved_mode

        api_key = os.environ.get("STANNP_API_KEY", "").strip()
        if not api_key:
            raise StannpConfigError(
                "STANNP_API_KEY environment variable is not set. "
                "Set it in Railway env vars before sending mail."
            )
        self.api_key = api_key

        # httpx.Auth via tuple — Stannp expects API key as username,
        # empty password. Same pattern as Lob.
        self._auth = (self.api_key, "")
        self._client = httpx.Client(
            base_url=STANNP_BASE_URL,
            timeout=DEFAULT_TIMEOUT,
            auth=self._auth,
        )

    def close(self) -> None:
        self._client.close()

    # ── Internal request helper ────────────────────────────────────

    def _post(
        self,
        path: str,
        *,
        data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, tuple]] = None,
    ) -> dict[str, Any]:
        """
        POST to Stannp with retry on transient 5xx. Returns the parsed
        `data` field on success. Raises typed exceptions on failure.

        Stannp response envelope:
          {"success": true, "data": {...}}  on success
          {"success": false, "error": "..."} on failure

        Even when HTTP status is 200, success=false means a logical
        error (bad address, etc.) — we raise so callers don't have to
        check both.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.post(path, data=data, files=files)
                # 5xx — retry
                if 500 <= resp.status_code < 600:
                    raise StannpError(
                        f"Stannp {resp.status_code} on {path}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                # Parse envelope
                try:
                    payload = resp.json()
                except Exception:
                    raise StannpError(
                        f"Stannp returned non-JSON ({resp.status_code}): {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                # 401/403 — auth issue, don't retry
                if resp.status_code in (401, 403):
                    raise StannpAuthError(
                        f"Stannp auth failed: {payload.get('error') or resp.text[:200]}",
                        status_code=resp.status_code,
                        stannp_data=payload,
                    )

                # 429 — rate limited
                if resp.status_code == 429:
                    raise StannpRateLimitError(
                        "Stannp rate limit exceeded",
                        status_code=429,
                        stannp_data=payload,
                    )

                # Logical failure inside a 200
                if not payload.get("success"):
                    err = payload.get("error") or "Unknown Stannp error"
                    # Heuristic: address-related failures get a more
                    # specific exception so /letters/send can surface
                    # a clean message to the agent.
                    err_lower = str(err).lower()
                    if any(t in err_lower for t in ("address", "zip", "undeliverable", "verify")):
                        raise StannpAddressError(
                            err,
                            status_code=resp.status_code,
                            stannp_data=payload,
                        )
                    raise StannpError(
                        err,
                        status_code=resp.status_code,
                        stannp_data=payload,
                    )

                return payload.get("data") or {}

            except (StannpAuthError, StannpAddressError, StannpRateLimitError):
                # Don't retry these — they won't get better on retry.
                raise
            except (StannpError, httpx.HTTPError) as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    backoff = RETRY_BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Stannp %s attempt %d failed: %s — backing off %.1fs",
                        path, attempt + 1, e, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise

        # Unreachable in practice; the loop either returns or raises.
        if last_exc:
            raise last_exc
        raise StannpError(f"Stannp {path} failed after retries")

    def _get(self, path: str) -> dict[str, Any]:
        """GET helper. Same envelope handling as _post."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.get(path)
                if 500 <= resp.status_code < 600:
                    raise StannpError(
                        f"Stannp {resp.status_code} on {path}",
                        status_code=resp.status_code,
                    )
                try:
                    payload = resp.json()
                except Exception:
                    raise StannpError(
                        f"Stannp returned non-JSON ({resp.status_code}): {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                if not payload.get("success"):
                    raise StannpError(
                        payload.get("error") or "Unknown error",
                        status_code=resp.status_code,
                        stannp_data=payload,
                    )
                return payload.get("data") or {}
            except (StannpError, httpx.HTTPError) as e:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise

    # ── Public API ─────────────────────────────────────────────────

    def create_letter(
        self,
        *,
        pdf_bytes: bytes,
        recipient: dict[str, str],
        first_class: bool = True,
        confidential: bool = False,
        tags: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        post_unverified: bool = False,
        size: str = "US-LETTER",
        duplex: bool = False,
    ) -> dict[str, Any]:
        """
        Create a letter with Stannp's mail-merge endpoint. Stannp prints
        the body content from the PDF we upload and overlays the recipient
        address onto the clear zone.

        Args:
          pdf_bytes:        Raw PDF bytes (rendered by letter_pdf_renderer).
                            Must NOT contain a recipient address — Stannp
                            puts it on. Max 25 pages.
          recipient:        Dict with title, firstname, lastname, company,
                            address1, address2, city, zipcode, country.
                            'firstname'+'lastname' or 'company' required.
          first_class:      True for First-Class postage (~5-7 days). False
                            for Standard (marketing-only, 10-15 days).
          confidential:     True to use Stannp's confidential envelope.
          tags:             Comma-separated tags for filtering in Stannp
                            reporting. We use 'probate,98004' etc.
          idempotency_key:  Stannp doesn't have a dedicated idempotency
                            header, but they de-dupe per tag suffix if
                            included. We pass it as a tag.
          post_unverified:  If False (default), Stannp won't send if their
                            address verification can't validate. Errors back.
          size:             "US-LETTER" (default) or "US-LETTER-XL-WINDOW"
                            for the larger address window.
          duplex:           Double-sided. Default False (single-sided) —
                            most condolence letters are one page.

        Returns the Stannp letter object: id, cost, status, format, pdf URL,
        tracking_ref. In test mode the id is 0 and status is "test".
        """
        # Build form data. Stannp uses flat form encoding with bracket
        # syntax for nested recipient fields.
        data: dict[str, Any] = {
            "size": size,
            "duplex": "true" if duplex else "false",
            "post_unverified": "true" if post_unverified else "false",
        }
        if self.mode == "test":
            data["test"] = "1"

        # Flatten recipient with bracket keys: recipient[firstname], etc.
        # Skip empty values so Stannp doesn't reject blank lines.
        for k, v in recipient.items():
            if v is None or v == "":
                continue
            data[f"recipient[{k}]"] = str(v)

        # Build tags string. Include idempotency key as a tag prefix —
        # callers can search by it in Stannp reporting later.
        tag_parts: list[str] = []
        if tags:
            tag_parts.append(tags)
        if idempotency_key:
            tag_parts.append(f"idem-{idempotency_key}")
        if tag_parts:
            data["tags"] = ",".join(tag_parts)

        # Addons — comma-separated codes per their API.
        addons: list[str] = []
        if first_class:
            addons.append("FIRST_CLASS")
        if confidential:
            addons.append("CONFIDENTIAL")
        if addons:
            data["addons"] = ",".join(addons)

        # PDF upload via multipart. Stannp accepts either a URL string
        # in `file=` or a binary upload in the same field. Binary upload
        # is safer (no need to host the PDF publicly).
        files = {
            "file": (
                f"letter-{idempotency_key or uuid.uuid4().hex[:8]}.pdf",
                pdf_bytes,
                "application/pdf",
            ),
        }

        return self._post("/letters/create", data=data, files=files)

    def get_letter(self, letter_id: int) -> dict[str, Any]:
        """
        Fetch current state of a letter by Stannp ID. Returns the full
        mailpiece object including status, tracking_ref, dispatched
        timestamp, and cost.

        Status values from Stannp's lifecycle:
          'pending'    — accepted, queued for print
          'printed'    — physical piece produced
          'dispatched' — handed to USPS
          'delivered'  — delivery confirmed (if tracking available)
          'cancelled'  — cancelled before dispatch
          'failed'     — terminal failure (address rejected, etc.)
        """
        return self._get(f"/letters/get/{letter_id}")

    def cancel_letter(self, letter_id: int) -> bool:
        """
        Cancel a letter if it hasn't been processed yet. Returns True
        on success. Stannp's cancel window is roughly the same as Lob's
        — letters can be cancelled up until they enter the print queue.

        Returns False if cancel was rejected (already processing).
        """
        try:
            result = self._post("/letters/cancel", data={"id": str(letter_id)})
            # Stannp returns {data: 1} on success. Any truthy value counts.
            return bool(result) if isinstance(result, (int, dict)) else True
        except StannpError as e:
            logger.warning("Stannp cancel %s failed: %s", letter_id, e)
            return False


# ────────────────────────────────────────────────────────────────────
# Module-level convenience — one shared client per process.
# ────────────────────────────────────────────────────────────────────


_default_client: Optional[StannpClient] = None


def get_client() -> StannpClient:
    """
    Get the process-wide Stannp client, lazily constructed. Callers
    should use this rather than instantiating StannpClient directly so
    we don't open new httpx connection pools per request.
    """
    global _default_client
    if _default_client is None:
        _default_client = StannpClient()
    return _default_client
