import SiteLayout from '../components/shell/SiteLayout.jsx';

// ProfilePage — placeholder for Session 1. Session 2 (auth) creates
// the underlying profile table; Session 4 (Lob) consumes the data
// from this form for letter automation.
//
// Form will collect: full name, phone, brokerage, license number,
// headshot upload, signature image upload. Pre-populated from
// Supabase auth.users metadata when available.
export default function ProfilePage({ agent = null, onSignOut = null }) {
  return (
    <SiteLayout
      agent={agent}
      onSignOut={onSignOut}
      mode="authenticated"
      contentMaxWidth={680}
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
          Account
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 36,
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
        }}>
          Your profile
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          fontStyle: 'italic',
          marginTop: 'var(--space-xs)',
        }}>
          Identity used in automated letters and outreach.
        </p>
      </header>

      <div style={{
        padding: 'var(--space-lg)',
        border: '1px dashed var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-card)',
        fontSize: 14,
        fontStyle: 'italic',
        color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-serif)',
        lineHeight: 1.6,
      }}>
        Profile form wires in next session — full name, phone, brokerage,
        license number, headshot, signature. These details flow into the
        letter automation when an agent clicks &ldquo;Send a handwritten
        letter&rdquo; from a CALL NOW lead.
      </div>
    </SiteLayout>
  );
}
