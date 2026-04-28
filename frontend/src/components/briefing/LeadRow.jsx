import { useState } from 'react';

/**
 * LeadRow — one clickable lead in the action list or pipeline.
 *
 * The shape is the same in both contexts so the agent never has to
 * learn a new pattern. Differences between the two are visual weight
 * (action list rows are slightly more prominent) and which dataset
 * each list pulls from.
 *
 * Spec rules followed:
 *   - Name is the dominant element (Playfair Display, 16-17px)
 *   - Signal hint subtitle is plain English with perishability framing
 *     ("Probate filed 6 weeks ago", not "probate · Mar 2026")
 *   - One line per lead, max ~5-6 words on the hint
 *   - Open arrow on the right is a clear affordance
 *   - Hover state is decisive — this is meant to be clicked
 *
 * The signal-hint string is computed by buildSignalHint() — kept
 * in this file rather than a shared util so the rules stay close
 * to the rendering and we don't accidentally drift between contexts.
 *
 * Props:
 *   lead       — playbook lead object (owner_name, address, harvester_matches,
 *                signal_family, tenure_years, owner_type)
 *   index      — 1-based row number for the list. Pass null/undefined to hide.
 *   selected   — boolean, true when this lead's dossier is currently open
 *   accent     — CSS color string for the selected-state left border
 *   onClick    — handler invoked with no args; parent already knows the pin
 */
export default function LeadRow({ lead, index, selected, accent, onClick }) {
  const [hovered, setHovered] = useState(false);

  const name = lead.owner_name || lead.address || 'Unknown owner';
  const hint = buildSignalHint(lead);

  return (
    <li
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        listStyle: 'none',
        padding: '12px 14px 12px 16px',
        margin: '2px 0',
        cursor: 'pointer',
        borderRadius: 'var(--radius-md)',
        borderLeft: `3px solid ${selected ? (accent || 'var(--accent)') : 'transparent'}`,
        background: selected || hovered ? 'var(--bg-card-hover)' : 'transparent',
        transition: 'all var(--transition)',
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: 'var(--space-sm)',
      }}>
        <div style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
        }}>
          {index != null && (
            <span style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 12,
              color: 'var(--text-tertiary)',
              fontWeight: 500,
              minWidth: 18,
              flexShrink: 0,
            }}>
              {index}.
            </span>
          )}
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 16,
            fontWeight: 500,
            color: 'var(--text)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            letterSpacing: '-0.005em',
          }}>
            {name}
          </span>
        </div>
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 11,
          fontWeight: 500,
          color: hovered || selected ? 'var(--accent-hover)' : 'var(--accent)',
          letterSpacing: '0.04em',
          flexShrink: 0,
        }}>
          Open →
        </span>
      </div>
      {hint && (
        <div style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 13,
          color: 'var(--text-secondary)',
          marginTop: 3,
          marginLeft: index != null ? 28 : 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {hint}
        </div>
      )}
    </li>
  );
}

// ── Signal hint computation ─────────────────────────────────────
//
// The one-line subtitle under each name. Spec rules:
//   - "Probate filed 6 weeks ago" — not "probate · Mar 2026"
//   - Plain English, max ~5-6 words
//   - Use perishability framing when there's a recent trigger event
//   - Use tenure as the hook for ongoing-state leads
//
// Priority order: harvester match (with date) > investor profile
// (with tenure) > silent_transition tenure > out-of-area > generic
// signal family.

const SIGNAL_LABELS = {
  probate:         'Probate filed',
  divorce:         'Divorce filed',
  obituary:        'Obituary',
  tax_foreclosure: 'Tax foreclosure',
};

function buildSignalHint(lead) {
  const matches = lead.harvester_matches || [];

  // Strongest signal: a harvester match with a date. Frame as
  // "Probate filed N weeks ago" / "Divorce filed N months ago".
  if (matches.length > 0) {
    // Sort by matched_at desc, take the most recent
    const dated = matches
      .filter((m) => m.matched_at && m.signal_type)
      .sort((a, b) => (b.matched_at || '').localeCompare(a.matched_at || ''));
    if (dated.length > 0) {
      const m = dated[0];
      const label = SIGNAL_LABELS[m.signal_type] || _humanize(m.signal_type);
      const elapsed = _elapsed(m.matched_at);
      return elapsed ? `${label} ${elapsed}` : label;
    }
    // Has matches but no dates — fall back to the type alone
    const m = matches[0];
    return SIGNAL_LABELS[m.signal_type] || _humanize(m.signal_type);
  }

  // Investor-held: tenure hook
  if (lead.owner_type === 'llc' || lead.owner_type === 'investor') {
    if (lead.tenure_years != null) {
      return `Investor-held · ${Math.round(lead.tenure_years)} yrs`;
    }
    return 'Investor-held';
  }

  // Trust-held: tenure hook
  if (lead.owner_type === 'trust') {
    if (lead.tenure_years != null) {
      return `Trust-held · ${Math.round(lead.tenure_years)} yrs`;
    }
    return 'Trust-held';
  }

  // Out-of-area absentee
  if (lead.is_out_of_state) {
    return lead.owner_state
      ? `Out-of-area · mails to ${lead.owner_state}`
      : 'Out-of-area owner';
  }
  if (lead.is_absentee) {
    return 'Absentee owner';
  }

  // Long tenure (no event, no off-area marker) — surface tenure
  if (lead.tenure_years != null && lead.tenure_years >= 15) {
    return `Long-tenure owner · ${Math.round(lead.tenure_years)} yrs`;
  }

  // Last-resort: structural signal family in plain English
  if (lead.signal_family) {
    return _humanize(lead.signal_family);
  }

  return null;
}

// Replace underscores, lowercase. "estate_heirs" → "estate heirs"
function _humanize(s) {
  if (!s) return null;
  return s.replace(/_/g, ' ');
}

// Render a date as a perishability phrase: "6 weeks ago" / "3 months ago".
// Caps at "over a year ago" to avoid "73 weeks ago" oddities. Returns
// null if the date is unparseable.
function _elapsed(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  const ms = now.getTime() - d.getTime();
  if (ms < 0) return null; // future date — skip
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  if (days < 7) return days <= 1 ? 'this week' : `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 9) return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} months ago`;
  return 'over a year ago';
}
