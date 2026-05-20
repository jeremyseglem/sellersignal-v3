import { useState } from 'react';
import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { sendPasswordReset } from '../lib/supabase.js';
import { useAuth } from '../lib/AuthContext.jsx';

// ForgotPasswordPage — request a password-reset email. Supabase
// sends an email containing a link to /reset-password with a
// recovery token in the URL fragment. Lacking a session at that
// route, the user types a new password and we call updateUser to
// set it.
//
// Note: the reset email contains a clickable link, which means
// corporate email scanners (Microsoft Defender Safe Links etc.) can
// pre-fetch and consume the token before the user clicks. Password
// reset is infrequent enough that we accept this risk for now; if it
// becomes a problem we can add OTP-code-based reset later.
//
// For the eight existing magic-link-only beta agents: they don't
// need to use this page unless they want to switch to password
// auth. Their magic-link login still works on /login. Resetting
// just sets a password on top of their existing account.
export default function ForgotPasswordPage() {
  const { isConfigured, loading: authLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await sendPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err.message || 'Could not send reset email.');
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
          Reset password
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          lineHeight: 1.6,
          marginBottom: 'var(--space-xl)',
        }}>
          Enter your email and we&rsquo;ll send you a link to set a
          new password.
        </p>

        {!authLoading && !isConfigured && (
          <div style={warnStyle}>
            Authentication isn&rsquo;t configured in this environment.
            Contact the SellerSignal team for access.
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
              If an account exists for <strong>{email}</strong>, we
              sent a reset link. Click the link to set a new password.
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
              disabled={submitting || !isConfigured}
              style={inputStyle}
            />
            {error && (
              <div style={errorStyle}>{error}</div>
            )}
            <button
              type="submit"
              disabled={submitting || !email || !authLoading && !isConfigured}
              style={primaryButtonStyle(submitting || !email || !authLoading && !isConfigured)}
            >
              {submitting ? 'Sending\u2026' : 'Send reset link'}
            </button>
          </form>
        )}

        <div style={{
          marginTop: 'var(--space-xl)',
          fontSize: 13,
          color: 'var(--text-tertiary)',
        }}>
          Remembered it? <Link to="/login" style={{
            color: 'var(--accent)',
            textDecoration: 'none',
            borderBottom: '1px dotted var(--accent)',
          }}>Back to sign in</Link>.
        </div>
      </div>
    </SiteLayout>
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
