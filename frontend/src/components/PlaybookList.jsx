import { useState } from 'react';
import { ownerTypeLabel } from '../lib/ownerType';

const SECTIONS = [
  { key: 'call_now',        label: 'CALL NOW',         color: 'var(--call-now)' },
  { key: 'build_now',       label: 'BUILD NOW',        color: 'var(--build-now)' },
  { key: 'strategic_holds', label: 'STRATEGIC HOLDS',  color: 'var(--hold)' },
];

function formatValue(v) {
  if (!v) return '—';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}

// Map backend signal_type strings to short, readable badge labels.
// Keep these short (<= 10 chars) so multiple badges fit on a lead card.
function signalTypeLabel(t) {
  const map = {
    probate:          'PROBATE',
    obituary:         'OBITUARY',
    divorce:          'DIVORCE',
    tax_foreclosure:  'TAX LIEN',
  };
  return map[t] || t.toUpperCase();
}

// Inline badge used on lead cards to surface active harvester signals.
// `prominent` swaps the rendering to a filled pill — used for the
// convergence badge where we want extra visual weight.
function SignalBadge({ label, color, prominent = false, title = null }) {
  const base = {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: '0.08em',
    padding: '2px 6px',
    borderRadius: 3,
    lineHeight: 1.3,
    whiteSpace: 'nowrap',
    fontFamily: 'var(--font-sans)',
  };
  if (prominent) {
    return (
      <span title={title || undefined} style={{
        ...base,
        background: color,
        color: 'white',
      }}>
        {label}
      </span>
    );
  }
  return (
    <span title={title || undefined} style={{
      ...base,
      background: 'transparent',
      color: color,
      border: `1px solid ${color}`,
    }}>
      {label}
    </span>
  );
}

export default function PlaybookList({ playbook, selectedPin, onPickLead }) {
  return (
    <div>
      {SECTIONS.map(({ key, label, color }) => {
        const leads = playbook[key] || [];
        if (leads.length === 0) return null;
        return (
          <section key={key} style={{ marginBottom: 'var(--space-lg)' }}>
            <SectionHeader label={label} count={leads.length} color={color} />
            <ul style={{ listStyle: 'none', marginTop: 'var(--space-sm)' }}>
              {leads.map((lead, i) => (
                <LeadRow
                  key={lead.pin || i}
                  lead={lead}
                  index={i + 1}
                  accent={color}
                  selected={selectedPin === lead.pin}
                  onClick={() => onPickLead(lead.pin)}
                />
              ))}
            </ul>
          </section>
        );
      })}

      {/* Empty state — no leads at all */}
      {SECTIONS.every(({ key }) => (playbook[key] || []).length === 0) && (
        <div style={{
          padding: 'var(--space-xl) var(--space-md)',
          textAlign: 'center',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 14,
        }}>
          No leads surfaced for this week.<br/>
          Run an investigation to populate the playbook.
        </div>
      )}
    </div>
  );
}

function SectionHeader({ label, count, color }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-sm)',
      padding: 'var(--space-sm) 0',
      borderBottom: `1px solid ${color}`,
    }}>
      <span style={{
        fontFamily: 'var(--font-sans)',
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.1em',
        color: color,
      }}>
        {label}
      </span>
      <span style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        marginLeft: 'auto',
      }}>
        {count}
      </span>
    </div>
  );
}

function LeadRow({ lead, index, accent, selected, onClick }) {
  const [hovered, setHovered] = useState(false);
  const action = lead.recommended_action;

  // Build the secondary-meta line: owner name + type + tenure + OOS
  const ownerBits = [];
  if (lead.owner_name) ownerBits.push(lead.owner_name);
  // Uses shared ownerTypeLabel from lib/ownerType so labels stay
  // consistent with the dossier. Returns null for 'unknown' so the
  // badge is hidden entirely for those rows.
  const ownerTypeText = ownerTypeLabel(lead.owner_type);
  if (ownerTypeText) {
    // PlaybookList rendered this in ALL CAPS historically (pre-sharing
    // the helper). Keep the uppercase presentation here for visual
    // consistency with the other uppercase meta markers on the card.
    ownerBits.push(ownerTypeText.toUpperCase());
  }
  if (lead.tenure_years != null) {
    ownerBits.push(`${Math.round(lead.tenure_years)}yr`);
  }
  // Absentee / Out-of-State marker. Prefer OOS when both apply —
  // it's the stronger signal (genuine out-of-state ownership,
  // typically high disposition intent). Include the mailing city
  // when available so the agent sees "CA" or "TX" not just "OOS".
  if (lead.is_out_of_state) {
    ownerBits.push(lead.owner_state
      ? `MAILS TO ${lead.owner_state}`
      : 'OUT OF STATE');
  } else if (lead.is_absentee) {
    ownerBits.push('ABSENTEE');
  }

  // Signal family label: replace underscores with spaces, keep lowercase
  const signalLabel = lead.signal_family
    ? lead.signal_family.replace(/_/g, ' ')
    : null;

  // Harvester match tags — one badge per distinct signal_type that fired.
  // These make the "why call_now" visible at a glance on the card, without
  // requiring the user to open the dossier.
  const harvesterMatches = lead.harvester_matches || [];
  const uniqueSignalTypes = Array.from(new Set(
    harvesterMatches.map((m) => m.signal_type).filter(Boolean)
  ));
  const hasConvergence = Boolean(lead.convergence);

  // Parcel-state tags — HIGH EQUITY, DEEP TENURE, LEGACY HOLD, MATURE LLC.
  // Descriptive situational markers derived from the parcel's own columns.
  // Lower visual priority than harvester badges (already sorted by rank
  // on the backend).
  const parcelStateTags = lead.parcel_state_tags || [];

  return (
    <li
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: 'var(--space-md)',
        cursor: 'pointer',
        borderLeft: `3px solid ${selected ? accent : 'transparent'}`,
        background: selected
          ? 'var(--bg-card-hover)'
          : hovered
            ? 'var(--bg-card-hover)'
            : 'transparent',
        transition: 'all var(--transition)',
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: 'var(--space-sm)',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 11,
            color: 'var(--text-tertiary)',
            fontWeight: 500,
          }}>
            {String(index).padStart(2, '0')}
          </div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 15,
            fontWeight: 600,
            color: 'var(--text)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {lead.address || 'Address unknown'}
          </div>
          {ownerBits.length > 0 && (
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              fontStyle: 'italic',
              marginTop: 2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {ownerBits.join(' · ')}
            </div>
          )}
          {signalLabel && (
            <div style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--text-tertiary)',
              marginTop: 6,
            }}>
              {signalLabel}
            </div>
          )}
          {/* One-line situation summary from the backend's resolve_copy.
              Same source the dossier's BUILD NOW card uses for WHY NOW —
              showing it on the card too lets the agent skim the deck
              and recognize lead types without clicking each one open.
              Renders only when present (always present for classified
              parcels). */}
          {lead.copy?.happening && (
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginTop: 4,
              lineHeight: 1.4,
            }}>
              {lead.copy.happening}
            </div>
          )}
          {/* Harvester signal tags — render one badge per distinct
              signal_type, plus a convergence badge if 2+ strict signals
              fired on the same pin. These make the lead's actionable
              signal visible without opening the dossier. */}
          {uniqueSignalTypes.length > 0 && (
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 4,
              marginTop: 6,
            }}>
              {hasConvergence && (
                <SignalBadge
                  label="CONVERGED"
                  color={accent}
                  prominent
                />
              )}
              {uniqueSignalTypes.map((t) => (
                <SignalBadge key={t} label={signalTypeLabel(t)} color={accent} />
              ))}
            </div>
          )}
          {/* Parcel-state tags (HIGH EQUITY, DEEP TENURE, LEGACY HOLD,
              MATURE LLC) — descriptive situational markers derived from
              parcel columns. Rendered in a muted color (text-tertiary)
              to de-emphasize relative to harvester signals. */}
          {parcelStateTags.length > 0 && (
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 4,
              marginTop: 6,
            }}>
              {parcelStateTags.map((t) => (
                <SignalBadge
                  key={t.kind}
                  label={t.label}
                  color="var(--text-tertiary)"
                  title={t.description}
                />
              ))}
            </div>
          )}
        </div>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: 14,
          fontWeight: 600,
          color: accent,
          whiteSpace: 'nowrap',
        }}>
          {formatValue(lead.value)}
        </div>
      </div>
      {action?.next_step && (
        <div style={{
          marginTop: 'var(--space-sm)',
          fontSize: 12,
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-serif)',
          lineHeight: 1.4,
        }}>
          → {action.next_step}
        </div>
      )}
    </li>
  );
}
