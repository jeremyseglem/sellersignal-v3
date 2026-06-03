# Letterhead assets

## Files

- `the-agency.svg` — source of truth for the agency mark. Edit this if the
  brand changes.
- `the-agency.png` — pre-rendered raster version, **committed**, loaded by
  `backend/services/letter_renderer.py` at runtime.

## Why a pre-rendered PNG

xhtml2pdf (our HTML → PDF engine on the letter pipeline) doesn't reliably
render SVG. Earlier in the Stannp migration we tried to embed the SVG via
data URI and it came out blank or garbled depending on the path complexity.

Rather than carry a heavy native dep on Railway (cairosvg pulls in libcairo
which has had issues with Nixpacks before — see the WeasyPrint chapter of
the build journal in `MANIFESTO.md`), we render the SVG to PNG **once** in
a dev container and commit the result. Runtime never touches the conversion.

## Re-rendering after a brand change

In a dev container with `cairosvg` installed:

```bash
pip install cairosvg

python3 -c "
import cairosvg
cairosvg.svg2png(
    url='data/letterheads/the-agency.svg',
    write_to='data/letterheads/the-agency.png',
    output_width=360,
    output_height=360,
)
"
```

The output is 360x360 (3× the SVG's 120-unit viewBox) so the logo prints
crisp at the ~60pt size used in the letter renderer. If you change the size
in `letter_renderer.py` to be much larger, re-render at a higher resolution
to keep the print quality.

Commit both files — the SVG so future edits start from the right source,
the PNG so production keeps working.
