import { Routes, Route, Navigate } from 'react-router-dom';

import HomePage        from './pages/HomePage.jsx';
import LoginPage       from './pages/LoginPage.jsx';
import SignupPage      from './pages/SignupPage.jsx';
import TerritoriesPage from './pages/TerritoriesPage.jsx';
import BriefingPage    from './pages/BriefingPage.jsx';
import ProfilePage     from './pages/ProfilePage.jsx';
import { PrivacyPage, TermsPage } from './pages/LegalPages.jsx';

import AuthGate from './components/shell/AuthGate.jsx';
import { useAuth } from './lib/AuthContext.jsx';

// Application routes for the V3 React SPA.
//
// Public routes (no auth):
//   /            — marketing landing page
//   /login       — magic-link sign-in
//   /signup      — magic-link 'request access'
//   /privacy     — privacy policy
//   /terms       — terms of service
//
// Authenticated routes (gated via <AuthGate>):
//   /territories — agent's territory list
//   /zip/:zip    — briefing (operator cards, tiered map, dossier)
//   /profile     — agent profile form
//
// Legacy alias: /coverage redirects to /territories.
//
// AuthGate handles the redirect-to-login flow, including preserving
// the original path as ?next= so post-sign-in the user lands where
// they were trying to go.
//
// Inside protected pages, components call useAuth() directly to pull
// the current profile + signOut handler. App.jsx no longer threads
// these as explicit props — the context is the source of truth.
export default function App() {
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
        element={
          <AuthGate>
            <AuthenticatedTerritories />
          </AuthGate>
        }
      />
      <Route
        path="/zip/:zip"
        element={
          <AuthGate>
            <AuthenticatedBriefing />
          </AuthGate>
        }
      />
      <Route
        path="/profile"
        element={
          <AuthGate>
            <ProfilePage />
          </AuthGate>
        }
      />

      {/* Legacy alias */}
      <Route path="/coverage" element={<Navigate to="/territories" replace />} />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}


// Thin wrappers that pull profile + signOut from context and pass
// them to the page as props. Pages are kept prop-driven (rather
// than calling useAuth themselves) so they can be reused in
// non-authenticated contexts later (e.g. an admin preview tool).
function AuthenticatedTerritories() {
  const { profile, signOut } = useAuth();
  return <TerritoriesPage agent={profile} onSignOut={signOut} />;
}

function AuthenticatedBriefing() {
  const { profile, signOut } = useAuth();
  return <BriefingPage agent={profile} onSignOut={signOut} />;
}
