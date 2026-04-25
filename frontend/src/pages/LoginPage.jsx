import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';

// LoginPage — placeholder for Session 1. Session 2 will replace the
// body with a real Supabase magic-link flow (email field, "send link"
// button, "check your email" confirmation state).
//
// The page intentionally renders inside SiteLayout so the header is
// already present and the visual language is locked from day one.
export default function LoginPage() {
  return (
    <SiteLayout mode="public" contentMaxWidth={440}>
      <div style={{ paddingTop: 'var(--space-2xl)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 36,
          fontWeight: 600,
          color: 'var(--text)',
          marginBottom: 'var(--space-md)',
          letterSpacing: '-0.01em',
        }}>
          Sign in
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          lineHeight: 1.6,
          marginBottom: 'var(--space-xl)',
        }}>
          Magic-link sign-in coming soon. Beta access is currently
          invitation-only.
        </p>
        <Placeholder note="Magic-link auth wires in next session." />
        <div style={{
          marginTop: 'var(--space-xl)',
          fontSize: 13,
          color: 'var(--text-tertiary)',
        }}>
          Don&rsquo;t have an account? <Link to="/signup" style={{
            color: 'var(--accent)',
            textDecoration: 'none',
            borderBottom: '1px dotted var(--accent)',
          }}>Request access</Link>.
        </div>
      </div>
    </SiteLayout>
  );
}

function Placeholder({ note }) {
  return (
    <div style={{
      padding: 'var(--space-md)',
      border: '1px dashed var(--border)',
      borderRadius: 'var(--radius-md)',
      background: 'var(--bg-card)',
      fontSize: 13,
      fontStyle: 'italic',
      color: 'var(--text-tertiary)',
      fontFamily: 'var(--font-serif)',
    }}>
      {note}
    </div>
  );
}
