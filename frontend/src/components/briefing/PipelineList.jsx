import LeadRow from './LeadRow.jsx';

/**
 * PipelineList — the longer-horizon pipeline below the action list.
 *
 * Per the v4 spec, Build Now and Strategic Holds are merged into a
 * single "60 More Likely Sellers" section labeled "Working pipeline."
 * The provisional merge reflects that the underlying band-2 data
 * doesn't currently support a sharp differentiation between the two,
 * and that the spec's overclaim discipline rules out implying a
 * distinction we can't back up.
 *
 * Future re-split candidates (timeline-based, signal-density-based)
 * are noted in the spec but not implemented here. When the time
 * comes to re-split, this component will be replaced — not edited
 * in place to add complexity.
 *
 * Renders nothing if there are no pipeline leads.
 *
 * Props:
 *   buildNowLeads, holdLeads — playbook arrays from briefings API
 *   selectedPin              — currently-open dossier's pin
 *   onPickLead               — handler called with (pin) on click
 */
export default function PipelineList({
  buildNowLeads,
  holdLeads,
  selectedPin,
  onPickLead,
}) {
  // Merge the two arrays. Build Now first (ranked by selector for
  // diversity + strength), then Holds (long-cycle leftovers). Dedupe
  // by pin in case anything overlaps.
  const seen = new Set();
  const merged = [];
  for (const lead of [...(buildNowLeads || []), ...(holdLeads || [])]) {
    if (!lead?.pin || seen.has(lead.pin)) continue;
    seen.add(lead.pin);
    merged.push(lead);
  }

  if (merged.length === 0) return null;

  return (
    <section
      aria-label="More likely sellers in the pipeline"
      style={{ padding: 'var(--space-md) var(--space-lg) var(--space-xl)' }}
    >
      <div style={{
        fontFamily: 'var(--font-sans)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--text)',
      }}>
        {merged.length} more likely {merged.length === 1 ? 'seller' : 'sellers'}
      </div>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontStyle: 'italic',
        fontSize: 12,
        color: 'var(--text-tertiary)',
        marginTop: 4,
        marginBottom: 'var(--space-sm)',
      }}>
        Working pipeline
      </div>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {merged.map((lead) => (
          <LeadRow
            key={lead.pin}
            lead={lead}
            index={null}
            selected={lead.pin === selectedPin}
            accent="var(--build-now)"
            onClick={() => onPickLead(lead.pin)}
          />
        ))}
      </ul>
    </section>
  );
}
