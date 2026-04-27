/**
 * ThisWeekBlock — the action-first executive summary that lands at the
 * very top of the /zip/{zip} briefing page.
 *
 * Why this exists (Round 2B from the critic's feedback):
 *
 *   The briefing page used to be exploration-first: stat row + map +
 *   playbook decks. An agent landing on it had to interpret what to do.
 *
 *   This block reorders the hierarchy. It says, in plain language, who
 *   to call this week and why. The full decks still exist below for
 *   context, but the agent's first read is action-first.
 *
 * Behavior:
 *   - Shows the top N (default 5) Call Now leads
 *   - Each bullet is clickable → jumps to that lead's dossier
 *     (uses the same handlePickLead handler the playbook list uses,
 *     so map + dossier sync just like normal)
 *   - Renders nothing when there are no Call Now leads (graceful empty
 *     state — no point dominating the page with "call nobody")
 *
 * Visual:
 *   - Uses the call-now accent for the headline number
 *   - Bullets read like a list, not buttons (consistent with the
 *     critic's "feels like edge, not like SaaS tool" framing)
 *   - Hover state shows it's clickable without screaming "BUTTON"
 */

import { useState } from 'react';

const SIGNAL_LABELS = {
  probate:          'probate',
  divorce:          'divorce',
  obituary:         'obituary',
  tax_foreclosure:  'tax lien',
};

function formatSignalReason(lead) {
  // Prefer explicit harvester-match signal types (probate / divorce /
  // obituary / tax_foreclosure) — these are the strongest, clearest
  // hooks for the bullet line. Fall back to the structural signal
  // family if no harvester signal fired.
  const matches = lead.harvester_matches || [];
  const types = Array.from(new Set(
    matches.map((m) => m.signal_type).filter(Boolean)
  ));
  if (types.length > 0) {
    const first = types[0];
    return SIGNAL_LABELS[first] || first.replace(/_/g, ' ');
  }
  // Fall back to signal_family (silent_transition, dormant_absentee,
  // etc.) — read as a plain English phrase.
  if (lead.signal_family) {
    return lead.signal_family.replace(/_/g, ' ');
  }
  return null;
}

function leadDisplayName(lead) {
  // What we put on the bullet line. Owner name is the first choice.
  // Falls back to address when owner is unknown (rare — usually means
  // gov/nonprofit which doesn't reach Call Now anyway).
  return lead.owner_name || lead.address || 'Unknown owner';
}

function Bullet({ lead, onClick }) {
  const [hovered, setHovered] = useState(false);
  const reason = formatSignalReason(lead);
  return (
    <li
      role="button"
      tabIndex={0}
      onClick={() => onClick(lead.pin)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(lead.pin);
        }
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        listStyle: 'none',
        padding: '6px 8px',
        margin: '2px -8px',
        borderRadius: 'var(--radius-sm)',
        cursor: 'pointer',
        background: hovered ? 'var(--bg-card-hover)' : 'transparent',
        transition: 'background var(--transition)',
        display: 'flex',
        alignItems: 'baseline',
        gap: 8,
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        lineHeight: 1.4,
      }}
    >
      <span style={{
        color: 'var(--call-now)',
        fontFamily: 'var(--font-sans)',
        fontWeight: 700,
        flexShrink: 0,
      }}>
        •
      </span>
      <span style={{ color: 'var(--text)', flex: 1, minWidth: 0 }}>
        <span style={{
          fontWeight: 600,
          textDecoration: hovered ? 'underline' : 'none',
          textUnderlineOffset: 3,
        }}>
          {leadDisplayName(lead)}
        </span>
        {reason && (
          <>
            <span style={{ color: 'var(--text-tertiary)' }}> — </span>
            <span style={{
              color: 'var(--text-secondary)',
              fontStyle: 'italic',
            }}>
              {reason}
            </span>
          </>
        )}
      </span>
    </li>
  );
}

export default function ThisWeekBlock({ playbook, zip, onPickLead, max = 5 }) {
  const callNow = (playbook && playbook.call_now) || [];
  if (callNow.length === 0) return null;

  const shown = callNow.slice(0, max);
  const verb = shown.length === 1 ? 'this person' : `these ${shown.length} people`;

  return (
    <section
      aria-label={`Action priorities for ZIP ${zip}`}
      style={{
        padding: 'var(--space-lg)',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-card)',
      }}
    >
      {/* Headline — uppercase eyebrow + the action verb */}
      <div style={{
        fontFamily: 'var(--font-sans)',
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
      }}>
        This week in {zip}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 18,
        fontWeight: 600,
        color: 'var(--text)',
        marginTop: 4,
        marginBottom: 'var(--space-sm)',
        lineHeight: 1.2,
      }}>
        Call {verb}:
      </h2>

      <ul style={{ margin: 0, padding: 0 }}>
        {shown.map((lead) => (
          <Bullet key={lead.pin} lead={lead} onClick={onPickLead} />
        ))}
      </ul>

      {/* Closing line — reinforces the value prop on every page load.
          Subtle, italic, smaller — present but not shouting. */}
      <div style={{
        marginTop: 'var(--space-sm)',
        paddingTop: 'var(--space-sm)',
        borderTop: '1px dashed var(--border)',
        fontFamily: 'var(--font-serif)',
        fontStyle: 'italic',
        fontSize: 12,
        color: 'var(--text-tertiary)',
        lineHeight: 1.4,
      }}>
        → Highest-probability listing opportunities this week.
      </div>
    </section>
  );
}
