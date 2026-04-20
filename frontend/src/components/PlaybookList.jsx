import { useState } from 'react';

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

  // Build the secondary-meta line: owner name + type + tenure
  const ownerBits = [];
  if (lead.owner_name) ownerBits.push(lead.owner_name);
  if (lead.owner_type && lead.owner_type !== 'unknown') {
    ownerBits.push(lead.owner_type.toUpperCase());
  }
  if (lead.tenure_years != null) {
    ownerBits.push(`${Math.round(lead.tenure_years)}yr`);
  }

  // Signal family label: replace underscores with spaces, keep lowercase
  const signalLabel = lead.signal_family
    ? lead.signal_family.replace(/_/g, ' ')
    : null;

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
