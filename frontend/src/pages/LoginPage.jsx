import { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import {
  sendMagicLink,
  signInWithPassword,
} from '../lib/supabase.js';
import { useAuth } from '../lib/AuthContext.jsx';

// LoginPage — two sign-in modes on one page.
//
//   mode = 'password' (default): email + password form, calls
//     signInWithPassword and navigates to `next` on success.
//
//   mode = 'magic'              : email-only form, calls
//     sendMagicLink and shows a "Check your email" confirmation
//     state until the user clicks the link.
//
// Password is the default because corporate email scanners
// (Microsoft Defender Safe Links, Mimecast, Proofpoint, etc.)
// pre-fetch magic-link URLs and consume the one-time-use token
// before the user can click it. Magic-link remains available as a
// fallback for users who prefer it or who already had accounts
// created via magic-link before passwords were added.
//
// Existing magic-link-only accounts continue to work in both modes:
// they can sign in via magic-link as before, or click "Forgot
// password?" to set a password and use the password mode going
// forward. Nothing forces them to migrate.
export default function LoginPage() {
  const { isConfigured, loading: authLoading } = useAuth();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const next = searchParams.get('next') || '/territories';
  const redirectTo = `${window.location.origin}${next}`;

  const [mode, setMode] = useState('password');       // 'password' | 'magic'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await signInWithPassword(email, password);
      navigate(next);
    } catch (err) {
      setError(err.message || 'Could not sign in. Check your email and password.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleMagicSubmit = async (e) => {
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

  const switchToMagic = () => {
    setError(null);
    setMode('magic');
  };

  const switchToPassword = () => {
    setError(null);
    setSent(false);
    setMode('password');
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
          {mode === 'password'
            ? 'Enter your email and password to sign in.'
            : 'Enter your email and we\u2019ll send you a one-time sign-in link.'}
        </p>

        {!authLoading && !isConfigured && (
          <div style={warnStyle}>
            Authentication isn&rsquo;t configured in this environment.
            Contact the SellerSignal team for access.
          </div>
        )}

        {mode === 'password' && (
          <form onSubmit={handlePasswordSubmit}>
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
            <label style={{ ...labelStyle, marginTop: 'var(--space-md)' }}>
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
              disabled={submitting || !isConfigured}
              style={inputStyle}
            />
            {error && (
              <div style={errorStyle}>{error}</div>
            )}
            <button
              type="submit"
              disabled={submitting || !email || !password || !authLoading && !isConfigured}
              style={primaryButtonStyle(submitting || !email || !password || !authLoading && !isConfigured)}
            >
              {submitting ? 'Signing in\u2026' : 'Sign in'}
            </button>
            <div style={fallbackRowStyle}>
              <Link to="/forgot-password" style={subtleLinkStyle}>
                Forgot password?
              </Link>
              <button type="button" onClick={switchToMagic} style={textButtonStyle}>
                Email me a sign-in link instead
              </button>
            </div>
          </form>
        )}

        {mode === 'magic' && !sent && (
          <form onSubmit={handleMagicSubmit}>
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
              {submitting ? 'Sending\u2026' : 'Send sign-in link'}
            </button>
            <div style={fallbackRowStyle}>
              <button type="button" onClick={switchToPassword} style={textButtonStyle}>
                Use email and password instead
              </button>
            </div>
          </form>
        )}

        {mode === 'magic' && sent && (
          <ConfirmState email={email} onUsePassword={switchToPassword} />
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


function ConfirmState({ email, onUsePassword }) {
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
      <div style={{ marginTop: 'var(--space-md)' }}>
        <button type="button" onClick={onUsePassword} style={textButtonStyle}>
          Use email and password instead
        </button>
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

const fallbackRowStyle = {
  marginTop: 'var(--space-md)',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 'var(--space-sm)',
  flexWrap: 'wrap',
};

const subtleLinkStyle = {
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  color: 'var(--text-tertiary)',
  textDecoration: 'none',
  borderBottom: '1px dotted var(--text-tertiary)',
};

const textButtonStyle = {
  background: 'none',
  border: 'none',
  padding: 0,
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  color: 'var(--text-tertiary)',
  cursor: 'pointer',
  borderBottom: '1px dotted var(--text-tertiary)',
};
