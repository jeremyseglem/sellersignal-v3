import { useState } from 'react';
import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { sendMagicLink, supabaseConfigured } from '../lib/supabase.js';

// SignupPage — magic-link 'request access' flow. Same underlying
// Supabase signInWithOtp call as LoginPage; the difference is purely
// presentational. This page frames the action as 'requesting beta
// access' rather than 'signing in,' which matches the marketing
// copy and the invite-only positioning.
//
// Once magic link auth completes, a row in agent_profiles_v3 is
// auto-created by the database trigger (see schema/010_agent_profiles.sql).
// The user lands on /territories — empty until an admin assigns them
// a ZIP. Future iteration adds an invite-code requirement; for beta
// we hand-pick agents and let anyone with an email through.
export default function SignupPage() {
  const redirectTo = `${window.location.origin}/territories`;

  const [email, setEmail]       = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent]         = useState(false);
  const [error, setError]       = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await sendMagicLink(email, { redirectTo });
      setSent(true);
    } catch (err) {
      setError(err.message || 'Could not send confirmation link.');
    } finally {
      setSubmitting(false);
    }
  };

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
          Beta is invite-only with one agent per ZIP. Enter your email
          and we&rsquo;ll send you a confirmation link.
        </p>

        {!supabaseConfigured && (
          <div style={warnStyle}>
            Authentication isn&rsquo;t configured in this environment.
            Contact the SellerSignal team at{' '}
            <a href="mailto:hello@sellersignal.co" style={{ color: 'inherit' }}>
              hello@sellersignal.co
            </a>.
          </div>
        )}

        {sent ? (
          <div style={confirmStyle}>
            <div style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              marginBottom: 8,
              fontFamily: 'var(--font-sans)',
            }}>
              Check your email
            </div>
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 14,
              color: 'var(--text)',
              lineHeight: 1.6,
            }}>
              We sent a confirmation link to <strong>{email}</strong>.
              Click it to finish creating your account.
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@brokerage.com"
              autoFocus
              disabled={submitting || !supabaseConfigured}
              style={inputStyle}
            />
            {error && (
              <div style={errorStyle}>{error}</div>
            )}
            <button
              type="submit"
              disabled={submitting || !email || !supabaseConfigured}
              style={primaryButtonStyle(submitting || !email || !supabaseConfigured)}
            >
              {submitting ? 'Sending…' : 'Send confirmation link'}
            </button>
          </form>
        )}

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


// Same styles as LoginPage. Could be hoisted into a shared file
// later but duplication is fine while the auth flow is still
// settling.
const labelStyle = {
  display: 'block',
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'var(--text-tertiary)',
  marginBottom: 6,
  fontFamily: 'var(--font-sans)',
};

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  fontSize: 15,
  fontFamily: 'var(--font-serif)',
  color: 'var(--text)',
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  boxSizing: 'border-box',
  outline: 'none',
};

function primaryButtonStyle(disabled) {
  return {
    width: '100%',
    marginTop: 'var(--space-lg)',
    padding: '14px 20px',
    fontSize: 14,
    fontWeight: 600,
    fontFamily: 'var(--font-sans)',
    color: 'var(--text-inverse)',
    background: disabled ? 'var(--text-tertiary)' : 'var(--accent)',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    cursor: disabled ? 'not-allowed' : 'pointer',
  };
}

const errorStyle = {
  marginTop: 12,
  padding: '10px 14px',
  background: 'var(--call-now-bg)',
  color: 'var(--call-now)',
  borderRadius: 'var(--radius-sm)',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
};

const warnStyle = {
  marginBottom: 'var(--space-lg)',
  padding: '12px 14px',
  background: 'var(--accent-dim)',
  color: 'var(--accent)',
  borderRadius: 'var(--radius-sm)',
  fontSize: 13,
  fontFamily: 'var(--font-serif)',
};

const confirmStyle = {
  padding: 'var(--space-lg)',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
};
