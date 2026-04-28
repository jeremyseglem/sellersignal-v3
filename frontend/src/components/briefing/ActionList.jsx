import LeadRow from './LeadRow.jsx';

/**
 * ActionList — the action-first deck at the top of the briefing.
 *
 * Renders the top N (default 5) leads from playbook.call_now. The
 * spec calls these "the people to contact this week" — they're the
 * highest-priority leads and they get the most prominent treatment.
 *
 * If there are zero call_now leads, this renders nothing. The
 * BriefingHeader's actionCount handles the "no active leads"
 * messaging — there's no point in showing an empty action list.
 *
 * Props:
 *   leads         — array of lead objects from playbook.call_now
 *   selectedPin   — currently-open dossier's pin (highlights the row)
 *   onPickLead    — handler called with (pin) when a row is clicked
 *   max           — soft cap on rendered rows; defaults to 5
 */
export default function ActionList({ leads, selectedPin, onPickLead, max = 5 }) {
  if (!leads || leads.length === 0) return null;

  const shown = leads.slice(0, max);

  return (
    <section
      aria-label="Sellers to contact this week"
      style={{
        padding: 'var(--space-md) var(--space-lg) var(--space-lg)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {shown.map((lead, i) => (
          <LeadRow
            key={lead.pin}
            lead={lead}
            index={i + 1}
            selected={lead.pin === selectedPin}
            accent="var(--call-now)"
            onClick={() => onPickLead(lead.pin)}
          />
        ))}
      </ul>
    </section>
  );
}
