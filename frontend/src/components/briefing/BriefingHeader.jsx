import { Link } from 'react-router-dom';

/**
 * BriefingHeader — top of the briefing-page left panel.
 *
 * Layout: back-link → ZIP+city headline → oracle line (pipeline +
 * territory parcel count) → week-of marker.
 *
 * The Contact Now count used to live in this header as a big
 * dynamic number ("5 sellers to contact this week"). With the
 * bucket redesign, the BucketTabs below this header carry the
 * per-bucket counts and the active bucket selection — a single
 * headline number would either be stale (sum of all buckets, never
 * what the agent is looking at) or would churn on every tab click.
 * The territory name does more durable work as the headline.
 *
 * Props:
 *   zip               — ZIP code string ("98004")
 *   buildNowCount     — count of leads in active pipeline (Build Now tier).
 *                       Excludes Strategic Holds — those are watch-list,
 *                       a different mental category, and live only in the
 *                       Pipeline section header below.
 *   parcelCount       — total parcels tracked in this ZIP
 *   city, state       — location strings, render in the headline
 *   weekOf            — date string for the briefing's week-of marker
 */
export default function BriefingHeader({
  zip,
  buildNowCount,
  parcelCount,
  city,
  state,
  weekOf,
}) {
  // The oracle line — surfaces "we're watching the whole ZIP" without
  // overclaiming. Numbers are real, territory-specific, no inference.
  const pipelineText = buildNowCount > 0
    ? `${buildNowCount.toLocaleString()} more in pipeline`
    : null;
  const parcelText = parcelCount > 0
    ? `${parcelCount.toLocaleString()} homes tracked in your territory`
    : null;
  const oracleParts = [pipelineText, parcelText].filter(Boolean);

  // Headline assembles the territory name. Falls back to ZIP-only if
  // city/state didn't load yet.
  const headlineText = city
    ? `${city}, ${state || 'WA'}`
    : `ZIP ${zip}`;

  return (
    <header style={{
      padding: 'var(--space-lg) var(--space-lg) var(--space-md)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {/* Quiet back-link to the territories grid. */}
      <Link to="/territories" style={{
        color: 'var(--text-tertiary)',
        textDecoration: 'none',
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}>
        ← Territories
      </Link>

      {/* Headline: territory name + ZIP. Largest typographic element. */}
      <h1 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 28,
        fontWeight: 600,
        color: 'var(--text)',
        marginTop: 'var(--space-sm)',
        lineHeight: 1.15,
        letterSpacing: '-0.005em',
      }}>
        {headlineText}
        <span style={{
          color: 'var(--text-tertiary)',
          fontWeight: 500,
          fontSize: 18,
          marginLeft: 10,
          letterSpacing: '0.02em',
        }}>
          {zip}
        </span>
      </h1>

      {/* Oracle line — italic serif, soft color. The "homes tracked"
          count is the differentiator from competitors who give static
          lists. */}
      {oracleParts.length > 0 && (
        <div style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 13,
          color: 'var(--text-secondary)',
          marginTop: 6,
          lineHeight: 1.5,
        }}>
          {oracleParts.join(' · ')}
        </div>
      )}

      {/* Week-of marker, quiet treatment. */}
      {weekOf && (
        <div style={{
          fontSize: 11,
          fontStyle: 'italic',
          color: 'var(--text-tertiary)',
          marginTop: 'var(--space-md)',
          fontFamily: 'var(--font-serif)',
        }}>
          week of {weekOf}
        </div>
      )}
    </header>
  );
}
