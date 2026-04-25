import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/AuthContext.jsx';

// AuthGate — wraps protected routes. Redirects to /login when the
// user is signed out. Renders a simple loading state while the
// initial auth check is in flight (so the app doesn't briefly flash
// the login page for users who actually have a valid session in
// localStorage).
//
// Usage in App.jsx:
//   <Route path="/territories" element={
//     <AuthGate><TerritoriesPage /></AuthGate>
//   } />
//
// The redirect carries the original path as a 'next' query param
// so LoginPage can route the user back to where they were after
// magic-link auth completes.
export default function AuthGate({ children }) {
  const { loading, session } = useAuth();
  const location = useLocation();

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
