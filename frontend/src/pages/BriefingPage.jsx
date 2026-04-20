import { useEffect, useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  briefings,
  map as mapApi,
  parcels as parcelsApi,
  coverage as coverageApi,
} from '../api/client.js';
import MapPanel from '../components/MapPanel.jsx';
import PlaybookList from '../components/PlaybookList.jsx';
import ParcelDossier from '../components/ParcelDossier.jsx';

function formatValue(v) {
  if (!v) return '—';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}

function formatRelative(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 60)        return `${mins}m ago`;
  if (mins < 60 * 24)   return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 60 / 24)}d ago`;
}

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

export default function BriefingPage() {
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

  // Apply search + filter + sort to each section
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

  if (error) {
    return (
      <div style={{ padding: 'var(--space-xl)', maxWidth: 720, margin: '0 auto' }}>
        <Link to="/coverage" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: 13 }}>
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
      height: '100vh',
      overflow: 'hidden',
    }}>
      {/* ── Left panel ── */}
      <aside style={{
        background: 'var(--bg-card)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <header style={{
          padding: 'var(--space-lg)',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <Link to="/coverage" style={{
            color: 'var(--text-tertiary)',
            textDecoration: 'none',
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}>
            ← Territories
          </Link>
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 26,
            fontWeight: 600,
            color: 'var(--text)',
            marginTop: 'var(--space-xs)',
            lineHeight: 1.15,
          }}>
            ZIP {zip}{stats?.city ? ` · ${stats.city}, ${stats.state}` : ''}
          </h1>
          {briefing && (
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--text-secondary)',
              fontSize: 13,
              marginTop: 4,
            }}>
              Week of {briefing.week_of}
              {stats?.last_refresh && (
                <>
                  {' · '}
                  <span style={{ fontStyle: 'normal', color: 'var(--text-tertiary)', fontSize: 11 }}>
                    refreshed {formatRelative(stats.last_refresh)}
                  </span>
                </>
              )}
            </div>
          )}
          {stats && <StatsRow stats={stats} />}
        </header>

        {/* Search + filter + sort */}
        {briefing && (
          <div style={{
            padding: 'var(--space-md) var(--space-lg)',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg)',
            flexShrink: 0,
          }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by address, owner, or PIN"
              style={{
                width: '100%',
                padding: '7px 10px',
                fontSize: 13,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-card)',
                color: 'var(--text)',
                fontFamily: 'var(--font-sans)',
                boxSizing: 'border-box',
              }}
            />
            <div style={{
              display: 'flex',
              gap: 6,
              marginTop: 'var(--space-sm)',
              flexWrap: 'wrap',
            }}>
              {FILTER_OPTIONS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilterKey(f.key)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: '0.03em',
                    borderRadius: 999,
                    border: `1px solid ${filterKey === f.key ? 'var(--accent)' : 'var(--border)'}`,
                    background: filterKey === f.key ? 'var(--accent)' : 'transparent',
                    color: filterKey === f.key ? 'var(--bg-card)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value)}
              style={{
                marginTop: 'var(--space-sm)',
                width: '100%',
                padding: '6px 8px',
                fontSize: 12,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-card)',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-md)' }}>
          {!briefing && <p style={{ color: 'var(--text-tertiary)' }}>Loading playbook…</p>}
          {briefing && filteredPlaybook && (
            <PlaybookList
              playbook={filteredPlaybook}
              selectedPin={selectedPin}
              onPickLead={handlePickLead}
            />
          )}
        </div>
      </aside>

      {/* ── Right: map + dossier ── */}
      <main style={{ position: 'relative', background: 'var(--bg)' }}>
        {!mapData && (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-tertiary)',
          }}>
            Loading territory map…
          </div>
        )}
        {mapData && (
          <MapPanel
            mapData={mapData}
            selectedPin={selectedPin}
            onPickPin={handlePickLead}
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

function StatsRow({ stats }) {
  const items = [
    { label: 'Parcels',    value: stats.parcel_count?.toLocaleString?.() || stats.parcel_count || '—' },
    { label: 'Median',     value: formatValue(stats.median_value) },
    { label: 'Scored',     value: stats.investigated_count ?? '—' },
    { label: 'Call now',   value: stats.call_now_count ?? '—' },
    { label: 'Build now',  value: stats.build_now_count ?? '—' },
  ];
  return (
    <div style={{
      marginTop: 'var(--space-md)',
      display: 'grid',
      gridTemplateColumns: 'repeat(5, 1fr)',
      gap: 4,
      paddingTop: 'var(--space-sm)',
      borderTop: '1px solid var(--border)',
    }}>
      {items.map((it) => (
        <div key={it.label}>
          <div style={{
            fontSize: 9,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            {it.label}
          </div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--text)',
            marginTop: 2,
          }}>
            {it.value}
          </div>
        </div>
      ))}
    </div>
  );
}
