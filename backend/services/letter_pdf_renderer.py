"""
backend/services/letter_pdf_renderer.py — HTML → PDF conversion for Stannp.

Stannp's /letters/create endpoint takes a PDF file and does the address
mail-merge themselves (overlays the recipient address onto a clear zone
near the top-left of the page). We render our existing letter HTML to
a PDF using xhtml2pdf (pure-Python, built on reportlab) and post the
bytes to Stannp.

History: this module previously used WeasyPrint, which produces
better-fidelity output but requires Cairo/Pango/GLib system libraries
at import time. On Railway/Nixpacks the apt-installed libs sit at
/usr/lib/x86_64-linux-gnu/ while the Nix-managed Python looks for
shared objects in /nix/store/, so WeasyPrint's ctypes loader couldn't
find them despite a correct apt list. Rather than fight Nixpacks lib
paths we switched to xhtml2pdf, which has no native deps.

xhtml2pdf CSS support is more limited than WeasyPrint's — no flexbox,
no CSS grid, weaker SVG handling. Our letter_renderer outputs simple
inline-styled HTML with positioned text + raster/SVG images and falls
within xhtml2pdf's supported subset.

Stannp page constraints (from https://stannp.com/us/design-specs):
  - US Letter (8.5" x 11")
  - Top-left address clear zone for the windowed envelope. We must NOT
    place content there — Stannp's mail-merge overlay puts the recipient
    address in that area at print time. The renderer's existing top
    margin (which positions the body well below the address area)
    keeps content out of that zone for us.
"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def render_html_to_pdf(html: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using xhtml2pdf.

    Args:
        html: A complete HTML document (must include <html>, <body>).
              Should NOT contain the recipient address — Stannp adds it.
              Typically the output of letter_renderer.render_letter_html
              called with no_recipient_block=True.

    Returns:
        PDF file as bytes, ready to upload to Stannp's letters/create
        endpoint.

    Raises:
        RuntimeError: if xhtml2pdf reports a render error.

    Note: layout (page size, margins, Stannp clear-zone padding) is owned
    by letter_renderer.py's inline CSS rather than this module — earlier
    versions injected an additional @page stylesheet here which competed
    with the renderer's .page padding and pushed content onto a second
    sheet. Single source of truth in the renderer is simpler.

    xhtml2pdf is imported lazily to keep app startup cheap and to surface
    any install issues only when sending — so a missing dep doesn't break
    health checks or other endpoints.
    """
    try:
        from xhtml2pdf import pisa
    except ImportError as e:
        raise RuntimeError(
            "xhtml2pdf failed to import. Confirm 'xhtml2pdf' is in "
            f"requirements.txt and the deploy succeeded. Original error: {e}"
        ) from e

    buf = BytesIO()
    try:
        status = pisa.CreatePDF(
            src=html,
            dest=buf,
            encoding="utf-8",
        )
    except Exception as e:
        raise RuntimeError(f"xhtml2pdf CreatePDF raised: {type(e).__name__}: {e}") from e

    if status.err:
        raise RuntimeError(
            f"xhtml2pdf reported {status.err} render error(s). Check HTML "
            f"input for unsupported CSS or malformed structure."
        )

    pdf_bytes = buf.getvalue()
    if not pdf_bytes:
        raise RuntimeError("xhtml2pdf produced an empty PDF — check input HTML")

    logger.info("Rendered letter PDF (xhtml2pdf): %d bytes", len(pdf_bytes))
    return pdf_bytes


def render_html_to_pdf_safe(html: str) -> tuple[bytes | None, str | None]:
    """
    Wrapper that returns (pdf_bytes, error_message) instead of raising.
    Useful in API handlers where we want to return a structured error
    response rather than a 500.
    """
    try:
        return render_html_to_pdf(html), None
    except Exception as e:
        logger.exception("PDF render failed")
        return None, str(e)
