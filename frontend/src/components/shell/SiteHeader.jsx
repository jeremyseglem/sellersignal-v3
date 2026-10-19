import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Logo from './Logo.jsx';
import styles from './SiteHeader.module.css';

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
// Mobile (<768px): the right-hand desktop nav collapses to a hamburger
// toggle. Tapping it opens a dropdown sheet below the header with the
// same nav items. The sheet auto-closes on route change. The desktop
// layout is unchanged at >=768px.
//
// Header keeps a fixed height (56px) and a dark background — matches
// the brand reference. White-space chrome below the header is the
// page's responsibility.
export default function SiteHeader({ agent, onSignOut, mode = 'auto' }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile sheet whenever the route changes. Without this,
  // tapping a nav link from inside the sheet would navigate but leave
  // the sheet open over the new page.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

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
    <>
      <header className={styles.header}>
        {/* Logo links to the agent's home (territories list) when
            signed in, or marketing root when not. */}
        <Link
          to={resolvedMode === 'authenticated' ? '/territories' : '/'}
          style={{ textDecoration: 'none' }}
          aria-label="SellerSignal home"
        >
          <Logo tone="light" size="default" />
        </Link>

        {/* Desktop nav — hidden at <768px via the CSS module. */}
        <nav className={styles.desktopNav}>
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

        {/* Mobile toggle — hidden at >=768px via the CSS module. */}
        <button
          type="button"
          className={styles.mobileToggle}
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          aria-controls="site-header-mobile-sheet"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <CloseIcon /> : <HamburgerIcon />}
        </button>
      </header>

      {/* Mobile sheet — anchored to viewport, rendered outside the
          header element so the header's overflow / stacking doesn't
          interfere. Visibility is controlled by the data-open
          attribute the CSS reads. */}
      <div
        id="site-header-mobile-sheet"
        className={styles.mobileSheet}
        data-open={menuOpen ? 'true' : 'false'}
        role="menu"
      >
        {resolvedMode === 'authenticated' ? (
          <AuthenticatedMobileMenu
            agent={agent}
            isActive={isActive}
            onSignOut={() => {
              setMenuOpen(false);
              if (onSignOut) onSignOut();
            }}
          />
        ) : resolvedMode === 'demo' ? (
          <DemoMobileMenu isActive={isActive} />
        ) : (
          <PublicMobileMenu isActive={isActive} />
        )}
      </div>
    </>
  );
}


// ── Icons ────────────────────────────────────────────────────────
// Inline SVGs so we don't pull in an icon library for two shapes.
// currentColor lets the icon inherit the toggle's text color.

function HamburgerIcon() {
  return (
    <svg width="20" height="14" viewBox="0 0 20 14" fill="none" aria-hidden="true">
      <path d="M1 1h18M1 7h18M1 13h18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2 2l12 12M14 2L2 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
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

function PublicMobileMenu({ isActive }) {
  return (
    <>
      <Link
        to="/login"
        className={`${styles.mobileSheetItem} ${isActive('/login') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        Sign in
      </Link>
      <Link
        to="/signup"
        className={styles.mobileSheetItem}
        role="menuitem"
      >
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

function DemoMobileMenu({ isActive }) {
  return (
    <>
      <Link
        to="/territories"
        className={`${styles.mobileSheetItem} ${isActive('/territories') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        Briefing
      </Link>
      <div className={styles.mobileSheetIdentity}>Demo</div>
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
      <Link to="/my-leads" style={navBtnStyle('ghost', isActive('/my-leads'))}>
        My Leads
      </Link>
      <Link to="/letters" style={navBtnStyle('ghost', isActive('/letters'))}>
        Letters
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

function AuthenticatedMobileMenu({ agent, isActive, onSignOut }) {
  const displayName = agent?.full_name || agent?.email || 'Account';
  return (
    <>
      <Link
        to="/territories"
        className={`${styles.mobileSheetItem} ${isActive('/territories') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        Briefing
      </Link>
      <Link
        to="/my-leads"
        className={`${styles.mobileSheetItem} ${isActive('/my-leads') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        My Leads
      </Link>
      <Link
        to="/letters"
        className={`${styles.mobileSheetItem} ${isActive('/letters') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        Letters
      </Link>
      <Link
        to="/profile"
        className={`${styles.mobileSheetItem} ${isActive('/profile') ? styles.mobileSheetItemActive : ''}`}
        role="menuitem"
      >
        Profile
      </Link>
      <div className={styles.mobileSheetIdentity}>{displayName}</div>
      <button
        type="button"
        className={styles.mobileSheetSignOut}
        onClick={onSignOut}
        role="menuitem"
      >
        Sign out
      </button>
    </>
  );
}


// ── Shared button style (DESKTOP NAV ONLY) ──────────────────────
// Two variants matching the legacy reference: ghost (transparent,
// thin border) and primary (gold). Active state on ghost adds gold
// border + gold text.
//
// The mobile sheet uses its own classes from the CSS module —
// these inline styles are only consulted for the desktop nav row.
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

