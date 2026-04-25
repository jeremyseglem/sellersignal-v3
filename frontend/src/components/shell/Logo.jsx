// SellerSignal logo component.
//
// Composition: a circular "signal" mark (3 ascending bars inside a thin
// circle, evoking sound-wave / chart) followed by the wordmark in DM
// Serif Display. The mark is rendered as inline SVG so it scales
// crisply at any size and inherits color via currentColor — letting
// the parent context (light shell, dark hero, footer, etc.) recolor
// it without touching the SVG.
//
// Two size presets:
//   default     — 28px mark + 18px wordmark, used in the site header
//   hero        — 40px mark + 26px wordmark, used in the marketing
//                 page hero and any large brand surface
//
// The component is purely presentational. It takes a tone prop
// (`light` | `dark`) so the parent can dictate the color treatment;
// `light` is for use on the dark navigation bar / hero (off-white
// strokes), `dark` is for use on the ivory canvas (deep brown).
// Defaults to `light` because the primary placement is the header.

export default function Logo({ size = 'default', tone = 'light', as = 'span' }) {
  const config = SIZES[size] || SIZES.default;
  const color = tone === 'dark' ? 'var(--text)' : 'var(--text-inverse)';

  const Wrapper = as;

  return (
    <Wrapper style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: config.gap,
      lineHeight: 1,
      color,
    }}>
      <SignalMark size={config.markSize} />
      <span style={{
        fontFamily: 'var(--font-wordmark)',
        fontSize: config.wordSize,
        letterSpacing: '0.005em',
        // DM Serif Display has a strong baseline; nudge slightly so
        // the wordmark optically aligns with the mark's center.
        marginTop: 1,
      }}>
        SellerSignal
      </span>
    </Wrapper>
  );
}


// ── Size presets ─────────────────────────────────────────────────
const SIZES = {
  default: { markSize: 28, wordSize: 18, gap: 10 },
  hero:    { markSize: 40, wordSize: 26, gap: 14 },
  small:   { markSize: 22, wordSize: 14, gap: 8 },
};


// ── The mark itself ──────────────────────────────────────────────
// Three ascending vertical bars inside a thin circle. The bars sit
// flush with the circle's bottom inner edge, padded inward so they
// don't touch the stroke. Drawn at a 28-unit viewBox so the proportions
// match the legacy CSS version (28px circle, ~2px stroke, three bars
// of heights 4 / 7 / 11 px from a 28px container).
function SignalMark({ size = 28 }) {
  // Stroke width scales with size so the ring stays visually consistent
  // across presets without becoming hairline at small sizes or chunky
  // at large.
  const strokeWidth = Math.max(1.4, size / 14);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ flexShrink: 0 }}
      aria-hidden="true"
    >
      {/* Outer ring */}
      <circle
        cx="14"
        cy="14"
        r={14 - strokeWidth / 2}
        stroke="currentColor"
        strokeWidth={strokeWidth}
        fill="none"
      />
      {/* Three ascending bars, baseline-aligned at y=20 (6px from
          bottom for inner padding). Heights: 4 / 7 / 11. Bar width
          2.5px to match the legacy CSS proportions. Gap 2px between
          bars. */}
      <rect
        x="9.5"   y="16"  width="2.5" height="4"
        rx="1"    fill="currentColor"
      />
      <rect
        x="13"    y="13"  width="2.5" height="7"
        rx="1"    fill="currentColor"
      />
      <rect
        x="16.5"  y="9"   width="2.5" height="11"
        rx="1"    fill="currentColor"
      />
    </svg>
  );
}
