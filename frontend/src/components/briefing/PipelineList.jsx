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

  // Display the underlying counts from the unmerged arrays so the
  // header matches what the agent sees referenced from the oracle
  // line above. Dedupe doesn't change these much in practice
  // (Build Now and Holds are mostly disjoint), but we render the
  // raw counts because that's what the agent's mental model expects.
  const buildCount = (buildNowLeads || []).length;
  const holdCount  = (holdLeads || []).length;

  // Header parts. Both are conditional — a small ZIP could have only
  // pipeline or only watch-list leads. Render whichever exists.
  const headerParts = [];
  if (buildCount > 0) {
    headerParts.push(`${buildCount.toLocaleString()} IN PIPELINE`);
  }
  if (holdCount > 0) {
    headerParts.push(`${holdCount.toLocaleString()} ON WATCH LIST`);
  }

  return (
    <section
      aria-label="Pipeline and watch list"
      style={{ padding: 'var(--space-md) var(--space-lg) var(--space-xl)' }}
    >
      {/* Header: shows both counts without overclaim. The prior
          version read "N more likely sellers / Working pipeline" —
          which was both jargon-y ("Working pipeline" repeats itself
          since "pipeline" already implies working) and overclaim-y
          ("more likely sellers" projects intent onto leads that are
          structural, not event-driven). The honest split is to name
          each tier directly. */}
      <div style={{
        fontFamily: 'var(--font-sans)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--text)',
        marginBottom: 'var(--space-sm)',
      }}>
        {headerParts.join(' · ')}
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
