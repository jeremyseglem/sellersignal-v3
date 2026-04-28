import { useEffect, useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  briefings,
  map as mapApi,
  parcels as parcelsApi,
  coverage as coverageApi,
} from '../api/client.js';
import MapPanel from '../components/MapPanel.jsx';
import ParcelDossier from '../components/ParcelDossier.jsx';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import BriefingHeader from '../components/briefing/BriefingHeader.jsx';
import ActionList from '../components/briefing/ActionList.jsx';
import PipelineList from '../components/briefing/PipelineList.jsx';
import MapExplorePanel from '../components/briefing/MapExplorePanel.jsx';

const FILTER_OPTIONS = [
  { key: 'all',        label: 'All',        matches: () => true },
  { key: 'call_now',   label: 'Call now',   matches: (lead) => lead.recommended_action?.category === 'call_now' },
  { key: 'build_now',  label: 'Build now',  matches: (lead) => lead.recommended_action?.category === 'build_now' },
  { key: 'hold',       label: 'Holds',      matches: (lead) => !lead.recommended_action?.category || lead.recommended_action?.category === 'hold' },
];

const SORT_OPTIONS = [
  { key: 'default',    label: 'Default order' },
  { key: 'value_desc', label: 'Value: high → low' },
  { key: 'value_asc',  label: 'Value: low → high' },
  { key: 'tenure_desc',label: 'Tenure: long → short' },
  { key: 'tenure_asc', label: 'Tenure: short → long' },
];

function sortLeads(leads, sortKey) {
  if (sortKey === 'default') return leads;
  const copy = [...leads];
  const byValue = (dir) => (a, b) => dir * ((a.value || 0) - (b.value || 0));
  const byTenure = (dir) => (a, b) => dir * ((a.tenure_years || 0) - (b.tenure_years || 0));
  const cmp =
      sortKey === 'value_desc'  ? byValue(-1)
    : sortKey === 'value_asc'   ? byValue(1)
    : sortKey === 'tenure_desc' ? byTenure(-1)
    : sortKey === 'tenure_asc'  ? byTenure(1)
    : null;
  if (cmp) copy.sort(cmp);
  return copy;
}

function searchLeads(leads, query) {
  if (!query || !query.trim()) return leads;
  const q = query.trim().toLowerCase();
  return leads.filter((L) => (
    (L.address && L.address.toLowerCase().includes(q)) ||
    (L.owner_name && L.owner_name.toLowerCase().includes(q)) ||
    (L.pin && L.pin.includes(q))
  ));
}

export default function BriefingPage(props) {
  return (
    <SiteLayout
      agent={props.agent || null}
      onSignOut={props.onSignOut || null}
      mode="authenticated"
      showFooter={false}
    >
      <BriefingBody />
    </SiteLayout>
  );
}

function BriefingBody() {
  const { zip } = useParams();
  const [briefing, setBriefing] = useState(null);
  const [mapData, setMapData]   = useState(null);
  const [stats, setStats]       = useState(null);
  const [selectedPin, setSelectedPin] = useState(null);
  const [dossier, setDossier]   = useState(null);
  const [error, setError]       = useState(null);

  // UI state for left panel controls
  const [searchQuery, setSearchQuery] = useState('');
  const [filterKey, setFilterKey]     = useState('all');
  const [sortKey, setSortKey]         = useState('default');

  // Load briefing + map + stats on ZIP change
  useEffect(() => {
    setBriefing(null); setMapData(null); setStats(null);
    setSelectedPin(null); setDossier(null); setError(null);

    Promise.all([briefings.get(zip, false), mapApi.get(zip)])
      .then(([b, m]) => { setBriefing(b); setMapData(m); })
      .catch((e) => setError(e.detail?.message || e.message));

    // Stats are nice-to-have; don't block the rest on them
    coverageApi.stats(zip).then(setStats).catch(() => setStats(null));
  }, [zip]);

  // Load dossier when a pin is selected
  useEffect(() => {
    if (!selectedPin) { setDossier(null); return; }
    parcelsApi.get(selectedPin)
      .then(setDossier)
      .catch((e) => console.error('Failed to load dossier:', e));
  }, [selectedPin]);

  const handlePickLead = (pin) => setSelectedPin(pin);

  // Apply search + filter + sort to each section. Filtered output
  // feeds the map (so pin highlights match what the agent searches),
  // not the briefing left panel — the action list is intentionally
  // unfiltered so search doesn't accidentally hide a Call Now.
  const filteredPlaybook = useMemo(() => {
    if (!briefing?.playbook) return null;
    const activeFilter = FILTER_OPTIONS.find((o) => o.key === filterKey) || FILTER_OPTIONS[0];
    const processSection = (leads) => {
      if (!leads) return [];
      const searched = searchLeads(leads, searchQuery);
      const filtered = searched.filter(activeFilter.matches);
      return sortLeads(filtered, sortKey);
    };
    return {
      call_now:        processSection(briefing.playbook.call_now),
      build_now:       processSection(briefing.playbook.build_now),
      strategic_holds: processSection(briefing.playbook.strategic_holds),
    };
  }, [briefing, searchQuery, filterKey, sortKey]);

  // ── Derived values for the new briefing components ──
  // Action list shows up to 5 Call Now leads, unfiltered. Pipeline
  // shows the Build Now + Strategic Holds merge — also unfiltered,
  // because filtering belongs to exploration mode (the map controls).
  const actionLeads = briefing?.playbook?.call_now || [];
  const pipelineLeads = {
    buildNow: briefing?.playbook?.build_now || [],
    holds:    briefing?.playbook?.strategic_holds || [],
  };

  // Header counts use the briefing's own stats (computed from the
  // just-built playbook, so they always agree with the lists below).
  // Coverage stats are a fallback for parcel count when briefing.stats
  // doesn't carry it.
  const actionCount   = Math.min(actionLeads.length, 5);
  const pipelineCount =
      (briefing?.stats?.build_now_count ?? pipelineLeads.buildNow.length)
    + (briefing?.stats?.strategic_holds_count ?? pipelineLeads.holds.length);
  const parcelCount   =
      briefing?.stats?.total_parcels
   ?? stats?.parcel_count
   ?? mapData?.parcels?.length
   ?? 0;

  if (error) {
    return (
      <div style={{ padding: 'var(--space-xl)', maxWidth: 720, margin: '0 auto' }}>
        <Link to="/territories" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: 13 }}>
          ← Back to territories
        </Link>
        <h2 style={{ marginTop: 'var(--space-md)', fontFamily: 'var(--font-display)' }}>
          {zip} isn&rsquo;t available
        </h2>
        <p style={{ color: 'var(--text-secondary)', marginTop: 'var(--space-sm)' }}>
          {String(error)}
        </p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '420px 1fr',
      height: 'calc(100vh - 56px)',
      overflow: 'hidden',
    }}>
      {/* ── Left panel: action-first briefing ── */}
      <aside style={{
        background: 'var(--bg-card)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <BriefingHeader
          zip={zip}
          actionCount={actionCount}
          pipelineCount={pipelineCount}
          parcelCount={parcelCount}
          city={stats?.city}
          state={stats?.state}
          weekOf={briefing?.week_of}
        />

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!briefing && (
            <p style={{
              padding: 'var(--space-lg)',
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
            }}>
              Loading briefing…
            </p>
          )}

          {briefing && actionLeads.length === 0 && (
            <div style={{
              padding: 'var(--space-lg)',
              fontFamily: 'var(--font-serif)',
              color: 'var(--text-secondary)',
            }}>
              <p style={{
                fontFamily: 'var(--font-display)',
                fontSize: 16,
                fontWeight: 600,
                color: 'var(--text)',
                marginBottom: 6,
              }}>
                No active leads this week
              </p>
              <p style={{ fontSize: 13, fontStyle: 'italic', lineHeight: 1.5 }}>
                The briefing refreshes weekly. Or explore the territory on
                the map — the pipeline is still building.
              </p>
            </div>
          )}

          {briefing && (
            <>
              <ActionList
                leads={actionLeads}
                selectedPin={selectedPin}
                onPickLead={handlePickLead}
              />
              <PipelineList
                buildNowLeads={pipelineLeads.buildNow}
                holdLeads={pipelineLeads.holds}
                selectedPin={selectedPin}
                onPickLead={handlePickLead}
              />
            </>
          )}
        </div>
      </aside>

      {/* ── Right: map + exploration controls + dossier ── */}
      <main style={{ position: 'relative', background: 'var(--bg)' }}>
        {!mapData && (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
          }}>
            Loading territory map…
          </div>
        )}
        {mapData && (
          <MapPanel
            mapData={mapData}
            playbook={filteredPlaybook || briefing?.playbook}
            selectedPin={selectedPin}
            onPickPin={handlePickLead}
          />
        )}

        {/* Exploration controls overlaid on the map. Hidden until
            the briefing has loaded so the controls don't appear
            against an empty map. */}
        {briefing && (
          <MapExplorePanel
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            filterKey={filterKey}
            onFilterChange={setFilterKey}
            sortKey={sortKey}
            onSortChange={setSortKey}
            filterOptions={FILTER_OPTIONS}
            sortOptions={SORT_OPTIONS}
          />
        )}

        {selectedPin && dossier && (
          <ParcelDossier
            dossier={dossier}
            onClose={() => setSelectedPin(null)}
          />
        )}
      </main>
    </div>
  );
}
