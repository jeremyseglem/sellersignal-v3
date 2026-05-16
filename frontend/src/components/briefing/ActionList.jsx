import { useState } from 'react';
import LeadRow from './LeadRow.jsx';

/**
 * ActionList — the action-first deck at the top of the briefing.
 *
 * Renders all Call Now leads in two visual tiers:
 *   - Top 5: prominent treatment (numbered, full-weight name, larger font)
 *   - Rows 6+: muted treatment, hidden behind a "Show N more →" toggle
 *
 * The 5-row split honors the spec's headline framing — "5 SELLERS TO
 * CONTACT THIS WEEK" is the curated focal point, and the typography
 * makes those 5 read as the priority. But the rest of the call_now
 * list isn't hidden: agents who want to scan deeper find them via
 * the expand toggle. No data is dropped on the floor.
 *
 * Rationale: the prior version sliced the array at 5 and discarded
 * the rest. In ZIPs with many actionable leads (98004 has 26
 * after the contact_status fix), that meant 21 leads disappeared
 * from the UI entirely — they weren't in the action list, the
 * pipeline, or the map highlights. This version surfaces them all
 * without diluting the "5" frame.
 *
 * If there are zero call_now leads, this renders nothing. The
 * BriefingHeader's actionCount handles the "no active leads"
 * messaging — there's no point in showing an empty action list.
 *
 * Props:
 *   leads         — array of lead objects from playbook.call_now
 *   selectedPin   — currently-open dossier's pin (highlights the row)
 *   onPickLead    — handler called with (pin) when a row is clicked
 *   topN          — count of leads to show in the prominent tier;
 *                   defaults to 5 (matches the spec headline)
 */
export default function ActionList({ leads, selectedPin, onPickLead, topN = 5 }) {
  const [expanded, setExpanded] = useState(false);

  if (!leads || leads.length === 0) return null;

  const top = leads.slice(0, topN);
  const overflow = leads.slice(topN);

  // If a lead in the overflow is currently selected, auto-expand so
  // the agent can see why the row they clicked is highlighted. They
  // probably got there via the map.
  const overflowSelected = overflow.some((L) => L.pin === selectedPin);
  const showOverflow = expanded || overflowSelected;

  return (
    <section
      aria-label="Sellers to contact this week"
      style={{
        padding: 'var(--space-md) var(--space-lg) var(--space-lg)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {top.map((lead, i) => (
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

      {overflow.length > 0 && (
        <>
          {showOverflow && (
            <ul style={{
              listStyle: 'none',
              padding: 0,
              margin: '8px 0 0',
              borderTop: '0.5px dashed var(--border)',
              paddingTop: 8,
            }}>
              {overflow.map((lead) => (
                <LeadRow
                  key={lead.pin}
                  lead={lead}
                  index={null}
                  selected={lead.pin === selectedPin}
                  accent="var(--call-now)"
                  muted
                  onClick={() => onPickLead(lead.pin)}
                />
              ))}
            </ul>
          )}

          <button
            onClick={() => setExpanded((v) => !v)}
            style={{
              marginTop: 10,
              padding: '6px 0',
              fontFamily: 'var(--font-sans)',
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--accent)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              letterSpacing: '0.02em',
            }}
            aria-expanded={showOverflow}
          >
            {showOverflow
              ? `Show fewer ↑`
              : `Show ${overflow.length} more ${overflow.length === 1 ? 'lead' : 'leads'} →`}
          </button>
        </>
      )}
    </section>
  );
}
