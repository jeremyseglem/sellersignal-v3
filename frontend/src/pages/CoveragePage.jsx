import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { coverage } from '../api/client.js';

export default function CoveragePage() {
  const [zips, setZips] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    coverage.list()
      .then((data) => setZips(data.coverage || []))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div style={{
      maxWidth: 960,
      margin: '0 auto',
      padding: 'var(--space-xl) var(--space-lg)',
    }}>
      <header style={{ marginBottom: 'var(--space-xl)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 42,
          fontWeight: 600,
          letterSpacing: '-0.02em',
          color: 'var(--text)',
        }}>
          SellerSignal
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 16,
          fontStyle: 'italic',
          marginTop: 'var(--space-xs)',
        }}>
          Territory intelligence for luxury real estate.
        </p>
      </header>

      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 22,
        fontWeight: 600,
        color: 'var(--text)',
        marginBottom: 'var(--space-md)',
      }}>
        Live territories
      </h2>

      {error && (
        <div style={{
          padding: 'var(--space-md)',
          background: 'var(--call-now-bg)',
          color: 'var(--call-now)',
          borderRadius: 'var(--radius-md)',
          marginBottom: 'var(--space-md)',
        }}>
          Error loading coverage: {error}
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
          No territories are live yet. The first territory will appear here
          once its build lifecycle completes.
        </p>
      )}

      {zips && zips.length > 0 && (
        <ul style={{ listStyle: 'none' }}>
          {zips.map((z) => (
            <li key={z.zip_code} style={{
              padding: 'var(--space-lg)',
              marginBottom: 'var(--space-sm)',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              transition: 'background var(--transition), border-color var(--transition)',
            }}>
              <Link
                to={`/zip/${z.zip_code}`}
                style={{
                  textDecoration: 'none',
                  color: 'inherit',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 20,
                    fontWeight: 600,
                    color: 'var(--text)',
                  }}>
                    {z.city}, {z.state} · {z.zip_code}
                  </div>
                  <div style={{
                    fontSize: 13,
                    color: 'var(--text-tertiary)',
                    marginTop: 'var(--space-xs)',
                  }}>
                    {z.parcel_count?.toLocaleString() || 0} parcels ·
                    {' '}{z.investigated_count?.toLocaleString() || 0} investigated ·
                    {' '}{z.current_call_now_count || 0} on this week&rsquo;s CALL NOW
                  </div>
                </div>
                <div style={{
                  color: 'var(--accent)',
                  fontSize: 13,
                  fontWeight: 500,
                }}>
                  View briefing →
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
