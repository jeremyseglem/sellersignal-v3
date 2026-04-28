import { Link } from 'react-router-dom';

/**
 * BriefingHeader — top of the briefing-page left panel.
 *
 * Replaces the prior structure (← Territories link → ZIP title → "Week of"
 * → 5-cell stat row). The new shape leads with the action and surfaces
 * the oracle metric below it, then drops the location into a quiet
 * eyebrow underneath. Meets the spec's 8-second test: a cold visitor
 * sees the action they need to take before any context.
 *
 * The number in the headline pulls from action list count, not a fixed
 * "5". When the agent has fewer leads (smaller ZIP, mid-week refresh),
 * the headline reads accurately ("3 sellers to contact this week" / etc).
 *
 * Props:
 *   zip               — ZIP code string ("98004")
 *   actionCount       — count of leads in the action list (typically 5)
 *   buildNowCount     — count of leads in active pipeline (Build Now tier).
 *                       Excludes Strategic Holds — those are watch-list,
 *                       a different mental category, and live only in the
 *                       Pipeline section header below the action list.
 *   parcelCount       — total parcels tracked in this ZIP
 *   city, state       — location strings, render below the headline
 *   weekOf            — date string for the briefing's week-of marker
 */
export default function BriefingHeader({
  zip,
  actionCount,
  buildNowCount,
  parcelCount,
  city,
  state,
  weekOf,
}) {
  // Phrasing matches the count exactly: "1 seller" not "1 sellers"
  const sellerWord = actionCount === 1 ? 'seller' : 'sellers';

  // The oracle line — surfaces "we're watching the whole ZIP" without
  // overclaiming. Numbers are real, territory-specific, no inference.
  //
  // Two pieces only: pipeline (active leads the agent is cultivating)
  // and territory parcels tracked. Strategic Holds (the watch list)
  // are excluded from the oracle on purpose — they sit in the
  // Pipeline section header below where the agent has full context,
  // and including them in the oracle would force the cold visitor to
  // parse three numbers in one line.
  //
  // "in pipeline" replaces the earlier "more building" because
  // "building" is internal jargon — a cold visitor reading "100 more
  // building" might think we mean construction. "Pipeline" is
  // universally understood by anyone in sales (including agents)
  // and reads as modest: it claims "lead being cultivated," not
  // "likely seller."
  const pipelineText = buildNowCount > 0
    ? `${buildNowCount.toLocaleString()} more in pipeline`
    : null;
  const parcelText = parcelCount > 0
    ? `${parcelCount.toLocaleString()} homes tracked in your territory`
    : null;
  const oracleParts = [pipelineText, parcelText].filter(Boolean);

  return (
    <header style={{
      padding: 'var(--space-lg) var(--space-lg) var(--space-md)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {/* Quiet back-link to the territories grid. Subtle so it doesn't
          compete with the headline; agents who want to switch ZIPs will
          find it. */}
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

      {/* The headline. Largest typographic element on the page.
          The number gets the call-now red so the eye lands on it
          first. Action verb second. ZIP context drops below. */}
      <h1 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 28,
        fontWeight: 600,
        color: 'var(--text)',
        marginTop: 'var(--space-sm)',
        lineHeight: 1.15,
        letterSpacing: '-0.005em',
      }}>
        <span style={{ color: 'var(--call-now)' }}>{actionCount}</span>{' '}
        {sellerWord} to contact this week
      </h1>

      {/* Oracle line — italic serif, soft color. Present but
          deferential to the headline. The "homes tracked" count is
          the differentiator from competitors who give static lists. */}
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

      {/* Location eyebrow. Below the headline rather than above it —
          it's context, not the lead. Same uppercase treatment as the
          back-link so they read as the same chrome layer. */}
      <div style={{
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginTop: 'var(--space-md)',
      }}>
        ZIP {zip}{city ? ` · ${city}, ${state}` : ''}
        {weekOf && (
          <span style={{
            marginLeft: 8,
            fontStyle: 'italic',
            textTransform: 'none',
            letterSpacing: 0,
            fontWeight: 400,
            fontFamily: 'var(--font-serif)',
            fontSize: 11,
            color: 'var(--text-tertiary)',
          }}>
            · week of {weekOf}
          </span>
        )}
      </div>
    </header>
  );
}
