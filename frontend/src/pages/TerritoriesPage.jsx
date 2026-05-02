import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { territory } from '../api/client.js';
import { useAuth } from '../lib/AuthContext.jsx';
import SiteLayout from '../components/shell/SiteLayout.jsx';

/**
 * TerritoriesPage — the post-signin landing for both operators and
 * agents. Renders an annotated grid of every live ZIP, with semantics
 * that depend on the viewer's role:
 *
 *   OPERATOR (Jeremy / Brian) — sees all ZIPs as clickable. Each ZIP
 *     shows whether it's claimed by an agent and by whom. No claim UI;
 *     operators don't claim territory.
 *
 *   AGENT WITH CLAIM — sees their own ZIP highlighted as 'mine' and
 *     clickable; other ZIPs show 'claimed by [name]' or 'available'
 *     but are not clickable. Cannot claim a second.
 *
 *   AGENT WITHOUT CLAIM (fresh signup) — clicking an available ZIP
 *     opens a claim confirmation modal. Claimed-by-other ZIPs are
 *     visibly disabled.
 */
export default function TerritoriesPage() {
  const { profile, refreshProfile, signOut } = useAuth();
  const navigate = useNavigate();

  const [data, setData]       = useState(null);   // { role, my_zip, zips }
  const [error, setError]     = useState(null);
  const [claimModal, setClaimModal] = useState(null);
  const [claiming, setClaiming]     = useState(false);
  const [claimError, setClaimError] = useState(null);

  useEffect(() => {
    territory.status()
      .then(setData)
      .catch((e) => setError(e?.detail?.detail || e?.message || 'Failed to load territories'));
  }, []);

  async function confirmClaim() {
    if (!claimModal) return;
    setClaiming(true);
    setClaimError(null);
    try {
      await territory.claim(claimModal.zip_code);
      await refreshProfile();
      const fresh = await territory.status();
      setData(fresh);
      setClaimModal(null);
      navigate(`/zip/${claimModal.zip_code}`);
    } catch (e) {
      setClaimError(e?.detail?.detail || e?.message || 'Claim failed');
    } finally {
      setClaiming(false);
    }
  }

  return (
    <SiteLayout
      agent={profile}
      onSignOut={signOut}
      mode="authenticated"
      showFooter={false}
      contentMaxWidth={960}
    >
      <header style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--text-tertiary)', fontWeight: 600,
          marginBottom: 6, fontFamily: 'var(--font-sans)',
        }}>
          {data?.role === 'operator' ? 'Operator dashboard' : 'Your territory'}
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 600,
          letterSpacing: '-0.01em', color: 'var(--text)',
        }}>
          {data?.role === 'operator'
            ? 'All territories'
            : data?.my_zip
              ? 'Live briefings'
              : 'Choose your territory'}
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)', color: 'var(--text-secondary)',
          fontSize: 15, fontStyle: 'italic', marginTop: 'var(--space-xs)',
          lineHeight: 1.5,
        }}>
          <Subhead role={data?.role} myZip={data?.my_zip} />
        </p>
      </header>

      {error && (
        <div style={{
          padding: 'var(--space-md)',
          background: 'var(--call-now-bg)', color: 'var(--call-now)',
          borderRadius: 'var(--radius-md)', marginBottom: 'var(--space-md)',
        }}>
          {error}
        </div>
      )}

      {data === null && !error && (
        <p style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
      )}

      {data && data.zips.length === 0 && (
        <p style={{
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-serif)', fontStyle: 'italic',
        }}>
          No territories are live yet.
        </p>
      )}

      {data && data.zips.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {data.zips.map((z) => (
            <ZipCard
              key={z.zip_code}
              zip={z}
              role={data.role}
              myZip={data.my_zip}
              onClickAvailable={() => setClaimModal(z)}
            />
          ))}
        </ul>
      )}

      {claimModal && (
        <ClaimModal
          zip={claimModal}
          claiming={claiming}
          error={claimError}
          onConfirm={confirmClaim}
          onCancel={() => { setClaimModal(null); setClaimError(null); }}
        />
      )}
    </SiteLayout>
  );
}


// ──────────────────────────────────────────────────────────────────
// Subcomponents
// ──────────────────────────────────────────────────────────────────

function Subhead({ role, myZip }) {
  if (role === 'operator') {
    return (<>Watching all 11 ZIPs in real time. Click any to open the briefing.</>);
  }
  if (myZip) {
    return (<>Your territory is {myZip}. Click below to open this week&rsquo;s playbook.</>);
  }
  return (<>You have one territory. Pick the ZIP you want to work — it becomes yours exclusively.</>);
}


function ZipCard({ zip, role, myZip, onClickAvailable }) {
  const status = zip.status;
  const isMine = status === 'mine';
  const isClaimed = status === 'claimed_by_other';
  const isAvailable = status === 'available';

  // Operators: every ZIP is navigable. Agents: only their own — and
  // unclaimed agents can click an available card to open the claim
  // modal (handled via onClickAvailable, not Link).
  const navigable =
    role === 'operator' ||
    isMine ||
    (isAvailable && !myZip);

  const linkTarget = (role === 'operator' || isMine)
    ? `/zip/${zip.zip_code}`
    : null;

  const cardStyle = {
    padding: 'var(--space-lg)',
    marginBottom: 'var(--space-sm)',
    background: 'var(--bg-card)',
    border: isMine ? '2px solid var(--accent)' : '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    opacity: (!navigable && !isMine) ? 0.6 : 1,
  };

  const innerStyle = {
    textDecoration: 'none',
    color: 'inherit',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 'var(--space-md)',
    cursor: navigable ? 'pointer' : 'default',
  };

  const inner = (
    <>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 22,
            fontWeight: 600, color: 'var(--text)',
          }}>
            {zip.city}, {zip.state} · {zip.zip_code}
          </div>
          <StatusBadge status={status} role={role} claimedByName={zip.claimed_by_name} />
        </div>
        <div style={{
          fontSize: 13, color: 'var(--text-tertiary)',
          marginTop: 6, fontFamily: 'var(--font-sans)',
        }}>
          {(zip.parcel_count ?? 0).toLocaleString()} parcels ·
          {' '}{zip.current_call_now_count ?? 0} on this week&rsquo;s CALL NOW
        </div>
      </div>
      <div style={{
        color: navigable ? 'var(--accent)' : 'var(--text-tertiary)',
        fontSize: 13, fontWeight: 600,
        fontFamily: 'var(--font-sans)', whiteSpace: 'nowrap',
      }}>
        <CtaLabel
          isMine={isMine}
          isAvailable={isAvailable}
          isClaimed={isClaimed}
          role={role}
          myZip={myZip}
        />
      </div>
    </>
  );

  if (linkTarget) {
    return (
      <li style={cardStyle}>
        <Link to={linkTarget} style={innerStyle}>{inner}</Link>
      </li>
    );
  }
  if (navigable && onClickAvailable) {
    return (
      <li style={cardStyle}>
        <div
          style={innerStyle}
          onClick={onClickAvailable}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClickAvailable(); }}
        >
          {inner}
        </div>
      </li>
    );
  }
  return (
    <li style={cardStyle}>
      <div style={innerStyle}>{inner}</div>
    </li>
  );
}


function CtaLabel({ isMine, isAvailable, isClaimed, role, myZip }) {
  if (isMine) return 'Open briefing →';
  if (role === 'operator') return 'Open briefing →';
  if (isAvailable && !myZip) return 'Claim this ZIP →';
  if (isAvailable && myZip)  return 'Available';
  if (isClaimed) return 'Claimed';
  return null;
}


function StatusBadge({ status, role, claimedByName }) {
  let label, color, bg;
  if (status === 'mine') {
    label = 'YOURS'; color = 'var(--text-inverse, #fff)'; bg = 'var(--accent)';
  } else if (status === 'claimed_by_other') {
    label = role === 'operator'
      ? `CLAIMED · ${(claimedByName || 'agent').toUpperCase()}`
      : 'CLAIMED';
    color = 'var(--text-secondary)'; bg = 'transparent';
  } else if (status === 'available') {
    label = 'AVAILABLE';
    color = 'var(--accent)'; bg = 'transparent';
  } else {
    return null;
  }
  return (
    <span style={{
      fontSize: 10, letterSpacing: '0.1em', fontWeight: 700,
      padding: '3px 8px', borderRadius: 4,
      color, background: bg,
      border: bg === 'transparent' ? `1px solid ${color}` : 'none',
      fontFamily: 'var(--font-sans)',
    }}>
      {label}
    </span>
  );
}


function ClaimModal({ zip, claiming, error, onConfirm, onCancel }) {
  return (
    <div
      onClick={onCancel}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-xl)',
          maxWidth: 480, width: '90%',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--accent)', fontWeight: 700,
          marginBottom: 6, fontFamily: 'var(--font-sans)',
        }}>
          Claim territory
        </div>
        <h2 style={{
          fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 600,
          color: 'var(--text)', margin: 0, letterSpacing: '-0.005em',
          marginBottom: 'var(--space-md)',
        }}>
          {zip.city}, {zip.state} — {zip.zip_code}
        </h2>
        <p style={{
          fontFamily: 'var(--font-serif)', fontSize: 15,
          color: 'var(--text-secondary)', lineHeight: 1.6,
          marginBottom: 'var(--space-lg)',
        }}>
          You&rsquo;re about to claim <strong>{zip.zip_code}</strong> as your
          exclusive territory. You can only claim one ZIP, and once claimed it&rsquo;s
          locked in — contact us if you need to change it later.
        </p>

        {error && (
          <div style={{
            padding: '10px 12px', marginBottom: 'var(--space-md)',
            background: 'var(--call-now-bg)', color: 'var(--call-now)',
            borderRadius: 'var(--radius-sm)', fontSize: 13,
            fontFamily: 'var(--font-sans)',
          }}>
            {error}
          </div>
        )}

        <div style={{
          display: 'flex', gap: 'var(--space-sm)',
          justifyContent: 'flex-end',
        }}>
          <button
            onClick={onCancel}
            disabled={claiming}
            style={{
              padding: '10px 18px', fontSize: 14, fontWeight: 500,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-secondary)',
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              cursor: claiming ? 'not-allowed' : 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={claiming}
            style={{
              padding: '10px 22px', fontSize: 14, fontWeight: 600,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-inverse, #fff)',
              background: claiming ? 'var(--text-tertiary)' : 'var(--accent)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: claiming ? 'wait' : 'pointer',
            }}
          >
            {claiming ? 'Claiming…' : `Claim ${zip.zip_code}`}
          </button>
        </div>
      </div>
    </div>
  );
}
