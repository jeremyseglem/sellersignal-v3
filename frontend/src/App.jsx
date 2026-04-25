import { Routes, Route, Navigate } from 'react-router-dom';

import HomePage        from './pages/HomePage.jsx';
import LoginPage       from './pages/LoginPage.jsx';
import SignupPage      from './pages/SignupPage.jsx';
import TerritoriesPage from './pages/TerritoriesPage.jsx';
import BriefingPage    from './pages/BriefingPage.jsx';
import ProfilePage     from './pages/ProfilePage.jsx';
import { PrivacyPage, TermsPage } from './pages/LegalPages.jsx';

// Application routes for the V3 React SPA.
//
// Public routes (no auth required for now — Session 2 adds the auth
// guard wrapper):
//   /            — marketing landing page
//   /login       — sign-in (Supabase magic link, Session 2)
//   /signup      — request access (invite-only beta)
//   /privacy     — privacy policy placeholder
//   /terms       — terms of service placeholder
//
// Authenticated routes (Session 2 will gate these on auth):
//   /territories — agent's territory list (the post-sign-in home)
//   /zip/:zip    — the briefing for a given ZIP — operator cards,
//                  tiered map, dossier
//   /profile     — agent profile (name, brokerage, signature)
//
// Legacy aliases (kept temporarily so any existing bookmarks survive
// the transition):
//   /coverage    — redirects to /territories
export default function App() {
  // Session 1: no real auth wired yet, so agent is null everywhere
  // and the authenticated-mode pages just render with public-style
  // headers. Session 2 replaces this with a real AuthProvider that
  // populates `agent` from Supabase and threads it down via context
  // (or props for now).
  const agent = null;
  const handleSignOut = () => {
    // Stub — Session 2 wires real Supabase signOut.
  };

  return (
    <Routes>
      {/* Public marketing + auth */}
      <Route path="/"        element={<HomePage    />} />
      <Route path="/login"   element={<LoginPage   />} />
      <Route path="/signup"  element={<SignupPage  />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/terms"   element={<TermsPage   />} />

      {/* Authenticated app surfaces */}
      <Route
        path="/territories"
        element={<TerritoriesPage agent={agent} onSignOut={handleSignOut} />}
      />
      <Route
        path="/zip/:zip"
        element={<BriefingPage agent={agent} onSignOut={handleSignOut} />}
      />
      <Route
        path="/profile"
        element={<ProfilePage agent={agent} onSignOut={handleSignOut} />}
      />

      {/* Legacy alias — anyone hitting /coverage gets redirected to
          the new /territories route. Remove after a few months. */}
      <Route path="/coverage" element={<Navigate to="/territories" replace />} />

      {/* Catch-all — unknown URL goes back to the marketing page */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
