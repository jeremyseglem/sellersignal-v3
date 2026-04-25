import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { coverage } from '../api/client.js';
import SiteLayout from '../components/shell/SiteLayout.jsx';

// TerritoriesPage — the agent's home after sign-in. Lists live ZIPs
// they have access to. For Session 1 this still calls the public
// coverage.list() API and shows every live ZIP; Session 2 adds auth
// gating so each agent sees only their assigned territory.
//
// Currently routed at both `/territories` (new) and `/coverage`
// (legacy alias kept temporarily so existing bookmarks don't 404).
// The redirect from `/coverage` is wired in App.jsx.
//
// Future-state: this page becomes a King County map with claimed
// (greyed) / available (gold) ZIPs as polygons. For now it's a
// minimal list — same data, new shell.
export default function TerritoriesPage({ agent = null, onSignOut = null }) {
  const [zips, setZips]   = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    coverage.list()
      .then((data) => setZips(data.coverage || []))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <SiteLayout
      agent={agent}
      onSignOut={onSignOut}
      mode="authenticated"
      showFooter={false}
      contentMaxWidth={960}
    >
      <header style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: 11,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--text-tertiary)',
          fontWeight: 600,
          marginBottom: 6,
          fontFamily: 'var(--font-sans)',
        }}>
          Your territories
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 36,
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
        }}>
          Live briefings
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          fontStyle: 'italic',
          marginTop: 'var(--space-xs)',
        }}>
          Choose a ZIP to open this week&rsquo;s playbook and map.
        </p>
      </header>

      {error && (
        <div style={{
          padding: 'var(--space-md)',
          background: 'var(--call-now-bg)',
          color: 'var(--call-now)',
          borderRadius: 'var(--radius-md)',
          marginBottom: 'var(--space-md)',
        }}>
          Error loading territories: {error}
        </div>
      )}

      {zips === null && !error && (
        <p style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
      )}

      {zips && zips.length === 0 && (
        <p style={{
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
        }}>
          No territories are live yet.
        </p>
      )}

      {zips && zips.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {zips.map((z) => (
            <li key={z.zip_code} style={{
              padding: 'var(--space-lg)',
              marginBottom: 'var(--space-sm)',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
            }}>
              <Link
                to={`/zip/${z.zip_code}`}
                style={{
                  textDecoration: 'none',
                  color: 'inherit',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 'var(--space-md)',
                }}
              >
                <div>
                  <div style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 22,
                    fontWeight: 600,
                    color: 'var(--text)',
                  }}>
                    {z.city}, {z.state} · {z.zip_code}
                  </div>
                  <div style={{
                    fontSize: 13,
                    color: 'var(--text-tertiary)',
                    marginTop: 6,
                    fontFamily: 'var(--font-sans)',
                  }}>
                    {z.parcel_count?.toLocaleString() || 0} parcels ·
                    {' '}{z.investigated_count?.toLocaleString() || 0} investigated ·
                    {' '}{z.current_call_now_count || 0} on this week&rsquo;s CALL NOW
                  </div>
                </div>
                <div style={{
                  color: 'var(--accent)',
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: 'var(--font-sans)',
                  whiteSpace: 'nowrap',
                }}>
                  Open briefing →
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SiteLayout>
  );
}
