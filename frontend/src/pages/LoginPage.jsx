import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { sendMagicLink, supabaseConfigured } from '../lib/supabase.js';

// LoginPage — magic-link sign-in. Email-only form. After submit,
// the page renders a 'Check your email' confirmation state until
// the user clicks the link in the email and lands back at /territories
// (or wherever ?next= said to go).
//
// Same form serves both sign-in and sign-up — Supabase's
// signInWithOtp creates the user on first use, so '/login' and
// '/signup' are functionally identical magic-link flows. The split
// into two pages exists for marketing-funnel reasons (two CTAs on
// the homepage) more than auth reasons.
export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next') || '/territories';
  const redirectTo = `${window.location.origin}${next}`;

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
      setError(err.message || 'Could not send sign-in link.');
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
          Sign in
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          lineHeight: 1.6,
          marginBottom: 'var(--space-xl)',
        }}>
          Enter your email and we&rsquo;ll send you a link. No password
          to remember.
        </p>

        {!supabaseConfigured && (
          <div style={warnStyle}>
            Authentication isn&rsquo;t configured in this environment.
            Contact the SellerSignal team for access.
          </div>
        )}

        {sent ? (
          <ConfirmState email={email} />
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
              {submitting ? 'Sending…' : 'Send sign-in link'}
            </button>
          </form>
        )}

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


function ConfirmState({ email }) {
  return (
    <div style={{
      padding: 'var(--space-lg)',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
    }}>
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
        We sent a sign-in link to <strong>{email}</strong>. Click the
        link in the email to finish signing in. The link expires in
        one hour.
      </div>
    </div>
  );
}


// ── Form styles ──────────────────────────────────────────────────
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
  transition: 'border-color 0.15s ease',
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
    transition: 'background 0.15s ease',
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
