"""
backend/services/letter_renderer.py — assemble Lob-ready letter HTML.

Takes:
  - the rendered letter body (from letter_content.py)
  - the agent's profile (signature URL, name, return address)
  - the recipient's address
  - the agency logo (read from data/letterheads/the-agency.svg)

Returns:
  HTML string suitable for POST /v1/letters file= field.

Layout (8.5" × 11" page, Lob standard #10 double-window envelope):
  - Top:    agency logo + recipient address block (positioned for the
            lower-left window of the double-window envelope when the
            letter is tri-folded)
  - Body:   letter content paragraphs
  - Bottom: signature image (if available) and agent typed name

The recipient address block must land within Lob's required address
window when the letter is folded. Per Lob's letter template specs:
  - Recipient address sits in a 4.5" × 1.125" area
  - Positioned 0.5" from left, ~3.875" from top of the unfolded page
  - This corresponds to the lower-left envelope window after tri-fold

We use inline CSS (no <link> tags) and inline the SVG logo as a data
URI. Lob's renderer doesn't fetch external resources reliably.

The return address printed on the ENVELOPE is set by Lob from the
from= field of the create_letter call — we don't need to put it on
the letter itself. We include the agent's name and brokerage tagline
in the closing for the recipient's reference.
"""

import base64
import logging
import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


# Default logo path. Will be made per-agent later when we add upload UI.
DEFAULT_LOGO_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "letterheads" / "the-agency.svg"
)


def _load_logo_data_uri(logo_path: Optional[Path] = None) -> str:
    """
    Read the SVG logo from disk and return a data:image/svg+xml;base64,...
    string suitable for embedding in an <img src=""> tag.

    Returns empty string if the file is missing — caller can choose
    to render without a logo rather than crash.
    """
    path = logo_path or DEFAULT_LOGO_PATH
    try:
        svg_bytes = path.read_bytes()
    except FileNotFoundError:
        logger.warning("Letterhead logo not found at %s — rendering without logo", path)
        return ""
    except Exception as e:
        logger.warning("Failed to read letterhead logo at %s: %s", path, e)
        return ""

    encoded = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _fetch_signature_data_uri(signature_url: Optional[str]) -> str:
    """
    Fetch the agent's signature image (PNG with transparent background,
    stored in Supabase storage) and return a data URI.

    Network fetch with short timeout — signatures live at a public
    Supabase URL. Returns empty string on any failure; caller falls
    back to typed-name signature.
    """
    if not signature_url:
        return ""

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            resp = client.get(signature_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png")
            # Guard against being served HTML (e.g. a 404 page that
            # returned 200 from a CDN) — only accept image responses.
            if not content_type.startswith("image/"):
                logger.warning(
                    "Signature URL returned non-image content-type %r — skipping",
                    content_type,
                )
                return ""
            encoded = base64.b64encode(resp.content).decode("ascii")
            return f"data:{content_type};base64,{encoded}"
    except Exception as e:
        logger.warning("Failed to fetch signature from %s: %s", signature_url, e)
        return ""


def _format_recipient_block(
    recipient_name: Optional[str],
    line1: str,
    line2: Optional[str],
    city: str,
    state: str,
    zip_code: str,
) -> str:
    """Produce the recipient address block as escaped HTML lines."""
    lines = []
    if recipient_name:
        lines.append(escape(recipient_name))
    lines.append(escape(line1))
    if line2:
        lines.append(escape(line2))
    lines.append(f"{escape(city)}, {escape(state)} {escape(zip_code)}")
    return "<br>".join(lines)


def _format_body_paragraphs(body: str) -> str:
    """
    Convert the letter body's plain-text paragraphs (separated by blank
    lines) into HTML <p> blocks. Preserves intentional line breaks
    inside a paragraph as <br>.
    """
    body = body.strip()
    # Normalize line endings
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    # Split on blank lines (one or more)
    paragraphs = re.split(r"\n\s*\n", body)
    html_parts = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Within a paragraph, escape HTML and convert single \n to <br>
        escaped = escape(para).replace("\n", "<br>")
        html_parts.append(f"<p>{escaped}</p>")
    return "\n".join(html_parts)


def render_letter_html(
    *,
    body: str,
    recipient_name: Optional[str],
    recipient_line1: str,
    recipient_line2: Optional[str] = None,
    recipient_city: str,
    recipient_state: str,
    recipient_zip: str,
    agent_full_name: str,
    agent_phone: Optional[str] = None,
    agent_email: Optional[str] = None,
    agent_signature_url: Optional[str] = None,
    logo_path: Optional[Path] = None,
    no_recipient_block: bool = False,
) -> str:
    """
    Render the full letter HTML string.

    All keyword-only for clarity at the call site — there are six
    required address fields and getting the order wrong would silently
    mis-mail a letter.

    Returns a complete <html>...</html> document. The result fits on
    a single 8.5x11 page; if content overflows, the print provider
    will auto-paginate and bill extra postage at the per-sheet rate.

    Args:
      no_recipient_block:
        When True, the recipient address block is omitted. This is the
        mode used for Stannp's /letters/create endpoint, where Stannp
        performs its own mail-merge and overlays the recipient address
        onto the page's clear zone at print time. The salutation
        ("Dear Mr. Smith") stays in the body — only the postal address
        block above the body is skipped. Default False preserves the
        original Lob behavior where we embed the address ourselves.

      All recipient_* parameters are still required even when
      no_recipient_block=True — the print provider needs them
      separately as structured data to do their own overlay, and the
      caller (backend/api/letters.py) reads them from the same kwargs.

    Rendering note: this function targets xhtml2pdf (see
    backend/services/letter_pdf_renderer.py). xhtml2pdf has limited
    CSS selector support and adds aggressive default vertical spacing
    when you use class-scoped paragraph rules. We render the letter
    as a flat tree of element-selected `<p>` and `<div>` nodes with
    element-level CSS rules — no .page wrapper, no .body / .header /
    .signature-block containers. Margins via @page rule rather than
    div padding so xhtml2pdf doesn't double-count.

    Logo rendering: we previously embedded the agency SVG logo as a
    data URI. xhtml2pdf's SVG backend renders SVGs poorly. The logo
    is now omitted — to bring it back, pre-render to PNG and embed
    that. Tracked as a follow-up.
    """
    body_html = _format_body_paragraphs(body)

    # Build the recipient block as a `<p>` element. Used only when the
    # caller wants the address embedded in the page (preview + PDF
    # download paths). Stannp's mail-merge path passes no_recipient_block=
    # True and skips this entirely.
    if no_recipient_block:
        recipient_block_html = ""
    else:
        recipient_lines = _format_recipient_block(
            recipient_name,
            recipient_line1,
            recipient_line2,
            recipient_city,
            recipient_state,
            recipient_zip,
        )
        recipient_block_html = (
            f'<p style="margin-top:0; margin-bottom:18pt;">{recipient_lines}</p>'
        )

    # Signature line — italic Georgia per the brand. xhtml2pdf doesn't
    # do raster signature images well either (they render but at low
    # fidelity); the italic-name fallback prints cleanly.
    signature_html = (
        f'<p style="margin-top:14pt; margin-bottom:0; '
        f'font-style:italic; font-size:14pt;">'
        f'{escape(agent_full_name)}</p>'
    )

    # Contact line under signature. Phone + email separated by a middle
    # dot. Phone is required at the API layer; email is best-effort.
    contact_parts = []
    if agent_phone:
        contact_parts.append(escape(agent_phone))
    if agent_email:
        contact_parts.append(escape(agent_email))
    contact_html = ""
    if contact_parts:
        contact_html = (
            f'<p style="margin-top:6pt; margin-bottom:0; '
            f'font-size:10pt; color:#555;">'
            f'{" &middot; ".join(contact_parts)}</p>'
        )

    today = datetime.now(timezone.utc).strftime("%B %-d, %Y")

    # Flat, minimal HTML. No wrappers. Element-level CSS. Whitespace
    # between tags collapsed so xhtml2pdf doesn't interpret it as
    # text nodes.
    return (
        '<!DOCTYPE html>'
        '<html><head><meta charset="utf-8"><style>'
        '@page { size: 8.5in 11in; margin: 2.5in 0.85in 0.5in 0.85in; }'
        'body { font-family: Georgia, "Times New Roman", serif; font-size: 11pt; color: #1a1a1a; }'
        'p { margin: 0 0 8pt 0; line-height: 14pt; }'
        '.date { font-size: 10.5pt; color: #555; margin-bottom: 14pt; }'
        '.closing { margin-top: 14pt; margin-bottom: 0; }'
        '</style></head><body>'
        f'<p class="date">{today}</p>'
        f'{recipient_block_html}'
        f'{body_html}'
        f'{signature_html}'
        f'{contact_html}'
        '</body></html>'
    )
