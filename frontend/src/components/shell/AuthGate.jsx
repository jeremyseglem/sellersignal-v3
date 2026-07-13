import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/AuthContext.jsx';

// AuthGate — wraps protected routes. Behavior depends on the
// VITE_AUTH_REQUIRED build-time env var:
//
//   default (unset/anything)  → enforce auth. Signed-out users get
//                                redirected to /login with ?next=
//                                preserving their original path.
//   VITE_AUTH_REQUIRED=false  → demo mode. Auth is fully bypassed;
//                                anyone with the URL can hit any
//                                route. Only for deliberate demos.
//
// SECURE BY DEFAULT: as of the post-launch auth hardening, the gate
// enforces auth unless explicitly disabled with VITE_AUTH_REQUIRED=
// 'false'. (Previously it was demo-by-default, which left protected
// routes open whenever the bundle wasn't built with the flag set.)
// The authoritative data gate is server-side (briefings/map/parcels
// require_zip_access); this is the UI gate that also drives the
// logout → /login redirect.
const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED !== 'false';

export default function AuthGate({ children }) {
  const { loading, session } = useAuth();
  const location = useLocation();

  // Per-URL demo bypass: ?demo=1 renders the page without auth. Only
  // the briefing page honors this flag, and there it loads fixture-only
  // /api/demo/* data (no real records reachable). Scoped to the query
  // string so it can't be used to reach live authed data on other routes.
  if (new URLSearchParams(location.search).get('demo') === '1') {
    return children;
  }

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
