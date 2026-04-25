import { Link, useLocation } from 'react-router-dom';
import Logo from './Logo.jsx';

// Build-time feature flag mirroring AuthGate. When auth isn't
// required, the header renders 'demo nav' (Briefing button only)
// instead of the public marketing CTAs (Sign in / Request access).
// This gives Jeremy + Brian the lived-in 'agent already inside the
// product' feel without forcing actual sign-in.
const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === 'true';

// SiteHeader — dark navigation bar present on every authenticated page.
//
// Left: SellerSignal logo (light tone, links to /territories — the home
// page for signed-in agents). Right: nav links + agent identity area.
//
// Auth state is opt-in via the `agent` prop: when null/undefined, the
// header renders public-mode (Sign in / Request access). When set,
// header renders authenticated-mode (Briefing / Territories /
// agent name / Sign out).
//
// Header keeps a fixed height (56px) and a dark background — matches
// the brand reference. White-space chrome below the header is the
// page's responsibility.
export default function SiteHeader({ agent, onSignOut, mode = 'auto' }) {
  const location = useLocation();
  // Mode resolution:
  //   explicit override   — caller passed mode='public' or 'authenticated'
  //   agent present       — render authenticated
  //   auth not required   — render demo-app (Briefing nav, no agent)
  //   else                — render public marketing nav (Sign in / Request access)
  const resolvedMode =
    mode === 'public'        ? 'public'
    : mode === 'authenticated' ? 'authenticated'
    : agent                  ? 'authenticated'
    : !AUTH_REQUIRED         ? 'demo'
    : 'public';

  const isActive = (path) => {
    if (path === '/territories') {
      return location.pathname === '/territories' ||
             location.pathname.startsWith('/zip/');
    }
    return location.pathname === path;
  };

  return (
    <header style={{
      position: 'sticky',
      top: 0,
      zIndex: 100,
      height: 56,
      padding: '0 32px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      background: 'var(--bg-dark)',
      borderBottom: '1px solid rgba(245, 240, 235, 0.06)',
      fontFamily: 'var(--font-sans)',
    }}>
      {/* Logo links to the agent's home (territories list) when
          signed in, or marketing root when not. */}
      <Link
        to={resolvedMode === 'authenticated' ? '/territories' : '/'}
        style={{ textDecoration: 'none' }}
        aria-label="SellerSignal home"
      >
        <Logo tone="light" size="default" />
      </Link>

      <nav style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        {resolvedMode === 'authenticated' ? (
          <AuthenticatedNav
            agent={agent}
            isActive={isActive}
            onSignOut={onSignOut}
          />
        ) : resolvedMode === 'demo' ? (
          <DemoNav isActive={isActive} />
        ) : (
          <PublicNav isActive={isActive} />
        )}
      </nav>
    </header>
  );
}


// ── Public nav (marketing pages, login, signup) ─────────────────
function PublicNav({ isActive }) {
  return (
    <>
      <Link to="/login" style={navBtnStyle('ghost', isActive('/login'))}>
        Sign in
      </Link>
      <Link to="/signup" style={navBtnStyle('primary', false)}>
        Request access
      </Link>
    </>
  );
}


// ── Demo nav (auth bypassed; product walkthrough mode) ──────────
// Same visual treatment as authenticated nav but skips the agent
// name slot and the Sign Out button. Looks 'lived in' to Jeremy
// and Brian without misrepresenting that anyone is actually
// signed in. The 'Demo' tag in the corner is honest about state
// without being intrusive.
function DemoNav({ isActive }) {
  return (
    <>
      <Link to="/territories" style={navBtnStyle('ghost', isActive('/territories'))}>
        Briefing
      </Link>
      <span style={{
        color: 'rgba(245, 240, 235, 0.4)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        marginLeft: 12,
        fontFamily: 'var(--font-sans)',
      }}>
        Demo
      </span>
    </>
  );
}


// ── Authenticated nav (territories, briefing, profile) ──────────
function AuthenticatedNav({ agent, isActive, onSignOut }) {
  const displayName = agent?.full_name || agent?.email || 'Account';
  return (
    <>
      <Link to="/territories" style={navBtnStyle('ghost', isActive('/territories'))}>
        Briefing
      </Link>
      <Link to="/profile" style={navBtnStyle('ghost', isActive('/profile'))}>
        Profile
      </Link>
      <span style={{
        color: 'rgba(245, 240, 235, 0.55)',
        fontSize: 13,
        marginLeft: 12,
        marginRight: 12,
      }}>
        {displayName}
      </span>
      <button
        onClick={onSignOut}
        style={{
          ...navBtnStyle('ghost', false),
          border: '1px solid rgba(245, 240, 235, 0.18)',
          background: 'transparent',
          cursor: 'pointer',
        }}
      >
        Sign out
      </button>
    </>
  );
}


// ── Shared button style ─────────────────────────────────────────
// Two variants matching the legacy reference: ghost (transparent,
// thin border) and primary (gold). Active state on ghost adds gold
// border + gold text.
function navBtnStyle(variant, active) {
  const base = {
    padding: '8px 18px',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 500,
    fontFamily: 'var(--font-sans)',
    textDecoration: 'none',
    transition: 'all 0.2s ease',
    display: 'inline-flex',
    alignItems: 'center',
  };
  if (variant === 'primary') {
    return {
      ...base,
      background: 'var(--accent)',
      border: 'none',
      color: 'var(--text-inverse)',
      fontWeight: 600,
    };
  }
  // ghost
  return {
    ...base,
    background: 'transparent',
    border: active
      ? '1px solid var(--accent)'
      : '1px solid rgba(245, 240, 235, 0.18)',
    color: active
      ? 'var(--accent)'
      : 'rgba(245, 240, 235, 0.7)',
  };
}
