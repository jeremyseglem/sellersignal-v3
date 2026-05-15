"""
backend/services/lob_client.py — thin wrapper around the Lob API.

Lob's REST API is straightforward (JSON over HTTPS, HTTP Basic auth with
the API key as username), so we skip their Python SDK and call directly.
The SDK adds a heavy dependency tree and obscures the wire protocol;
for the four endpoints we need, direct httpx is cleaner.

Endpoints used:
  POST /v1/us_verifications     — validate a US address before sending
  POST /v1/letters              — create a letter (immediate or scheduled)
  DELETE /v1/letters/{id}       — cancel before send_date passes
  GET /v1/letters/{id}          — fetch current state

This module does NOT touch the database. Callers (backend/api/letters.py)
are responsible for persistence, billing, and webhook reconciliation.

Mode switching:
  LOB_MODE=test (default)  → uses LOB_TEST_API_KEY, sandbox, no real mail
  LOB_MODE=live            → uses LOB_LIVE_API_KEY, real mail + charges

The live mode key only works after a payment method is attached to the
Lob account. Until then it silently fails on /v1/letters with a 403.
We catch that and surface a clearer error.
"""

import os
import time
import uuid
import logging
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)

LOB_BASE_URL = "https://api.lob.com/v1"

# Network timeouts — Lob is generally fast but address verification can
# take a couple seconds. Connect timeout short, total timeout generous.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)

# Retry policy. Lob occasionally returns transient 5xx during deploys;
# 3 attempts with exponential backoff handles all the cases we've seen.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


# ────────────────────────────────────────────────────────────────────
# Exceptions — give callers structured failure types so the API layer
# can return appropriate HTTP status codes without parsing strings.
# ────────────────────────────────────────────────────────────────────


class LobError(Exception):
    """Base for all Lob-related errors."""

    def __init__(self, message: str, status_code: int = 0, lob_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.lob_code = lob_code


class LobConfigError(LobError):
    """Misconfigured client: missing key, bad mode, no payment method on file."""


class LobAuthError(LobError):
    """401/403 from Lob — key invalid or insufficient permissions."""


class LobAddressError(LobError):
    """Address verification failed or address is undeliverable.

    Lob returns deliverability codes like 'deliverable_missing_unit',
    'undeliverable', etc. Surfaced in lob_code so callers can show the
    user an actionable message ('add unit number' vs 'totally wrong').
    """


class LobNotFoundError(LobError):
    """404 — letter ID doesn't exist (already deleted, or was never created)."""


class LobRateLimitError(LobError):
    """429 — backed off too aggressively or hit a hard cap."""


class LobNetworkError(LobError):
    """Couldn't reach Lob at all (DNS, connection refused, timeout)."""


# ────────────────────────────────────────────────────────────────────
# Client
# ────────────────────────────────────────────────────────────────────


class LobClient:
    """
    Synchronous Lob API client.

    Instantiate once per request handler — the underlying httpx.Client
    pools connections. The default mode comes from LOB_MODE env var
    ('test' or 'live'); callers can override with mode= for ad-hoc.

    Example:
        client = LobClient()
        verified = client.verify_address(
            line1="123 Main St", city="Bellevue", state="WA", zip_code="98004"
        )
        letter = client.create_letter(
            from_address=verified_from, to_address=verified,
            html_body="<html>...</html>",
            description="SellerSignal letter 1/6 to pin 471720-0260",
            metadata={"agent_id": "...", "pin": "...", "letter_index": "1"},
        )
        # later: client.cancel_letter(letter["id"])
    """

    def __init__(self, mode: Optional[str] = None):
        # Mode resolution: explicit arg → env var → default 'test'.
        # Default to test so accidentally instantiating without config
        # in dev/test runs against the sandbox, never live.
        resolved_mode = (mode or os.environ.get("LOB_MODE") or "test").strip().lower()
        if resolved_mode not in ("test", "live"):
            raise LobConfigError(
                f"LOB_MODE must be 'test' or 'live', got {resolved_mode!r}"
            )
        self.mode = resolved_mode

        # Key selection. Each mode uses its own key — we never read
        # the live key in test mode. If the active mode's key is
        # missing, fail loudly at construction (not later at send time)
        # so misconfiguration is obvious.
        env_var = "LOB_TEST_API_KEY" if self.mode == "test" else "LOB_LIVE_API_KEY"
        key = (os.environ.get(env_var) or "").strip()
        if not key:
            raise LobConfigError(
                f"{env_var} not set in environment. "
                f"Add it to Railway env vars before instantiating LobClient(mode={self.mode!r})."
            )
        self._key = key

        # Lob auth is HTTP Basic with the API key as username and empty
        # password. httpx handles the base64 encoding.
        self._auth = httpx.BasicAuth(username=self._key, password="")

        # Single httpx client per LobClient — keeps connection pool.
        self._http = httpx.Client(
            base_url=LOB_BASE_URL,
            auth=self._auth,
            timeout=DEFAULT_TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": "SellerSignal/1.0 (Lob client)",
            },
        )

    # Context manager support — `with LobClient() as client:` cleans
    # up the httpx connection pool automatically.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying HTTP client and release the connection pool."""
        try:
            self._http.close()
        except Exception:
            pass

    # ── Public API ──────────────────────────────────────────────────

    def verify_address(
        self,
        line1: str,
        city: str,
        state: str,
        zip_code: str,
        line2: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Validate a US address against USPS data. Returns the cleaned/
        standardized address dict, or raises LobAddressError if the
        address is undeliverable.

        Lob normalizes formatting (case, USPS-standard abbreviations)
        and adds a deliverability flag. We treat anything except
        'deliverable' and 'deliverable_missing_unit' as a hard fail —
        no point mailing if USPS won't deliver.

        Verification is FREE in test mode and ~$0.01 in live mode. We
        call it before every letter create to guarantee Lob accepts.
        """
        payload = {
            "primary_line": line1.strip(),
            "city": city.strip(),
            "state": state.strip().upper(),
            "zip_code": str(zip_code).strip(),
        }
        if line2:
            payload["secondary_line"] = line2.strip()

        resp = self._request("POST", "/us_verifications", json=payload)
        verified = resp.json()

        deliverability = verified.get("deliverability") or ""
        if deliverability in ("undeliverable", "deliverable_incorrect_unit"):
            raise LobAddressError(
                f"Address is {deliverability}: {line1}, {city} {state} {zip_code}",
                lob_code=deliverability,
            )

        # Build a Lob-shape address dict the create_letter call can
        # use directly. Name is passed through unverified — Lob doesn't
        # check it against the address.
        return {
            "name": (name or "").strip() or None,
            "address_line1": verified["primary_line"],
            "address_line2": verified.get("secondary_line") or None,
            "address_city":  verified["components"]["city"],
            "address_state": verified["components"]["state"],
            "address_zip":   verified["components"]["zip_code"],
            "address_country": "US",
            "_deliverability": deliverability,  # for caller logging
        }

    def create_letter(
        self,
        from_address: dict[str, Any],
        to_address: dict[str, Any],
        html_body: str,
        description: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        send_date: Optional[str] = None,  # ISO-8601 date, e.g. '2026-06-15'
        color: bool = True,
        double_sided: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a letter. Returns the Lob letter object (dict with id,
        expected_delivery_date, url, etc.).

        idempotency_key: if provided, Lob guarantees that retries with
        the same key return the same letter (no duplicate mail). We
        generate one if the caller doesn't, so accidental double-clicks
        on the send button don't double-charge the agent.

        send_date: pass an ISO date to schedule. Lob processes letters
        only on weekdays; if send_date falls on a weekend it's pushed
        to the next business day. Letters can be cancelled free of
        charge anytime before send_date passes (5-minute window for
        immediate sends — 'cancellation window' on the Lob plan tier).
        """
        # Strip private fields from address dicts before sending to Lob.
        # The _deliverability hint we added in verify_address is for our
        # logs only — Lob would reject it as an unknown field.
        def _clean_address(addr: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in addr.items() if not k.startswith("_") and v is not None}

        payload: dict[str, Any] = {
            "to":   _clean_address(to_address),
            "from": _clean_address(from_address),
            "file": html_body,
            "color": color,
            "double_sided": double_sided,
        }
        if description:
            # Lob caps description at 255 chars.
            payload["description"] = description[:255]
        if metadata:
            # Lob allows up to 20 keys, 40-char keys, 500-char values.
            # Trim defensively rather than reject.
            payload["metadata"] = {
                str(k)[:40]: str(v)[:500]
                for k, v in list(metadata.items())[:20]
            }
        if send_date:
            payload["send_date"] = send_date

        # Idempotency key — auto-generate if missing so retries are safe.
        idem = idempotency_key or f"ss-{uuid.uuid4()}"

        resp = self._request(
            "POST",
            "/letters",
            json=payload,
            headers={"Idempotency-Key": idem},
        )
        return resp.json()

    def cancel_letter(self, lob_letter_id: str) -> dict[str, Any]:
        """
        Cancel a scheduled letter. Only works if send_date hasn't
        passed (5-minute window for immediate sends, longer for
        scheduled). Returns {'id': ..., 'deleted': True} on success.

        Raises LobNotFoundError if the letter is already past its
        cancellation window — Lob returns 404 in that case (it treats
        cancelled and uncancellable identically from the API's view).
        """
        if not lob_letter_id:
            raise LobError("cancel_letter requires a lob_letter_id")
        resp = self._request("DELETE", f"/letters/{lob_letter_id}")
        return resp.json()

    def get_letter(self, lob_letter_id: str) -> dict[str, Any]:
        """
        Fetch current letter state. Useful for reconciliation when a
        webhook is missed or to manually check status from an admin
        endpoint.
        """
        if not lob_letter_id:
            raise LobError("get_letter requires a lob_letter_id")
        resp = self._request("GET", f"/letters/{lob_letter_id}")
        return resp.json()

    # ── Internals ───────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Single request with retry on transient errors (network / 5xx).
        Raises the appropriate LobError subclass on non-retryable
        failures.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._http.request(method, path, json=json, headers=headers)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                # Transient — retry with backoff
                last_exc = e
                logger.warning(
                    "Lob %s %s network error (attempt %d): %s",
                    method, path, attempt + 1, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise LobNetworkError(f"Network error reaching Lob: {e}") from e
            except httpx.HTTPError as e:
                # Other httpx errors — don't retry, surface immediately
                raise LobNetworkError(f"HTTP error reaching Lob: {e}") from e

            # Got a response. Decide based on status.
            if 200 <= resp.status_code < 300:
                return resp

            if resp.status_code in (500, 502, 503, 504):
                # 5xx transient — retry
                last_exc = LobError(
                    f"Lob server error {resp.status_code}",
                    status_code=resp.status_code,
                )
                logger.warning(
                    "Lob %s %s returned %d (attempt %d)",
                    method, path, resp.status_code, attempt + 1,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue

            # Non-retryable — map to a specific exception type and raise
            self._raise_for_response(resp)

        # Exhausted retries on a transient — re-raise the last one
        if last_exc:
            raise last_exc
        raise LobError("Lob request failed with no recorded exception")

    def _raise_for_response(self, resp: httpx.Response) -> None:
        """Convert a non-2xx Lob response into the right exception type."""
        try:
            body = resp.json()
        except Exception:
            body = {}

        # Lob error shape: {"error": {"message": "...", "code": "...", "status_code": ...}}
        err = body.get("error") or {}
        message = err.get("message") or resp.text or f"HTTP {resp.status_code}"
        lob_code = err.get("code") or ""

        # Live-key-but-no-payment-method case — Lob returns 403 with
        # a message about "payment method" or "billing address" (the
        # exact phrasing varies). Surface a clearer error so the
        # operator knows what to do.
        if resp.status_code == 403 and any(
            k in message.lower() for k in ("payment", "billing")
        ):
            raise LobConfigError(
                "Lob live key requires a billing address / payment method "
                "on file. Add one at https://dashboard.lob.com/settings/billing "
                "before using LOB_MODE=live.",
                status_code=403,
                lob_code=lob_code,
            )

        if resp.status_code in (401, 403):
            raise LobAuthError(message, status_code=resp.status_code, lob_code=lob_code)
        if resp.status_code == 404:
            raise LobNotFoundError(message, status_code=404, lob_code=lob_code)
        if resp.status_code == 422:
            # Validation — usually address-related on letters/verifications.
            # Surface as LobAddressError if the error mentions an address
            # field, else as a plain LobError.
            addr_keywords = ("address", "deliver", "zip", "city", "state")
            if any(k in message.lower() for k in addr_keywords):
                raise LobAddressError(message, status_code=422, lob_code=lob_code)
            raise LobError(message, status_code=422, lob_code=lob_code)
        if resp.status_code == 429:
            raise LobRateLimitError(message, status_code=429, lob_code=lob_code)

        # Catch-all
        raise LobError(message, status_code=resp.status_code, lob_code=lob_code)
