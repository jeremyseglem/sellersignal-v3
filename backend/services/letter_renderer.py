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
    agent_signature_url: Optional[str] = None,
    logo_path: Optional[Path] = None,
) -> str:
    """
    Render the full letter HTML string for Lob.

    All keyword-only for clarity at the call site — there are six
    required address fields and getting the order wrong would silently
    mis-mail a letter.

    Returns a complete <html>...</html> document. Lob renders this as
    a single 8.5x11 page; if content overflows, Lob auto-paginates and
    bills extra postage at the per-sheet rate. We size content to fit
    one sheet for now.
    """
    logo_uri = _load_logo_data_uri(logo_path)
    signature_uri = _fetch_signature_data_uri(agent_signature_url)

    recipient_block = _format_recipient_block(
        recipient_name,
        recipient_line1,
        recipient_line2,
        recipient_city,
        recipient_state,
        recipient_zip,
    )

    body_html = _format_body_paragraphs(body)

    # Logo rendering — small block at top-right. We use width:1in to
    # leave the address window area clear. If logo is missing, the
    # space stays empty (no broken-image icon).
    logo_html = (
        f'<img src="{logo_uri}" alt="" style="width:1in;height:1in;'
        f'display:block;" />'
        if logo_uri else ""
    )

    # Signature rendering — show the image if we have one, otherwise
    # show the typed name in italic at the signature line.
    if signature_uri:
        signature_html = (
            f'<img src="{signature_uri}" alt="" '
            f'style="height:0.5in;display:block;margin-bottom:0.05in;" />'
            f'<div>{escape(agent_full_name)}</div>'
        )
    else:
        signature_html = (
            f'<div style="font-style:italic;font-size:14pt;'
            f'margin-bottom:0.05in;">{escape(agent_full_name)}</div>'
            f'<div>{escape(agent_full_name)}</div>'
        )

    # The HTML is intentionally a single document with inline CSS.
    # Page sized 8.5x11 with 0.5" margins. Address block positioned
    # to land in the lower-left envelope window after tri-fold.
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: 8.5in 11in;
    margin: 0;
  }}
  html, body {{
    margin: 0;
    padding: 0;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 11pt;
    color: #1a1a1a;
    line-height: 1.45;
  }}
  .page {{
    width: 8.5in;
    height: 11in;
    padding: 0.5in;
    box-sizing: border-box;
    position: relative;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.25in;
  }}
  .recipient-block {{
    /* Positioned to align with Lob's standard #10 double-window
       envelope. The recipient window on a tri-folded letter sits
       roughly 3.5"-4.5" from the top of the unfolded page, 0.5"-4.5"
       from the left. Lob is forgiving within ~0.25" tolerance. */
    position: absolute;
    top: 3.625in;
    left: 0.875in;
    width: 4in;
    font-size: 11pt;
    line-height: 1.3;
  }}
  .body {{
    margin-top: 5.25in;  /* push body below the address window area */
  }}
  .body p {{
    margin: 0 0 0.12in 0;
    text-align: left;
  }}
  .signature-block {{
    margin-top: 0.25in;
  }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div></div>
    {logo_html}
  </div>

  <div class="recipient-block">
    {recipient_block}
  </div>

  <div class="body">
    {body_html}
    <div class="signature-block">
      {signature_html}
    </div>
  </div>
</div>
</body>
</html>"""
