import ErrorBoundary from './components/ErrorBoundary.jsx';
import { Routes, Route, Navigate } from 'react-router-dom';

import HomePage            from './pages/HomePage.jsx';
import HomeOverture        from './pages/HomeOverture.jsx';
import WelcomePage         from './pages/WelcomePage.jsx';
import V5Shell             from './pages/V5Shell.jsx';
import V5Territories       from './pages/V5Territories.jsx';
import V5Network           from './pages/V5Network.jsx';
import V5Briefing          from './pages/V5Briefing.jsx';
import LoginPage           from './pages/LoginPage.jsx';
import SignupPage          from './pages/SignupPage.jsx';
import ForgotPasswordPage  from './pages/ForgotPasswordPage.jsx';
import ResetPasswordPage   from './pages/ResetPasswordPage.jsx';
import TerritoriesPage     from './pages/TerritoriesPage.jsx';
import BriefingPage    from './pages/BriefingPage.jsx';
import MyLeadsPage     from './pages/MyLeadsPage.jsx';
import LettersPage     from './pages/LettersPage.jsx';
import ProfilePage     from './pages/ProfilePage.jsx';
import VoiceOnboardingPage from './pages/VoiceOnboardingPage.jsx';
import NetworkPage from './pages/NetworkPage.jsx';
import NetworkJoinPage from './pages/NetworkJoinPage.jsx';
import { PrivacyPage, TermsPage } from './pages/LegalPages.jsx';

import AuthGate from './components/shell/AuthGate.jsx';
import { useAuth } from './lib/AuthContext.jsx';

// Application routes for the V3 React SPA.
//
// Public routes (no auth):
//   /                — marketing landing page
//   /login           — email + password sign-in, with magic-link fallback
//   /signup          — email + password 'request access'
//   /forgot-password — request a password-reset email
//   /reset-password  — landing page from reset email; sets new password
//   /privacy         — privacy policy
//   /terms           — terms of service
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
    <ErrorBoundary>
    <Routes>
      {/* Public marketing + auth */}
      <Route path="/"                element={<HomeOverture       />} />
      <Route path="/welcome"         element={<WelcomePage        />} />
      <Route path="/classic-home"    element={<HomePage           />} />
      <Route path="/login"           element={<LoginPage          />} />
      <Route path="/signup"          element={<SignupPage         />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password"  element={<ResetPasswordPage  />} />
      <Route path="/privacy"         element={<PrivacyPage        />} />
      <Route path="/terms"           element={<TermsPage          />} />

      {/* Authenticated app — the V5 shell and every surface inside it
          sit behind AuthGate: real Supabase sessions only. */}
      <Route element={<AuthGate><V5Shell/></AuthGate>}>
        <Route path="/territories"   element={<V5Territories/>} />
        <Route path="/zip/:zip"      element={<V5Briefing/>} />
        <Route path="/my-leads"      element={<MyLeadsPage/>} />
        <Route path="/letters"       element={<LettersPage/>} />
        <Route path="/profile"       element={<ProfilePage/>} />
        <Route path="/profile/voice" element={<VoiceOnboardingPage/>} />
        <Route path="/network"       element={<V5Network/>} />
        <Route path="/network/classic" element={<NetworkPage/>} />
        <Route path="/network/join"  element={<NetworkJoinPage/>} />
      </Route>

      {/* Legacy alias */}
      <Route path="/coverage" element={<Navigate to="/territories" replace />} />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </ErrorBoundary>
  );
}


