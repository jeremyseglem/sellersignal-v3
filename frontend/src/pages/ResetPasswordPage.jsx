import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { useAuth } from '../lib/AuthContext.jsx';
import { updatePassword, supabaseConfigured } from '../lib/supabase.js';

// ResetPasswordPage — landing page from the password-reset email.
//
// Flow: user clicks the reset link in their email. Supabase routes
// them here with a recovery token in the URL fragment. The Supabase
// client (configured with detectSessionInUrl: true in supabase.js)
// automatically parses the fragment and establishes a session for
// the user. AuthContext's onAuthStateChange picks this up and sets
// session in context.
//
// The user is technically signed in at this point, but only for the
// purpose of changing their password. The form below collects a new
// password and calls updateUser to set it, then navigates them on.
//
// Three states to handle:
//   1. loading      — AuthContext is still resolving the session
//                     from the URL fragment.
//   2. no session   — link expired, was already used, or the user
//                     hit this page directly without clicking the
//                     reset link.
//   3. has session  — show the form.
export default function ResetPasswordPage() {
  const { loading, session } = useAuth();
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  // After a successful password update, give the user a beat to
  // read the confirmation, then send them to their dashboard.
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => navigate('/territories'), 1500);
    return () => clearTimeout(t);
  }, [done, navigate]);

  const validate = () => {
    if (password.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (password !== confirm) {
      return 'Passwords do not match.';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password || !confirm || submitting) return;
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await updatePassword(password);
      setDone(true);
    } catch (err) {
      setError(err.message || 'Could not update password.');
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
          Set a new password
        </h1>

        {!supabaseConfigured && (
          <div style={warnStyle}>
            Authentication isn&rsquo;t configured in this environment.
            Contact the SellerSignal team for access.
          </div>
        )}

        {loading && (
          <p style={mutedStyle}>Verifying reset link\u2026</p>
        )}

        {!loading && !session && supabaseConfigured && (
          <div style={confirmStyle}>
            <div style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'var(--call-now)',
              marginBottom: 8,
              fontFamily: 'var(--font-sans)',
            }}>
              Reset link invalid
            </div>
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 14,
              color: 'var(--text)',
              lineHeight: 1.6,
            }}>
              This reset link is expired or has already been used.{' '}
              <Link to="/forgot-password" style={{
                color: 'var(--accent)',
                textDecoration: 'none',
                borderBottom: '1px dotted var(--accent)',
              }}>
                Request a new one
              </Link>.
            </div>
          </div>
        )}

        {!loading && session && !done && (
          <form onSubmit={handleSubmit}>
            <p style={{
              fontFamily: 'var(--font-serif)',
              color: 'var(--text-secondary)',
              fontSize: 15,
              lineHeight: 1.6,
              marginBottom: 'var(--space-xl)',
            }}>
              Choose a new password for your account.
            </p>
            <label style={labelStyle}>New password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoFocus
              disabled={submitting}
              style={inputStyle}
            />
            <label style={{ ...labelStyle, marginTop: 'var(--space-md)' }}>
              Confirm new password
            </label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Re-enter your new password"
              disabled={submitting}
              style={inputStyle}
            />
            {error && (
              <div style={errorStyle}>{error}</div>
            )}
            <button
              type="submit"
              disabled={submitting || !password || !confirm}
              style={primaryButtonStyle(submitting || !password || !confirm)}
            >
              {submitting ? 'Updating\u2026' : 'Update password'}
            </button>
          </form>
        )}

        {done && (
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
              Password updated
            </div>
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 14,
              color: 'var(--text)',
              lineHeight: 1.6,
            }}>
              Taking you to your dashboard\u2026
            </div>
          </div>
        )}
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

const mutedStyle = {
  fontFamily: 'var(--font-serif)',
  color: 'var(--text-tertiary)',
  fontSize: 14,
};
