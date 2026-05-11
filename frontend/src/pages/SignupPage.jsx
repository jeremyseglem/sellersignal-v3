import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { signUpWithPassword, supabaseConfigured } from '../lib/supabase.js';

// SignupPage — email + password 'request access' flow. Replaces the
// previous magic-link-only signup, which would have been broken on
// corporate Outlook inboxes (Microsoft Defender Safe Links
// pre-fetches and consumes one-time-use magic-link tokens before the
// user can click them).
//
// "Confirm email" is DISABLED in the Supabase Auth dashboard, so
// signUp returns a session immediately. The user lands on
// /territories signed in — empty until an admin assigns them a ZIP.
//
// Account creation is permissive (anyone with an email can sign up)
// because beta is invite-only at the ZIP-assignment layer rather
// than at the account-creation layer. Creating an account does not
// give anyone access to data.
//
// Once Supabase Auth inserts the new auth.users row, the database
// trigger create_agent_profile_on_signup creates the matching
// agent_profiles_v3 row (same path as the previous magic-link flow,
// so nothing schema-side needs to change).
export default function SignupPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Client-side validation. Server is the real authority (Supabase
  // enforces its own minimum), but catching mismatches up front
  // saves a round trip.
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
    if (!email || !password || !confirm || submitting) return;
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await signUpWithPassword(email, password);
      // Confirm-email is off in Supabase, so signUp returns a session
      // and AuthContext's onAuthStateChange picks it up. Navigate to
      // territories so the user sees their (empty) dashboard.
      navigate('/territories');
    } catch (err) {
      // Common cases:
      //   - "User already registered" (existing magic-link account
      //     trying to sign up again) — point them to /login.
      //   - Supabase password policy violations (rare with 8+ chars).
      const msg = err.message || 'Could not create account.';
      if (/already registered|already exists/i.test(msg)) {
        setError('An account with that email already exists. Try signing in instead.');
      } else {
        setError(msg);
      }
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
          Beta is invite-only with one agent per ZIP. Create your
          account below — a member of the team will assign your
          territory.
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
          <label style={{ ...labelStyle, marginTop: 'var(--space-md)' }}>
            Password
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            disabled={submitting || !supabaseConfigured}
            style={inputStyle}
          />
          <label style={{ ...labelStyle, marginTop: 'var(--space-md)' }}>
            Confirm password
          </label>
          <input
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Re-enter your password"
            disabled={submitting || !supabaseConfigured}
            style={inputStyle}
          />
          {error && (
            <div style={errorStyle}>{error}</div>
          )}
          <button
            type="submit"
            disabled={submitting || !email || !password || !confirm || !supabaseConfigured}
            style={primaryButtonStyle(submitting || !email || !password || !confirm || !supabaseConfigured)}
          >
            {submitting ? 'Creating account\u2026' : 'Create account'}
          </button>
        </form>

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


// ── Form styles (mirror LoginPage) ──────────────────────────────
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
