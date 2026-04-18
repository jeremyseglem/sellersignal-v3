import { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { briefings, map as mapApi, parcels as parcelsApi } from '../api/client.js';
import MapPanel from '../components/MapPanel.jsx';
import PlaybookList from '../components/PlaybookList.jsx';
import ParcelDossier from '../components/ParcelDossier.jsx';

export default function BriefingPage() {
  const { zip } = useParams();
  const [briefing, setBriefing] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [selectedPin, setSelectedPin] = useState(null);
  const [dossier, setDossier] = useState(null);
  const [error, setError] = useState(null);

  // Load briefing + map data on ZIP change
  useEffect(() => {
    setBriefing(null); setMapData(null); setSelectedPin(null); setDossier(null);
    setError(null);

    Promise.all([briefings.get(zip, false), mapApi.get(zip)])
      .then(([b, m]) => { setBriefing(b); setMapData(m); })
      .catch((e) => setError(e.detail?.message || e.message));
  }, [zip]);

  // Load dossier when a pin is selected
  useEffect(() => {
    if (!selectedPin) { setDossier(null); return; }
    parcelsApi.get(selectedPin)
      .then(setDossier)
      .catch((e) => console.error('Failed to load dossier:', e));
  }, [selectedPin]);

  const handlePickLead = (pin) => {
    setSelectedPin(pin);
  };

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
      {/* ── Left panel: playbook + navigation ── */}
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
            fontSize: 28,
            fontWeight: 600,
            color: 'var(--text)',
            marginTop: 'var(--space-xs)',
          }}>
            ZIP {zip}
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
            </div>
          )}
        </header>

        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-md)' }}>
          {!briefing && <p style={{ color: 'var(--text-tertiary)' }}>Loading playbook…</p>}
          {briefing && (
            <PlaybookList
              playbook={briefing.playbook}
              selectedPin={selectedPin}
              onPickLead={handlePickLead}
            />
          )}
        </div>
      </aside>

      {/* ── Right: map fills, dossier overlays on pin click ── */}
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

        {/* Dossier overlay — slides in from right when a pin is selected */}
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
