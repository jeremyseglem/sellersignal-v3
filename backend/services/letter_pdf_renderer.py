"""
backend/services/letter_pdf_renderer.py — HTML → PDF conversion for Stannp.

Stannp's /letters/create endpoint takes a PDF file and does the address
mail-merge themselves (overlays the recipient address onto a clear zone
near the top-left of the page). We render our existing letter HTML to
a PDF using WeasyPrint, which handles inline CSS reliably and produces
print-quality output.

Why WeasyPrint over alternatives:
  - reportlab (already installed): great for drawing from scratch, but
    can't render arbitrary HTML+CSS. Would require rewriting the entire
    letter_renderer module.
  - xhtml2pdf (pure Python): handles basic HTML but struggles with our
    positioned signature block + inline SVG logo.
  - WeasyPrint: handles modern CSS2.1 + most CSS3 cleanly, produces
    print-grade PDFs. System deps (Cairo + Pango) installed via
    nixpacks.toml.

Stannp page constraints (from https://stannp.com/us/design-specs):
  - US Letter (8.5" x 11")
  - Top-left address clear zone for the windowed envelope. We must NOT
    place content there — Stannp's mail-merge overlay puts the recipient
    address in that area at print time.
  - Bottom OMR/IMB clear zone for tracking barcode.

The HTML passed in should already exclude the recipient address block
(letter_renderer.render_letter_html with no_recipient_block=True).
"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


# Page CSS injected into every render. WeasyPrint's @page rule controls
# physical page size and margins. US Letter with margins that leave the
# Stannp clear zones empty.
#
# Stannp's design spec for US-LETTER (standard window envelope):
#   - Address clear zone: roughly top-left, starts ~1" from top, ~0.75"
#     from left, 4" wide x 1" tall.
#   - We use a 1.25" top margin and 0.75" left/right margins to keep
#     content out of that zone. Body content starts well below the
#     address position.
#   - Bottom margin 0.75" to clear the OMR barcode area.
_PAGE_CSS = """
@page {
    size: 8.5in 11in;
    margin: 1.25in 0.75in 0.75in 0.75in;
}
@page :first {
    /* On the first page, push content down further so it never
       collides with the Stannp address overlay zone. */
    margin-top: 2.25in;
}
"""


def render_html_to_pdf(html: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using WeasyPrint.

    Args:
        html: A complete HTML document (must include <html>, <body>).
              Should NOT contain the recipient address — Stannp adds it.
              Typically the output of letter_renderer.render_letter_html
              called with no_recipient_block=True.

    Returns:
        PDF file as bytes, ready to upload to Stannp's letters/create
        endpoint.

    Raises:
        RuntimeError: if WeasyPrint isn't importable (missing system libs).
        Exception: re-raises WeasyPrint render errors with context.

    WeasyPrint is imported lazily so that app startup doesn't fail if
    the system Cairo/Pango libs are temporarily missing — we only need
    PDF rendering when MAIL_PROVIDER=stannp and an agent actually sends.
    """
    try:
        from weasyprint import HTML, CSS
    except ImportError as e:
        raise RuntimeError(
            "WeasyPrint failed to import — Cairo/Pango system libs may "
            "be missing. Check nixpacks.toml in the repo root. "
            f"Original error: {e}"
        ) from e
    except OSError as e:
        # WeasyPrint raises OSError when its native dependencies can't
        # be loaded at import time. This typically means the Railway
        # build didn't install the apt packages in nixpacks.toml.
        raise RuntimeError(
            "WeasyPrint native libraries failed to load. Verify the "
            "Nixpacks build installed libpango, libcairo2, "
            "libgdk-pixbuf-2.0-0, and libharfbuzz0b. "
            f"Original error: {e}"
        ) from e

    page_css = CSS(string=_PAGE_CSS)
    doc = HTML(string=html)
    buf = BytesIO()
    doc.write_pdf(buf, stylesheets=[page_css])
    pdf_bytes = buf.getvalue()

    if not pdf_bytes:
        raise RuntimeError("WeasyPrint produced an empty PDF — check input HTML")

    logger.info("Rendered letter PDF: %d bytes", len(pdf_bytes))
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
