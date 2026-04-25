import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';

// SignupPage — placeholder for Session 1. Session 2 will replace the
// body with a real Supabase magic-link signup form (email + name +
// brokerage). Beta-phase signup goes through invite codes; the form
// will gate on those before creating a profile.
export default function SignupPage() {
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
          Request access
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          lineHeight: 1.6,
          marginBottom: 'var(--space-xl)',
        }}>
          SellerSignal is currently invite-only, with one agent per ZIP.
          We&rsquo;ll reach out once a territory in your market is available.
        </p>
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
          Magic-link signup wires in next session. For now, contact us at{' '}
          <a href="mailto:hello@sellersignal.co" style={{ color: 'var(--accent)' }}>
            hello@sellersignal.co
          </a>.
        </div>
        <div style={{
          marginTop: 'var(--space-xl)',
          fontSize: 13,
          color: 'var(--text-tertiary)',
        }}>
          Already have an account? <Link to="/login" style={{
            color: 'var(--accent)',
            textDecoration: 'none',
            borderBottom: '1px dotted var(--accent)',
          }}>Sign in</Link>.
        </div>
      </div>
    </SiteLayout>
  );
}
