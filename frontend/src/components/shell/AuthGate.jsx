import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/AuthContext.jsx';

// AuthGate — wraps protected routes. Behavior depends on the
// VITE_AUTH_REQUIRED build-time env var:
//
//   VITE_AUTH_REQUIRED=true   → enforce auth. Signed-out users get
//                                redirected to /login with ?next=
//                                preserving their original path.
//   anything else (default)   → demo mode. Auth is fully bypassed.
//                                Anyone with the URL can hit any
//                                route. Useful for early beta where
//                                Jeremy + Brian want to walk the
//                                product without logging in.
//
// Demo mode is the default because beta validation matters more
// than gating during the 'show this to my partner' phase. Flip
// VITE_AUTH_REQUIRED=true in Railway when public launch needs
// real auth, and the gate re-engages without any code changes.
//
// AuthContext + Supabase Auth still run in demo mode — the user
// just doesn't need to sign in to see protected pages. If they DO
// sign in (manually navigating to /login), header and profile
// still work normally. The flag only controls redirects.
const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === 'true';

export default function AuthGate({ children }) {
  const { loading, session } = useAuth();
  const location = useLocation();

  // Demo mode: render children unconditionally. Skip the loading
  // gate too — no point waiting on an auth check we're going to
  // ignore anyway.
  if (!AUTH_REQUIRED) {
    return children;
  }

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-serif)',
        fontStyle: 'italic',
        fontSize: 14,
      }}>
        Loading…
      </div>
    );
  }

  if (!session) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return children;
}
